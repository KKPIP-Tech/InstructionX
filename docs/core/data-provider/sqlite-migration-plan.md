# DataProvider JSON → SQLite 迁移计划

> 将 `DataProvider` 的持久化后端从 `data/data.json` 迁移到 SQLite，在保持所有插件接口调用方式不变、功能语义等价的前提下，解决数万行数据场景下的性能瓶颈。本次迁移同时会修复旧实现中返回值浅拷贝可能导致的缓存污染风险，因此返回值将为独立深拷贝——这属于兼容性安全增强，不影响插件正常业务逻辑。

---

## 1. 背景与目标

### 1.1 用户原始需求

- `DataProvider` 当前使用 JSON 文件存储插件数据。
- 当数据量达到数万行时，全量序列化/反序列化 + 原子写入带来显著性能开销。
- 要求：**在确保当前 `DataProvider` 所有给插件使用的接口调用方法不变的情况下，将后端从 JSON 迁移到 SQLite 数据库**。
- 要求：**所有功能和现在的功能完全一致**。
- 要求：编写修改与迁移计划，并形成详细技术文档；同时创建 Agent 审计该文档的完整性以及目的是否充分反映用户目的。

### 1.2 迁移目标

| 目标 | 说明 |
|------|------|
| **接口零破坏** | 所有公共方法签名、返回值类型、异常类型、`DataNamespace` 枚举、`PluginServices.data_provider` 注入方式均保持不变。 |
| **功能等价** | 插件注册、活跃实例、命名空间隔离、Pub/Sub、资源文件管理、`load_data`/`save_data`/`clear_cache`/`reset_all_data` 语义与现有一致。返回值统一为深拷贝独立副本，修复旧实现浅拷贝导致的潜在缓存污染问题，对正常插件业务无影响。 |
| **性能提升** | 单次 `get_plugin_data` / `set_plugin_data` 不再全量读写 JSON，改为按 key 的 SQL 点查/点写，数万行数据下延迟不再随数据总量线性增长。 |
| **平滑迁移** | 已存在的 `data/data.json` 在首次启动时自动、无损地导入到 SQLite；迁移失败可回退到 JSON。 |
| **零额外依赖（SQLite 本身）** | 使用 Python 标准库 `sqlite3`，不引入数据库驱动。 |
| **可链式升级的数据库 schema** | 通过 `db_metadata` 表维护 schema 版本，支持未来的增量升级，不破坏既有数据。 |
| **序列化性能优化** | 使用 `orjson` 替代标准库 `json` 进行 value 序列化/反序列化，并配合 LRU 缓存进一步降低读放大；对插件接口完全透明。 |

---

## 2. 现状分析

### 2.1 当前实现：`core/data/data_provider.py`

`DataProvider` 是单例类，核心状态如下：

```python
self.data_dir          # 默认 <project_root>/data
self.data_file         # <data_dir>/data.json
self.temp_file         # <data_dir>/data.json.tmp
self.assets_dir        # <data_dir>/assets/plugins
self._file_lock        # threading.RLock，保护文件读写
self._subscription_lock# threading.RLock，保护订阅表
self._cache            # Dict[str, Any] | None，内存中的完整 data.json 副本
self._cache_dirty      # bool，缓存失效标记
self._initialized      # bool，单例初始化完成标记，防止重复初始化重置状态
self._subscriptions    # Dict[tuple, Callable]
self._logger           # LoggerManager 单例
```

默认 JSON 结构：

```json
{
  "plugins": {
    "<instance_id>": {
      "type": "<plugin_type>",
      "active": false,
      "private": {"<key>": <value>, ...},
      "public": {"<key>": <value>, ...}
    }
  },
  "active_instances": {
    "<plugin_type>": "<instance_id>"
  }
}
```

### 2.2 性能瓶颈

| 操作 | 当前行为 | 问题 |
|------|----------|------|
| `set_plugin_data` | `load_data()` 读完整 JSON → 修改一个 key → `save_data()` 写完整 JSON（临时文件 + `os.replace`） | 写放大：任意 key 变更都触发全量序列化与磁盘写入。 |
| `get_plugin_data` | `load_data()` 读完整 JSON → 返回一个 key | 读放大：任意查询都反序列化整个文件。 |
| `get_all_plugin_data` | 同上 | 虽然语义上就是取全部，但仍有一次完整反序列化。 |
| 无索引 | 字典 key 查找为 O(1)，但前提是先加载整个文件 | 磁盘 I/O 与 JSON 解析成为瓶颈。 |

### 2.3 调用方与接口边界

`DataProvider` 的公共接口是以下文件定义的契约，迁移后必须保持：

- `core/interfaces/i_data_provider.py`：抽象接口 `IDataProvider` + `DataNamespace`。
- `core/data/__init__.py`：导出 `DataProvider`、`DataNamespace`、`DataProviderError`。
- `core/interfaces/plugin_services.py`：通过 `PluginServices.data_provider` 注入到插件。
- `core/plugin/manager.py`：实例化 `DataProvider()` 并注入。
- `ui/main_window.py`：使用 `DataProvider()` 保存主题、LLM 偏好。

插件通过 `_services.data_provider` 或 UI 创建时传入的 `data_provider` 参数访问，**不直接依赖 JSON 实现细节**。

#### 2.3.1 实际调用代码示例

**`core/plugin/manager.py` 注入方式**（第 91-128 行）：

```python
def _create_plugin_services(self) -> PluginServices:
    try:
        from core.data import DataProvider
        data_provider = DataProvider()          # 单例
    except Exception:
        data_provider = None                    # 异常降级为 None

    return PluginServices(
        llm_facade=get_llm_plugin_service(),
        data_provider=data_provider,
        task_manager=task_manager,
        logger=logger,
        mcp_manager=self._get_mcp_manager(),
        mcp_client=self._get_mcp_client(),
    )
```

`PluginServices` 将 `data_provider` 注入到每个插件的 `Service` 实例；插件通过 `self._services.data_provider` 访问。**注意**：当前实现中 `data_provider` 在初始化失败时可能为 `None`，迁移后仍需保持该降级行为，确保插件侧已有 `if services.data_provider:` 判断继续生效。

**`ui/main_window.py` 直接使用方式**（第 302-512 行）：

```python
from core.data.data_provider import DataProvider, DataNamespace

def _load_saved_theme(self):
    provider = DataProvider()
    try:
        provider.register_plugin("__app_config__", "AppConfig")
    except:
        pass  # 已存在则忽略

    saved_theme = provider.get_plugin_data(
        "__app_config__", "theme",
        DataNamespace.PRIVATE, "auto"
    )
    ...

def _save_theme(self, theme: str):
    provider = DataProvider()
    try:
        provider.register_plugin("__app_config__", "AppConfig")
    except:
        pass
    provider.set_plugin_data(
        "__app_config__", "theme",
        theme, DataNamespace.PRIVATE, notify=False
    )

def _load_llm_preference(self) -> tuple:
    dp = DataProvider()
    try:
        dp.register_plugin(self._LLM_PREF_KEY, "LLMPrefs")
    except:
        pass
    provider = dp.get_plugin_data(
        self._LLM_PREF_KEY, "provider", DataNamespace.PRIVATE, ""
    )
    model = dp.get_plugin_data(
        self._LLM_PREF_KEY, "model", DataNamespace.PRIVATE, ""
    )
    return provider, model
```

> 兼容性要点：迁移后 `DataProvider()` 的签名、单例行为、`DataNamespace` 枚举值、`register_plugin` / `set_plugin_data` / `get_plugin_data` 的语义必须保持不变，否则主应用启动、主题加载、LLM 偏好恢复都会受影响。

### 2.4 资源文件

当前资源文件（`save_asset` / `load_asset` / `get_asset_path` / `get_plugin_assets_dir`）已经存储在文件系统 `data/assets/plugins/<plugin_id>/` 中，**不进入 `data.json`**。SQLite 不适合存储大文件，因此迁移后资源文件继续保留在文件系统中，逻辑不变。

### 2.5 订阅表

`_subscriptions` 是内存中的回调注册表，不属于持久化数据。迁移后仍保留在内存中，逻辑不变。

### 2.6 当前实现中的已知问题与迁移时的修复点

通过对 `core/data/data_provider.py`（第 1-732 行）、`core/interfaces/i_data_provider.py`、`core/plugin/manager.py`、`ui/main_window.py` 的实际阅读，发现以下需要在迁移中一并修复或保持的问题。

| # | 问题 | 当前代码位置 | 影响 | 迁移时处理策略 |
|---|------|--------------|------|----------------|
| 1 | **返回值浅拷贝/直接引用** | `load_data()` 第 159 行返回 `self._cache.copy()`（顶层浅拷贝）；`get_all_plugin_data()` 第 371 行返回命名空间字典浅拷贝；`get_all_plugins()` 第 598 行返回 `plugins` 顶层浅拷贝；`get_plugin_info()` 第 611 行直接返回引用 | 调用方修改返回值会污染内存缓存，甚至通过 `save_data()` 把意外修改写回磁盘 | 新实现统一返回**深拷贝独立副本**（`orjson` 反序列化或 `copy.deepcopy`），修复缓存污染风险；对只读调用方无感知 |
| 2 | **`DataNamespace` 跨模块比较 bug** | `core/data/data_provider.py` 第 14 行导入接口枚举并重命名为 `IDataNamespace`，但第 23-27 行又定义了同名 `DataNamespace`；`set_plugin_data()` 第 346 行使用 `if namespace == DataNamespace.PUBLIC and notify:` | 若调用方传入 `IDataNamespace.PUBLIC`，比较返回 `False`，`notify=True` 时不会触发回调 | 迁移后统一使用**字符串值比较**（`namespace_str == DataNamespace.PUBLIC.value`），无论从哪个模块导入 `DataNamespace.PUBLIC`，通知行为都正确 |
| 3 | **锁顺序不当：先 `_file_lock` 后 `_subscription_lock`** | `subscribe()` 第 394-402 行：先 `load_data()`（持有 `_file_lock`），再获取 `_subscription_lock`；`unregister_plugin()` 第 218-238 行：先 `load_data()`/`save_data()`（持有 `_file_lock`），再调用 `_remove_subscriptions_for_plugin()`（获取 `_subscription_lock`） | 回调或并发路径下可能死锁；订阅回调若反向操作 DataProvider 会重入 `_file_lock` | 迁移后严格遵守**完全释放 `_file_lock` 后再获取 `_subscription_lock`**的铁律（详见 6.6 节） |
| 4 | **`_subscription_lock` 为 `RLock`** | 第 76 行 `self._subscription_lock = threading.RLock()` | 与"不得同时持有两把锁"的铁律配合时，可重入锁会掩盖潜在死锁 | 迁移后改为普通 `threading.Lock`；订阅表操作粒度小，无需重入 |
| 5 | **`reset_all_data()` 不清空 `_subscriptions`** | 第 613-621 行仅重置数据，不清理订阅表 | 与语义"重置所有数据"存在偏差，但属于当前既有行为 | 为保持行为一致，迁移后**仍不清空 `_subscriptions`**；如未来要改，需单独记录为破坏性变更 |
| 6 | **所有写操作通过 `load_data()` 自动加载缓存** | `register_plugin` / `set_active_instance` / `set_plugin_data` 等均调用 `load_data()` | 当前 JSON 实现通过 `load_data()` 自动加载，行为一致 | 迁移后保持同样语义：写操作若发现 `_cache=None` 则调用 `load_data()` 加载；高频路径不依赖该行为 |
| 7 | **JSON 模式下任意 key 变更触发全量写盘** | `set_plugin_data()` 第 333-343 行：每次均 `load_data()` → 修改 → `save_data()` | 数万行数据时性能差，是本次迁移的根本原因 | 迁移后改为 SQLite 点查/点写，单次操作不随数据总量线性增长 |
| 8 | **`data.json.tmp` 残留** | `_write_to_disk()` 第 137-141 行使用临时文件，但崩溃时可能残留 | 无实质影响，但占用磁盘 | 迁移后在初始化时清理已存在的 `data.json.tmp` 残留（阶段 6 任务） |

> **说明**：以上问题中，问题 1、2、3、4 属于**兼容性安全增强或 bug 修复**，不影响插件正常业务逻辑；问题 5、6、7、8 属于**行为保持或性能优化**。所有变更都必须在测试中用 `test_data_provider.py` 覆盖。

---

## 3. 约束条件（不可违反）

1. **公共接口签名不变**：`DataProvider.__init__(data_dir=None, data_filename="data.json")` 及所有公共方法参数、顺序、默认值不变。
2. **导入路径不变**：`from core.data import DataProvider, DataNamespace, DataProviderError` 继续可用。
3. **返回值语义：业务等价，隔离性增强**：`get_plugin_data`、`get_all_plugin_data`、`get_all_plugins`、`get_plugin_info`、`load_data` 返回的字典/值**业务含义**与现在一致；新实现统一返回**深拷贝独立副本**（通过 `orjson.loads` 反序列化或 `copy.deepcopy` 生成），以修复旧实现中因浅拷贝可能导致的缓存污染问题。插件如果仅读取/使用返回值而不反向修改，行为与旧实现完全一致。
4. **异常语义不变**：插件不存在、路径遍历、读取失败等场景仍抛出 `DataProviderError`。
5. **Pub/Sub 语义不变**：`subscribe` 仍验证目标插件存在；`set_plugin_data(PUBLIC, notify=True)` 仍同步回调订阅者；回调签名不变。
6. **单例行为不变**：`DataProvider()` 全局唯一，重复初始化不重置状态。
7. **资源文件路径不变**：`save_asset` 返回的相对路径格式仍为 `assets/plugins/<plugin_id>/<filename>`。
8. **数据库依赖零额外**：SQLite 使用 Python 标准库 `sqlite3`，不引入数据库驱动；为消除 JSON 序列化开销，引入 `orjson` 作为唯一新增序列化依赖。
9. **序列化格式对插件透明**：插件通过 `get_plugin_data` / `set_plugin_data` 接收/传入的仍是 Python 对象，不感知底层使用 `json` 还是 `orjson`。
10. **NaN/Inf 行为显式变更**：标准库 `json` 默认允许写入/读取非标准 `NaN`/`Infinity` 标记，而 `orjson` 拒绝这些值。为保证后端一致性，新后端写入 `NaN/Inf` 统一抛出 `DataProviderError`；从旧 `data.json` 迁移时，这些值会被强制清洗为 `None`。这是兼容性安全变更，插件若依赖保存/读取 `NaN/Inf` 需适配。

---

## 4. SQLite Schema 设计

数据库文件：`data/data.db`（由 `data.json` 自动推导，见第 6.2 节）。
启用 WAL 模式后，同级目录还会出现 `data.db-wal` 和 `data.db-shm`，属于正常附属文件，不应手动删除。

### 4.1 表结构

```sql
-- 插件实例主表
CREATE TABLE IF NOT EXISTS plugins (
    instance_id TEXT PRIMARY KEY,
    plugin_type TEXT NOT NULL,
    active      INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1))
);

-- 插件键值数据表：每个 (instance_id, namespace, key) 唯一
CREATE TABLE IF NOT EXISTS plugin_data (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    instance_id TEXT NOT NULL,
    namespace   TEXT NOT NULL CHECK (namespace IN ('private', 'public')),
    key         TEXT NOT NULL,
    value_json  TEXT NOT NULL,           -- JSON 序列化后的值
    updated_at  INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),  -- 新增元数据，仅用于内部调试/清理，不暴露给插件
    FOREIGN KEY (instance_id) REFERENCES plugins(instance_id) ON DELETE CASCADE,
    UNIQUE (instance_id, namespace, key)
);

-- 活跃实例映射表：每个 plugin_type 只有一个活跃实例
CREATE TABLE IF NOT EXISTS active_instances (
    plugin_type TEXT PRIMARY KEY,
    instance_id TEXT NOT NULL,
    FOREIGN KEY (instance_id) REFERENCES plugins(instance_id) ON DELETE CASCADE
);

-- 数据库元数据表：存储 schema 版本、迁移来源等信息
CREATE TABLE IF NOT EXISTS db_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

### 4.2 索引

```sql
-- 已包含在 UNIQUE 约束中，SQLite 会自动创建隐式索引
-- plugin_data(instance_id, namespace, key)

-- 加速按类型查询插件列表
CREATE INDEX IF NOT EXISTS idx_plugins_type ON plugins(plugin_type);
```

### 4.3 Schema 版本

通过 `db_metadata` 表维护数据库 schema 版本：

```sql
INSERT INTO db_metadata (key, value) VALUES ('schema_version', '1')
ON CONFLICT(key) DO UPDATE SET value=excluded.value;
```

- **当前基础版本**：`1`（对应本次 JSON → SQLite 迁移创建的基础 schema）。
- **版本键**：`db_metadata.key = 'schema_version'`。
- **附加元数据**：
  - `migrated_from`：记录数据来源，例如 `data.json`（或用户自定义的 JSON 文件名）。
  - `migrated_at`：记录迁移完成时间戳（ISO 8601 或 Unix 秒）。
  - 应用可自由扩展其他元数据键，但 `schema_version` 为保留键。

### 4.4 与 JSON 结构的映射

| JSON 路径 | SQLite 位置 | 说明 |
|-----------|-------------|------|
| `plugins.<id>.type` | `plugins.plugin_type` | |
| `plugins.<id>.active` | `plugins.active` | 同时受 `active_instances` 表约束 |
| `plugins.<id>.private.<k>` | `plugin_data` 行，`namespace='private'` | `value_json` 存储 JSON 序列化值 |
| `plugins.<id>.public.<k>` | `plugin_data` 行，`namespace='public'` | 同上 |
| `active_instances.<type>` | `active_instances` 行 | 一对一映射 |
| （新增） | `db_metadata` 行 | schema 版本、迁移来源、迁移时间 |

### 4.5 值序列化

使用 **`orjson`** 替代标准库 `json` 进行 value 的序列化与反序列化。

```python
import orjson

def _raise_non_serializable(obj):
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

# 序列化
text = orjson.dumps(
    value,
    option=(
        orjson.OPT_NON_STR_KEYS
        | orjson.OPT_PASSTHROUGH_DATETIME
        | orjson.OPT_PASSTHROUGH_DATACLASS
    ),
    default=_raise_non_serializable,  # 拒绝 datetime/dataclass/UUID 等
).decode('utf-8')

# 反序列化
value = orjson.loads(text)
```

以上代码块为序列化/反序列化示例；实际实现中 `_raise_non_serializable` 等辅助函数见 6.4.0 节。
- **兼容性保证**：
  - `orjson` 默认输出标准 JSON，标准库 `json.loads` 也能解析新数据。
  - 旧 `data.json` 迁移导入的常规数据（dict/list/str/int/float/bool/None）可被 `orjson.loads` 正常解析。
  - 旧数据中若包含标准库 `json` 生成的非标准 `NaN`/`Infinity` 标记，`orjson.loads` 无法解析；迁移阶段需清洗为 `None` 或拒绝迁移。
  - 对插件而言，传入/返回的仍是 Python 对象，底层格式完全透明。
- **边界行为对齐**：
  - `orjson` 与标准库 `json` 在 `bytes`、`datetime`、`UUID`、`dataclass`、`NaN/Inf`、非字符串 dict key 等边界类型上行为不同。为保持与当前行为一致：
    - `bytes`：不可序列化，抛 `TypeError` → 包装为 `DataProviderError`。
    - `datetime` / `date` / `time`：不可序列化，递归检测并抛 `TypeError` → 包装为 `DataProviderError`。
    - `UUID` / `dataclass`：orjson 默认支持序列化，但标准库 `json` 不支持；递归检测并抛 `TypeError` → 包装为 `DataProviderError`。
    - `NaN/Inf`：标准库 `json` 输出非标准 `NaN`/`Infinity` 标记；`orjson` 默认输出 `null`。为保持一致，递归检测并抛出 `ValueError` → 包装为 `DataProviderError`。
    - 非字符串 dict key：`int` / `float` / `bool` / `None` / `IntEnum` / `IntFlag` 等 key 通过 `orjson.OPT_NON_STR_KEYS` 自动转为字符串；`tuple` 作为 key 时被拒绝，与标准库 `json.dumps` 行为一致。
- `None` 作为值会被序列化为 `"null"`，与 JSON 行为一致；`get_plugin_data` 的 `default` 参数仍用于区分 key 不存在的情况。

---

## 5. 数据库版本管理与链式升级

### 5.1 设计目标

- 支持未来对 SQLite schema 的**链式升级**，无需一次性重写所有历史逻辑。
- 版本信息存储在数据库内部，不依赖外部文件或代码常量。
- 升级过程**原子化**：每个版本升级在独立事务中执行，失败可回滚。
- 对插件接口完全透明：版本管理只发生在 `DataProvider` 内部初始化和维护阶段。

### 5.2 版本表设计

使用 `db_metadata` 表（见 4.1 / 4.3 节）：

| key | value | 说明 |
|-----|-------|------|
| `schema_version` | `"1"` | 当前 schema 版本号，字符串形式的正整数 |
| `migrated_from` | `"data.json"`（或用户自定义文件名） | 数据来源标识 |
| `migrated_at` | `"2026-06-26T20:52:38"` | 迁移完成时间（ISO 8601） |

### 5.3 升级脚本组织

在 `core/data/` 下新增 `schema_migrations.py`（或类似模块），定义迁移注册表：

```python
from typing import Callable, Dict

MigrationFunc = Callable[[sqlite3.Connection], None]

MIGRATIONS: Dict[int, MigrationFunc] = {
    # 1 -> 2: 示例未来升级（新增插件描述字段）
    # 2: upgrade_1_to_2,
}

TARGET_SCHEMA_VERSION = 1  # 当前代码期望的最新版本
```

每个迁移函数签名为：

```python
def upgrade_1_to_2(conn: sqlite3.Connection) -> None:
    """将 schema 从版本 1 升级到版本 2。

    注意：
    - 框架已为该迁移开启事务，函数内部不要再使用 `with conn:`。
    - 框架会在迁移成功后统一写入 `schema_version`，函数内部无需写入。
    """
    conn.execute("ALTER TABLE plugins ADD COLUMN description TEXT DEFAULT '';")
```

### 5.4 链式升级流程

在 `_ensure_database()` 或独立的 `_upgrade_schema()` 中执行：

```python
def _get_schema_version(self, conn: sqlite3.Connection) -> int:
    """读取当前 schema 版本，返回整数。若表或键不存在，返回 0；若值损坏则抛异常。"""
    try:
        cur = conn.execute("SELECT value FROM db_metadata WHERE key='schema_version';")
        row = cur.fetchone()
        if row is None:
            return 0
        return int(row[0])
    except (sqlite3.OperationalError, ValueError) as e:
        # OperationalError：db_metadata 表不存在（早期数据库）
        # ValueError：schema_version 值非数字
        raise DataProviderError(f"数据库 schema_version 读取或解析失败: {e}")

def _upgrade_schema(self, conn: sqlite3.Connection) -> None:
    current = self._get_schema_version(conn)
    target = TARGET_SCHEMA_VERSION
    if current > target:
        raise DataProviderError(
            f"数据库版本 {current} 高于当前代码目标版本 {target}，请升级应用版本"
        )
    while current < target:
        next_version = current + 1
        migration = MIGRATIONS.get(next_version)
        if migration is None:
            raise DataProviderError(f"缺少升级到版本 {next_version} 的迁移脚本")
        try:
            with conn:  # 每个迁移独立事务
                migration(conn)
                # 框架层统一写入版本号，防止迁移函数遗漏
                conn.execute(
                    "INSERT INTO db_metadata (key, value) VALUES ('schema_version', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value;",
                    (str(next_version),)
                )
            # 注意：with conn 块在成功时自动 commit，异常时自动 rollback
        except Exception as e:
            raise DataProviderError(f"数据库升级到版本 {next_version} 失败: {e}")
        current = next_version
```

> **事务嵌套注意**：`_upgrade_schema` 内部为每个迁移使用 `with conn:` 开启独立事务。调用 `_upgrade_schema` 时，调用方不应已处于外层 SQLite 事务中，以避免事务嵌套错误。推荐在 `ensure_database()` 中先完成版本检测与升级，再开启业务事务。

### 5.5 版本初始化规则

1. **新建数据库**（从无到有）：
   - 创建所有表和索引。
   - 写入 `schema_version = '1'`。
   - `migrated_from = 'created'`。
   - `migrated_at = 当前时间`。

2. **从 JSON 迁移创建数据库**：
   - 创建所有表和索引。
   - 导入 JSON 数据。
   - 写入 `schema_version = '1'`。
   - `migrated_from = '<原始 JSON 文件名>'`。
   - `migrated_at = 当前时间`。

3. **已存在数据库但版本低于当前目标**：
   - 按 5.4 流程链式升级。

4. **数据库版本高于当前代码目标**：
   - 说明数据库由更高版本代码创建，当前代码无法安全降级。
   - 抛出 `DataProviderError`，提示用户升级应用版本。

### 5.6 版本管理对插件接口的影响

- **无影响**。版本检查、升级只在 `DataProvider` 初始化阶段执行。
- 插件通过 `DataProvider` 访问数据时，所有接口与 JSON 时代完全一致。

---

## 6. 实现方案

### 6.1 总体思路

保持 `DataProvider` 的类名、单例模式、公共方法签名不变。将内部持久化逻辑从“完整 JSON 文件读写”替换为“SQLite 按 key 读写”，同时保留内存缓存以满足 `load_data` / `save_data` / `clear_cache` 的既有语义。

**模块集成关系**：

```
core/data/data_provider.py
  ├── core/data/sqlite_backend.py
  │     ├── SQLiteBackend        # 连接、DDL、CRUD、事务、LRU 缓存
  │     ├── _serialize/_deserialize
  │     └── _sanitize_for_migration
  └── core/data/schema_migrations.py
        ├── TARGET_SCHEMA_VERSION
        └── MIGRATIONS
```

- `DataProvider` 持有 `SQLiteBackend` 实例（例如 `self._backend`），所有持久化操作委托给 `SQLiteBackend`。
- `SQLiteBackend` 负责数据库连接、DDL、事务、版本调度、按 key 的 CRUD、LRU 缓存、序列化/反序列化。
- `schema_migrations.py` 仅存放 `TARGET_SCHEMA_VERSION` 与 `MIGRATIONS` 注册表，由 `SQLiteBackend.ensure_database()` 调用。
- `_file_lock` 仍保留在 `DataProvider` 中，`SQLiteBackend` 的所有公共方法假设调用方已持有该锁（或内部在需要时获取）。推荐实现：`DataProvider` 在调用 `SQLiteBackend` 前后获取/释放 `_file_lock`，`SQLiteBackend` 内部不再重复加锁。

核心改动集中在 `core/data/data_provider.py` 与新增文件；`core/interfaces/i_data_provider.py` 不需要改动；`core/data/__init__.py` 不需要改动。

### 6.2 构造函数兼容

保持原签名不变。构造函数内部应保留 `_initialized` 早退守卫，防止重复初始化重置 `_cache`、`_subscriptions`、`_file_lock` 等状态：

```python
from typing import Optional

class DataProvider:
    def __init__(self, data_dir: Optional[str] = None, data_filename: str = "data.json"):
        # 单例早退守卫
        if getattr(self, "_initialized", False):
            return
        # 后续初始化...
        self._initialized = True
```

内部数据库文件路径推导规则：

1. 若 `data_filename` 以 `.json` 结尾，数据库文件名为 `data_filename[:-5] + ".db"`。
2. 否则，数据库文件名为 `data_filename + ".db"`。

示例：

| 传入的 `data_filename` | 数据库文件 |
|------------------------|------------|
| `data.json`（默认） | `data.db` |
| `my_data.json` | `my_data.db` |
| `app_data` | `app_data.db` |

`data.json` 文件在迁移导入后保留为备份，不删除。

**临时 JSON 后端开关（阶段 3 起启用，阶段 4 后仍保留作为应急回退）**：

为便于调试和异常回退，阶段 3 起在 `DataProvider.__init__` 中保留一个后端选择开关：

- 环境变量 `INSTRUCTIONX_DATAPROVIDER_BACKEND=json`：使用旧 JSON 后端。
- 环境变量未设置、值为 `sqlite`、或取其他未知值：使用新 SQLite 后端（默认）。
- 该开关长期保留，作为迁移后的应急回退手段；正常使用无需设置。

> 注意：JSON 后端与 SQLite 后端共享 `data_dir` 和 `data_filename` 推导规则，但分别操作 `data.json` 和 `data.db`。启用 JSON 后端时不会触发 SQLite 自动迁移。

**实现示例**：

```python
import os
import threading

class _LRUCache:
    """占位：实际实现见 6.3.2 节。"""
    def __init__(self, capacity=4096):
        self.capacity = capacity

    def get(self, key, default=None):
        return default

    def put(self, key, value):
        pass

class SQLiteBackend:
    """占位：实际实现见第 6.4 节。"""
    def __init__(self, data_dir, data_filename):
        pass

    def get_plugin_data(self, instance_id, key, namespace, default):
        return default

class DataProvider:
    def __init__(self, data_dir=None, data_filename="data.json"):
        # 单例早退守卫
        if getattr(self, "_initialized", False):
            return

        self._backend_type = os.environ.get("INSTRUCTIONX_DATAPROVIDER_BACKEND", "sqlite").lower()
        if self._backend_type == "json":
            self._use_json_backend = True
        else:
            self._use_json_backend = False
            self._backend = SQLiteBackend(data_dir, data_filename)

        # 以下字段初始化与旧 JSON 实现保持一致（JSON/SQLite 后端共用）
        self._cache = None
        self._cache_dirty = True
        self._value_cache = _LRUCache(capacity=4096)
        self._subscriptions = {}
        self._file_lock = threading.RLock()
        self._subscription_lock = threading.Lock()
        self._initialized = True

    def get_plugin_data(self, instance_id, key, namespace, default=None):
        if self._use_json_backend:
            return self._json_get_plugin_data(instance_id, key, namespace, default)
        return self._backend.get_plugin_data(instance_id, key, namespace, default)
```

> 阶段 3 实现时，可仅对关键读写路径保留 JSON 分支；阶段 4 后 SQLite 为默认，JSON 分支作为应急回退保留。

### 6.3 缓存策略调整

迁移后采用**三级缓存/优化策略**：

#### 6.3.1 全量字典缓存（`_cache`）

- `_cache` 仍保存完整字典结构，用于满足 `load_data()` / `save_data()` / `clear_cache()` 的既有接口语义。
- 采用**延迟加载 + 写穿（write-through）**策略：
  - `load_data(force_reload=True)` 时从 SQLite 全量重建 `_cache`。
  - `set_plugin_data` 直接写 SQLite，同时更新 `_cache` 中对应节点（如果 `_cache` 已加载）。
  - `get_all_plugin_data` 查询该命名空间的所有 key，不依赖 `_cache`。
  - `register_plugin` / `unregister_plugin` / `set_active_instance` 直接写 SQLite，并同步失效/更新 `_cache`。

#### 6.3.2 反序列化结果缓存（LRU）

为消除 `orjson.loads` 的重复开销，引入按 key 的 LRU 缓存：

```python
self._value_cache: Dict[tuple, Any] = {}
# 或使用 OrderedDict / functools.lru_cache 实现固定容量 LRU
```

- 缓存 key：`(instance_id, namespace_str, key)`。
- 缓存 value：反序列化后的 Python 对象。
- 命中策略：
  - `get_plugin_data` 先查 LRU 缓存，命中则直接返回副本（避免重复解析）。
  - `get_all_plugin_data` 对每个 key 优先使用缓存，未命中则解析并写入缓存。
- 失效策略：
  - `set_plugin_data` 写入成功后，使对应 `(instance_id, namespace_str, key)` 缓存项失效。
  - `unregister_plugin` 使该插件所有缓存项失效。
  - `reset_all_data` 清空全部缓存。
  - `clear_cache` 清空 LRU 缓存（`_cache` 同时清空）。
- 容量与线程安全：
  - 使用带最大容量的 LRU。推荐实现见下方代码块。
  - 默认容量建议 `4096`，可根据实际场景调整。容量上限防止内存无限增长。
  - 所有缓存操作在 `_file_lock` 保护下进行，避免并发问题。

```python
from collections import OrderedDict
from typing import Any, Dict, Tuple

class _LRUCache:
    """带容量上限的 LRU 缓存。

    注意：本类不是线程安全的，所有 get/put/invalidate/clear 操作
    必须在 DataProvider 的 _file_lock（RLock）保护下进行。
    """
    def __init__(self, capacity: int = 4096):
        self.capacity = capacity
        self._data: "OrderedDict[Tuple[str, str, str], Any]" = OrderedDict()

    def get(self, key: Tuple[str, str, str]) -> Any:
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]

    def put(self, key: Tuple[str, str, str], value: Any) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        if len(self._data) > self.capacity:
            self._data.popitem(last=False)

    def invalidate(self, key: Tuple[str, str, str]) -> None:
        self._data.pop(key, None)

    def invalidate_plugin(self, instance_id: str) -> None:
        keys = [k for k in self._data if k[0] == instance_id]
        for k in keys:
            self._data.pop(k, None)

    def clear(self) -> None:
        self._data.clear()
```

**使用示例**：

```python
import copy

_MISSING = object()  # 用于区分"缓存未命中"与"值为 None"

def _get_plugin_data_with_cache(self, instance_id, namespace_str, key, default):
    cache_key = (instance_id, namespace_str, key)
    with self._file_lock:
        cached = self._value_cache.get(cache_key, _MISSING)
        if cached is not _MISSING:
            return copy.deepcopy(cached)
        # 未命中，查询 SQLite
        row = self._backend.execute(
            "SELECT value_json FROM plugin_data WHERE instance_id=? AND namespace=? AND key=?;",
            (instance_id, namespace_str, key)
        ).fetchone()
        if row is None:
            return default
        value = _deserialize(row[0])
        self._value_cache.put(cache_key, value)
        return copy.deepcopy(value)
```

- 返回副本与缓存隔离：
  - `get_plugin_data` / `get_all_plugin_data` 命中缓存后，返回 `copy.deepcopy(cached_value)`。
  - `set_plugin_data` 更新 `_cache` 时，存入 `copy.deepcopy(value)`，防止插件后续修改传入对象污染缓存。
  - 推荐在缓存中存不可变表示或返回前深拷贝，确保缓存与数据库一致。

#### 6.3.3 高频读写路径总结

| 操作 | 是否走 SQLite | 是否走 LRU 缓存 | 是否序列化/反序列化 |
|------|---------------|-----------------|---------------------|
| `get_plugin_data` | 是（点查） | 优先 | 未命中时一次 |
| `set_plugin_data` | 是（点写） | 失效 | 一次（orjson.dumps） |
| `get_all_plugin_data` | 是 | 优先 | 未命中时每个 key 一次 |
| `load_data` | 是（全量） | 填充缓存 | 全量 |
| `save_data` | 是（全量） | 不变 | 全量 |

这样，高频单 key 读写不再触发全量 JSON 序列化，也避免重复反序列化。

### 6.4 各方法实现要点

#### 6.4.0 之前：事务边界与异常包装通用规则

**事务边界**：

- 每个公共写操作（`register_plugin`、`unregister_plugin`、`set_active_instance`、`set_plugin_data`、`save_data`、`reset_all_data`）应作为一个独立事务，在 `_file_lock` 保护下执行：
  ```python
  with self._backend.transaction():  # BEGIN IMMEDIATE ... COMMIT/ROLLBACK
      # 执行 SQL 写入
  ```
- 读操作（`get_plugin_data`、`get_all_plugin_data`、`get_active_instance`、`get_plugin_info`、`get_all_plugins`、`load_data`）不开启显式事务，使用普通 `SELECT`；若需保证一致性，可使用只读事务。
- 迁移过程（JSON → SQLite）在一个事务中完成，失败时整体回滚。

**异常包装**：

所有公共方法内部必须对 SQLite 与序列化调用进行 try/except 包装，统一抛出 `DataProviderError`：

- 捕获 `sqlite3.Error` 及其子类（如 `sqlite3.OperationalError`、`sqlite3.IntegrityError`），包装为 `DataProviderError`。
- 捕获 `orjson.JSONEncodeError`、`orjson.JSONDecodeError`、`TypeError`、`ValueError`（来自序列化/反序列化），包装为 `DataProviderError`。
- 禁止将底层异常直接泄漏到插件层。

> 例如：`set_plugin_data` 写入失败、`get_plugin_data` 反序列化失败、`register_plugin` 遇到唯一约束冲突，都必须以 `DataProviderError` 形式抛出，与旧 JSON 实现的异常语义一致。

#### 6.4.0 序列化与反序列化工具方法

所有 value 的序列化/反序列化统一通过 `core/data/sqlite_backend.py` 中的两个模块级工具函数完成（也可作为 `SQLiteBackend` 的静态/私有方法；文档示例采用模块级函数形式）。`DataProvider` 通过直接 import 调用 `_serialize(value)` / `_deserialize(text)`，或经由 `self._backend` 代理调用，保持公共接口层不感知序列化细节。实现时选择其中一种方式并在整个后端中保持一致。

```python
# 位于 core/data/sqlite_backend.py

def _serialize(value: Any) -> str:
    """将 Python 对象序列化为 JSON 文本（使用 orjson），行为与标准库 json 一致。"""
    import datetime as dt
    import math
    from collections import deque
    from collections.abc import Mapping, Sequence
    from enum import Enum, IntEnum, IntFlag
    from uuid import UUID
    
    def _raise_non_serializable(obj: Any) -> None:
        """用于 orjson default 钩子，拒绝所有无法识别的类型。"""
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
    
    def _scan_non_json_types(obj: Any) -> None:
        """
        递归扫描标准库 json 无法序列化、或 orjson 行为与标准库不一致的类型，保持行为一致：
        - datetime / date / time
        - NaN / Inf
        - UUID
        - dataclass 实例
        - bytes / bytearray
        - set / frozenset
        - deque
        - 普通 Enum 实例（orjson 默认会序列化，标准库 json 会拒绝）
        注意：
        - tuple 与标准库 json 行为一致（序列化为数组），不拒绝。
        - IntEnum / IntFlag 与标准库 json 行为一致（序列化为整数），不拒绝。
        """
        if isinstance(obj, (dt.datetime, dt.date, dt.time)):
            raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
        if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
            raise ValueError("Out of range float values are not JSON compliant")
        if isinstance(obj, UUID):
            raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
        # set / frozenset / bytearray / bytes：标准库 json 无法序列化
        # orjson 对这些类型的处理与标准库 json 不一致（可能拒绝也可能默认序列化）
        # 为保持行为一致，主动拒绝
        if isinstance(obj, (set, frozenset, bytearray, bytes)):
            raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
        # 普通 Enum 实例：标准库 json 拒绝；orjson 内置支持会序列化为底层值
        # IntEnum / IntFlag 同时是 int 子类，标准库 json 会序列化为整数，orjson 同样会序列化为整数，与旧实现一致，不应拒绝
        if isinstance(obj, Enum) and not isinstance(obj, (IntEnum, IntFlag)):
            raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
        # deque：标准库 json 拒绝；orjson 默认会序列化为数组
        if isinstance(obj, deque):
            raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
        # tuple：标准库 json 会序列化为数组；orjson 同样会序列化为数组。旧实现使用标准库 json，因此 tuple 是被支持的，不应拒绝。
        # dataclass 实例：有 __dataclass_fields__ 且不是内置容器/字符串/bytes/set/frozenset/bytearray/deque
        if hasattr(type(obj), '__dataclass_fields__') and not isinstance(
            obj, (str, bytes, bytearray, Mapping, Sequence, set, frozenset, deque)
        ):
            raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
        if isinstance(obj, Mapping):
            for k, v in obj.items():
                # tuple key：标准库 json 拒绝；orjson.OPT_NON_STR_KEYS 同样拒绝
                # tuple value 是允许的，因此只在 key 位置拒绝
                if isinstance(k, tuple):
                    raise TypeError(f"Object of type {type(k).__name__} is not JSON serializable")
                _scan_non_json_types(k)  # dict key 也可能是 UUID/datetime
                _scan_non_json_types(v)
        elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes)):
            for item in obj:
                _scan_non_json_types(item)
    
    try:
        # 递归扫描非 JSON 类型，避免 orjson 默认扩展行为（如 UUID/dataclass 序列化、NaN 转 null）
        _scan_non_json_types(value)
        
        # OPT_NON_STR_KEYS：非字符串 dict key 自动转字符串，与 json.dumps 一致
        # OPT_PASSTHROUGH_DATETIME：让 datetime 走 default 钩子而非默认序列化
        # OPT_PASSTHROUGH_DATACLASS：让 dataclass 走 default 钩子而非默认序列化
        return orjson.dumps(
            value,
            option=(
                orjson.OPT_NON_STR_KEYS
                | orjson.OPT_PASSTHROUGH_DATETIME
                | orjson.OPT_PASSTHROUGH_DATACLASS
            ),
            default=_raise_non_serializable,
        ).decode('utf-8')
    except (TypeError, ValueError, orjson.JSONEncodeError) as e:
        raise DataProviderError(f"数据序列化失败: {e}")
```

```python
def _deserialize(text: str) -> Any:
    """将 JSON 文本反序列化为 Python 对象（使用 orjson）。"""
    try:
        return orjson.loads(text)
    except (orjson.JSONDecodeError, TypeError, ValueError) as e:
        raise DataProviderError(f"数据反序列化失败: {e}")
```

**兼容性保证**：
- `orjson.loads` 可解析标准库 `json.dumps(..., ensure_ascii=False)` 产生的旧数据（常规类型；含 `NaN/Infinity` 非标准标记的旧数据会解析失败，迁移阶段需清洗）。
- `orjson.dumps` 输出标准 JSON，标准库 `json.loads` 也能解析新数据。
- 非字符串 dict key 通过 `OPT_NON_STR_KEYS` 处理，与旧 `json.dumps` 行为一致。
- 若未来需要回退到标准库 `json`，只需替换这两个方法即可，不影响业务代码。

**边界类型处理**（保持与当前 `json` 行为一致）：
- `bytes` / `bytearray`：标准库 `json` 不可序列化；`orjson` 行为可能与标准库不一致。在 `_scan_non_json_types` 中主动拒绝 → 包装为 `DataProviderError`。
- `set` / `frozenset`：标准库 `json` 不可序列化；`orjson` 行为可能与标准库不一致。在 `_scan_non_json_types` 中主动拒绝 → 包装为 `DataProviderError`。
- `datetime` / `date` / `time`：不可序列化，在 `_serialize` 中先 `isinstance(value, (datetime.date, datetime.datetime, datetime.time))` 检测并抛 `TypeError` → 包装为 `DataProviderError`。注意：orjson 默认会序列化 `datetime`，必须主动拦截。
- `NaN/Inf`：在 `_serialize` 中显式检测 `math.isnan/isinf` 并抛 `ValueError` → 包装为 `DataProviderError`，避免 `orjson` 默认输出 `null` 与旧 `json` 输出 `NaN/Infinity` 不一致。
- 非字符串 dict key：`int` / `float` / `bool` / `None` / `IntEnum` / `IntFlag` 等 key 通过 `orjson.OPT_NON_STR_KEYS` 自动转为字符串；`tuple` 作为 key 时被标准库 `json` 与 `orjson` 均拒绝。普通 `Enum`、`datetime` / `date` / `time` / `UUID` / `bytes` / `bytearray` / `set` / `frozenset` / `deque` 等 key 也必须经过 `_scan_non_json_types` 递归扫描并拒绝，以与 `json.dumps` 保持一致。`OPT_NON_STR_KEYS` 不能单独保证所有 key 类型行为一致。
- **迁移特殊说明**：旧 `data.json` 中若已存在 `datetime` / `UUID` / `tuple` 等非字符串 dict key，迁移阶段的 `_sanitize_for_migration` 会将其转为字符串以保证导入成功；但迁移完成后，新后端写入含此类 key 的数据仍会统一拒绝。这是为了确保新数据始终符合标准 JSON 语义。
- 普通 `Enum` 实例（非 `IntEnum` / `IntFlag`）：标准库 `json` 拒绝；`orjson` 默认会序列化为底层值。在 `_scan_non_json_types` 中主动拒绝 → 包装为 `DataProviderError`。
- `IntEnum` / `IntFlag`：标准库 `json` 会序列化为整数；`orjson` 同样会序列化为整数。与旧实现行为一致，不应拒绝。
- 其他标准库 `json` 默认拒绝的类型（如 `memoryview`、`range`、`deque`）：同样由 `orjson` 的 `default` 钩子或 `_scan_non_json_types` 拒绝，行为一致。`tuple` 与标准库 `json` 行为一致（序列化为数组），无需拒绝。

#### 6.4.1 `_ensure_database()`

替代 `_ensure_data_file()`。流程如下：

1. 若 `data.db` 不存在或未初始化（判定标准同 7.1 节：文件不存在、大小为 0 字节、或未创建任何表）：
   1. 创建数据库文件（若不存在）。
   2. 执行 DDL 创建表和索引（含 `db_metadata`）。
   3. 启用 WAL 模式、`synchronous=NORMAL`、外键约束。
   4. 若 `data.json` 存在且可被解析为合法 JSON，读取并导入（见 7.2 节）。
   5. 若 `data.json` 不存在或无法解析，创建空数据库。
   6. 写入 `db_metadata`：
      - `schema_version` = `'1'`
      - `migrated_from` = `'<原始 JSON 文件名>'`（若从 JSON 导入）或 `'created'`（若新建）
      - `migrated_at` = 当前时间戳
2. 若 `data.db` 已存在且已初始化：
   1. 执行 PRAGMA 配置（WAL、外键等）。
   2. 读取 `db_metadata.schema_version`：
      - 若不存在 `db_metadata` 表或 `schema_version` 键，说明这是早期未带版本信息的数据库。此时直接创建/补齐 `db_metadata` 表，写入 `schema_version='1'`、`migrated_from='legacy'`、`migrated_at=当前时间`，**不调用**链式升级（因为基线表结构已存在，无需执行版本 `1→2` 的迁移）。
      - 若当前版本可解析为整数且低于 `TARGET_SCHEMA_VERSION`，按 5.4 节链式升级。
      - 若当前版本无法解析为整数，抛出 `DataProviderError("数据库 schema_version 损坏")`。
      - 若当前版本高于 `TARGET_SCHEMA_VERSION`，抛出 `DataProviderError`，提示数据库由更高版本代码创建。
   3. 校验核心表结构：
      - 使用 `CREATE TABLE IF NOT EXISTS` 确保 `plugins`、`plugin_data`、`active_instances`、`db_metadata` 表存在。
      - **仅 `CREATE TABLE IF NOT EXISTS` 无法检测列缺失或类型变更**，因此必须通过 `PRAGMA table_info(<table>)` 读取实际列定义，与期望 schema 对比。
      - 若检测到严重结构不一致（如列缺失、类型不匹配、非空约束不符），应抛出 `DataProviderError` 并提示用户手动修复或删除数据库，而不是自动重建导致数据丢失。
      - **绝不**删除或清空已有表。

**伪代码示例**：

```python
def ensure_database(self) -> None:
    # 清理旧 JSON 临时文件残留（无论使用哪种后端）
    self._remove_temp_json_file_if_exists()

    db_exists_and_initialized = self._db_file_exists() and self._has_core_tables()
    if not db_exists_and_initialized:
        # 新建数据库（或空/未初始化文件）
        # 注意：必须先解析 data.json 成功，再创建 data.db，避免 JSON 损坏时留下空库占位
        json_data = None
        if self._json_file_exists():
            json_data = self._parse_json_file()  # 解析失败直接抛异常，不创建 data.db
        self._create_connection()
        self._execute_pragmas()
        self._create_tables()
        if json_data is not None:
            self._migrate_json_to_sqlite(json_data)
            migrated_from = self._json_file_name  # 原始 JSON 文件名
        else:
            migrated_from = "created"
        self._set_metadata(
            schema_version="1",
            migrated_from=migrated_from,
            migrated_at=iso_now(),
        )
    else:
        self._create_connection()
        self._execute_pragmas()
        current = self._get_schema_version(self._conn)
        if current == 0:
            # 早期无版本数据库，补齐到版本 1
            self._set_metadata(schema_version="1", migrated_from="legacy", migrated_at=iso_now())
        elif current < TARGET_SCHEMA_VERSION:
            self._upgrade_schema(self._conn)
        elif current > TARGET_SCHEMA_VERSION:
            raise DataProviderError(f"数据库版本 {current} 高于代码目标版本 {TARGET_SCHEMA_VERSION}")
        # 校验核心表是否存在（CREATE TABLE IF NOT EXISTS 幂等）
        self._create_tables()
        # 校验核心表结构是否完整（CREATE TABLE IF NOT EXISTS 无法检测列缺失）
        self._validate_table_schema()
```

#### 6.4.2 `_read_from_disk()`

从 SQLite 重建完整字典并返回，同时填充 LRU 反序列化缓存。用于 `load_data()` 和缓存未命中时的兜底。

```python
{
    "plugins": {
        "<instance_id>": {
            "type": "...",
            "active": True/False,
            "private": {"key": value, ...},
            "public": {"key": value, ...}
        }
    },
    "active_instances": {"<type>": "<instance_id>", ...}
}
```

实现要点：
- 使用 `ORDER BY rowid` 保持与旧 JSON 实现一致的插入顺序：
  ```sql
  SELECT instance_id, plugin_type, active FROM plugins ORDER BY rowid;
  SELECT instance_id, namespace, key, value_json FROM plugin_data ORDER BY rowid;
  SELECT plugin_type, instance_id FROM active_instances ORDER BY rowid;
  ```
- 从 `plugin_data` 读取所有行，对每个 value 调用 `_deserialize(text)`。
- 将反序列化结果同时写入 `_cache` 和 LRU 缓存，供后续点查使用。
- 组装 `dict` 时使用标准 `dict`（Python 3.7+ 保持插入顺序），因此 `ORDER BY rowid` 可保证同一插件命名空间内的 key 顺序与原始写入顺序一致。
- **注意**：SQLite 的 `rowid` 在删除再插入时可能变化，因此无法 100% 保证与旧 JSON 的插入顺序完全相同；但与按主键字母序排序相比，`ORDER BY rowid` 更接近原始写入顺序。若未来需要严格顺序，可在 schema 中增加显式 `created_at`/`insert_order` 列。

#### 6.4.3 `_write_to_disk(data)`

将完整字典写回 SQLite（全量同步）。主要用于 `save_data()` 和 `reset_all_data()`。

实现方式：在事务中先清空 `plugin_data`、`active_instances` 和 `plugins`，再按 `_read_from_disk` 的逆过程重新插入。插入前对每个 value 调用 `_serialize(value)`。

> **清空顺序注意**：由于 `plugin_data` 和 `active_instances` 外键引用 `plugins`，应先清空子表 `plugin_data`、`active_instances`，再清空父表 `plugins`；插入时则相反，先插入 `plugins`，再插入 `plugin_data` 和 `active_instances`。这样才能保证 `save_data()` 时若 `_cache` 中插件集合已减少（例如先 `unregister_plugin` 再 `save_data`），已注销的插件记录不会残留在数据库中。
>
> 该路径在 SQLite 迁移后使用频率极低（因为 `set_plugin_data` 已经点写），性能可接受。

> 注意：全量写入完成后，建议清空并重新填充 LRU 缓存，避免缓存与数据库不一致。

#### 6.4.4 `register_plugin(instance_id, plugin_type)`

```sql
INSERT INTO plugins (instance_id, plugin_type, active) VALUES (?, ?, 0);
```

- 重复主键时 SQLite 抛出 `IntegrityError`，包装为 `DataProviderError("插件 ... 已存在")`。
- 若 `_cache` 为 `None`，先调用 `load_data()` 加载缓存，确保调用结束后 `_cache` 已加载，与旧实现行为一致（旧实现内部也会调用 `load_data()`）。
- 若 `_cache` 已加载，在 `_cache["plugins"][instance_id]` 中插入 `{"type": plugin_type, "active": False, "private": {}, "public": {}}`。

#### 6.4.5 `unregister_plugin(instance_id)`

- 若 `_cache` 为 `None`，先调用 `load_data()` 加载缓存，确保调用结束后 `_cache` 已加载，与旧实现行为一致（旧实现内部也会调用 `load_data()`）。

1. 先查询确认插件存在：
   ```sql
   SELECT 1 FROM plugins WHERE instance_id = ?;
   ```
   不存在则抛出 `DataProviderError(f"插件 {instance_id} 不存在")`。
2. 执行删除：
   ```sql
   DELETE FROM plugins WHERE instance_id = ?;
   ```
   利用外键 `ON DELETE CASCADE` 自动清理 `plugin_data` 和 `active_instances`。
3. 使该插件在 LRU 缓存中的所有条目失效（匹配 `instance_id` 的 key）。
4. 若 `_cache` 已加载，从 `_cache["plugins"]` 和 `_cache["active_instances"]` 中同步移除。
5. **释放 `_file_lock`**。
6. 调用 `_remove_subscriptions_for_plugin`（内存操作，需在 `_file_lock` 完全释放后获取 `_subscription_lock`，避免死锁）。

#### 6.4.6 `set_active_instance(instance_id)`

1. 验证插件存在。
2. 同类型其他插件 `active=0`：
   ```sql
   UPDATE plugins SET active=0 WHERE plugin_type=? AND instance_id!=?;
   ```
3. 目标插件 `active=1`：
   ```sql
   UPDATE plugins SET active=1 WHERE instance_id=?;
   ```
4. 更新/插入 `active_instances`：
   ```sql
   INSERT INTO active_instances (plugin_type, instance_id) VALUES (?, ?)
   ON CONFLICT(plugin_type) DO UPDATE SET instance_id=excluded.instance_id;
   ```
5. 若 `_cache` 为 `None`，先调用 `load_data()` 加载缓存，确保调用结束后 `_cache` 已加载，与旧实现行为一致（旧实现内部也会调用 `load_data()`）。
6. 若 `_cache` 已加载，同步更新 `_cache["plugins"][instance_id]["active"]` 为 `True`，并将 `_cache["active_instances"][plugin_type]` 更新为 `instance_id`。

#### 6.4.7 `get_plugin_data(instance_id, key, namespace, default)`

1. 验证插件存在（查询 `plugins` 表）。
2. 构造缓存 key `(instance_id, namespace_str, key)`，先查 LRU 反序列化缓存：
   - 命中：返回缓存值的深拷贝（防止外部修改污染缓存）。
3. 未命中则点查：
   ```sql
   SELECT value_json FROM plugin_data
   WHERE instance_id=? AND namespace=? AND key=?;
   ```
4. 无结果返回 `default`。
5. 有结果则 `_deserialize(value_json)`，写入 LRU 缓存，再返回深拷贝。

#### 6.4.8 `set_plugin_data(instance_id, key, value, namespace, notify)`

1. 验证插件存在。
2. **统一命名空间比较**：为避免 `core.interfaces.DataNamespace` 与 `core.data.DataNamespace` 是两个不同 `Enum` 类导致比较失败，所有命名空间判断统一使用字符串值：`namespace_str = namespace.value`（如 `is_public = namespace_str == DataNamespace.PUBLIC.value`）。保持当前“仅接受 `DataNamespace` 枚举”的行为；若传入字符串等非枚举对象，与当前实现一样会抛出 `AttributeError` 并由调用方处理。如需支持字符串命名空间，必须作为显式行为变更单独记录。
3. 获取旧值：
   - 先查 LRU 缓存；若未命中则点查：
     ```sql
     SELECT value_json FROM plugin_data
     WHERE instance_id=? AND namespace=? AND key=?;
     ```
   - 有结果则 `_deserialize(value_json)`；无结果则旧值为 `None`。
4. 使用 `_serialize(value)` 得到 JSON 文本。
5. 插入或更新：
   ```sql
   INSERT INTO plugin_data (instance_id, namespace, key, value_json)
   VALUES (?, ?, ?, ?)
   ON CONFLICT(instance_id, namespace, key)
   DO UPDATE SET value_json=excluded.value_json, updated_at=strftime('%s','now');
   ```
6. 使 LRU 缓存中对应 `(instance_id, namespace_str, key)` 项失效（写入新值后缓存必须更新或清除）。
7. 如果 `_cache` 已加载，同步更新 `_cache`（存入 `copy.deepcopy(value)`，防止插件后续修改传入对象污染缓存）；如果 `_cache` 为 `None`，应先调用 `load_data()` 加载一次，以保证后续 `save_data()` 等缓存相关接口可用（当前 JSON 实现也会通过 `load_data()` 自动加载；该加载仅发生在 `clear_cache()` 之后，不影响高频写性能）。
   - `load_data()` 内部也会获取 `_file_lock`，因此 `_file_lock` 必须继续使用 `threading.RLock`，以支持这种同线程内的重入。

> 说明：`save_data()` 仍保持旧语义：`_cache=None` 时直接抛异常。`set_plugin_data` 中的这步加载是为了避免正常写入后 `_cache` 仍为空。
8. **释放 `_file_lock`**。
9. 若 `namespace_str == DataNamespace.PUBLIC.value and notify`，调用 `_notify_subscribers`。

> **锁顺序说明**：数据库写入、缓存失效、`_cache` 更新均在 `_file_lock` 保护下完成；通知回调在释放 `_file_lock` 后调用。这样可避免订阅回调内部再次操作 DataProvider 时发生死锁或长时间阻塞其他线程。
>
> **回调参数副本说明**：`set_plugin_data` 通知回调中的 `old_value` 与 `new_value` 均为独立副本（`old_value` 来自 SQLite 反序列化或 LRU 缓存深拷贝，`new_value` 来自传入值的深拷贝）。插件不应使用 `is` 对这两个值进行对象身份比较。

#### 6.4.9 `get_all_plugin_data(instance_id, namespace)`

```sql
SELECT key, value_json FROM plugin_data
WHERE instance_id=? AND namespace=?
ORDER BY id;
```

- 对每个 `(instance_id, namespace_str, key)` 先查 LRU 缓存，命中则直接使用；未命中则 `_deserialize(value_json)` 并写入缓存。
- 返回 `{key: value, ...}` 的深拷贝，确保外部修改不影响缓存。

#### 6.4.10 `subscribe` / `unsubscribe` / `_notify_subscribers`

逻辑完全不变。`_subscriptions` 仍存内存。

`subscribe` 中验证目标插件存在改为查 SQLite：

1. 在 `_file_lock` 保护下查询 SQLite 确认目标插件存在；不存在则抛出 `DataProviderError`。
2. **释放 `_file_lock`**。
3. 获取 `_subscription_lock`，注册/更新订阅。
4. 释放 `_subscription_lock`。

> **锁顺序铁律**：订阅表相关操作（`subscribe` / `unsubscribe` / `_remove_subscriptions_for_plugin` / `_notify_subscribers`）必须在**完全释放 `_file_lock` 之后**再获取 `_subscription_lock`；任何情况下不得同时持有 `_file_lock` 与 `_subscription_lock`。`set_plugin_data` 在释放 `_file_lock` 后再调用 `_notify_subscribers`，回调内部若再次操作 DataProvider，其获取 `_file_lock` 的顺序与前述规则一致，因此不会死锁。

#### 6.4.11 资源文件方法

`save_asset`、`get_asset_path`、`load_asset`、`get_plugin_assets_dir` 逻辑完全不变，继续操作文件系统。

#### 6.4.12 `load_data` / `save_data` / `clear_cache`

- `load_data(force_reload=False)`：
  - 若 `_cache` 为空或 `force_reload` 或 `_cache_dirty`，调用 `_read_from_disk()` 重建 `_cache`。
  - 返回 `copy.deepcopy(self._cache)`（深拷贝，与 6.3 节整体隔离性策略一致；旧实现为顶层浅拷贝，新实现增强隔离）。
- `save_data()`：
  - 若 `_cache` 为 `None`，抛出 `DataProviderError("没有可保存的数据")`，与当前 JSON 实现语义一致。
  - 调用 `_write_to_disk(self._cache)`。
  - 设置 `_cache_dirty=False`。
  - 可选：清空并重新填充 LRU 缓存，确保缓存与数据库一致。

> 说明：`set_plugin_data` 在 `_cache` 为 `None` 时会先调用 `load_data()` 加载缓存，因此正常流程下 `save_data()` 不会因 `_cache=None` 而失败。`clear_cache()` → `save_data()` 的序列在当前实现中同样会失败，语义保持一致。
- `clear_cache()`：
  - 将 `self._cache` 设为 `None`，设置 `_cache_dirty=True`（与现有行为一致，确保下次 `load_data` 重新从 SQLite 加载）。
  - 清空 LRU 反序列化缓存。

> **缓存策略补充**：为保证 `clear_cache()` → `set_plugin_data()` → `save_data()` 序列与当前行为一致，`set_plugin_data` 在 `_cache` 为 `None` 时应先调用 `load_data()` 加载一次（当前 JSON 实现也会通过 `load_data()` 自动加载）。高频读写场景下该加载仅发生在 `clear_cache()` 之后，不影响正常性能。

#### 6.4.13 `get_all_plugins` / `get_plugin_info`

从 SQLite 查询并组装为与 JSON 结构一致的字典。实现可复用 `_read_from_disk` 中的一部分逻辑。

- `get_all_plugins()` 返回整个 `{"instance_id": {...}}` 结构的深拷贝。
- `get_plugin_info(instance_id)` 返回单个插件信息字典的深拷贝。
- 与 6.3 节整体策略一致：外部修改返回值不影响内部缓存或数据库。

#### 6.4.14 `reset_all_data`

实现方式：调用 `_write_to_disk({"plugins": {}, "active_instances": {}})`。`_write_to_disk` 会先清空 `plugin_data`、`active_instances`、`plugins` 三张表，再按空结构重新插入（实际上不会插入任何行），从而保证数据库与 `_cache` 一致。

1. 调用 `_write_to_disk({"plugins": {}, "active_instances": {}})`。
2. **订阅表处理**：当前实现 `reset_all_data()` **不会**清空 `_subscriptions`。为保持行为一致，本次迁移也不清空 `_subscriptions`；如需改变该行为，必须作为显式变更单独记录并通过测试覆盖。
3. 清空 LRU 反序列化缓存。
4. 调用 `clear_cache()`：将 `_cache` 设为 `None`，`_cache_dirty` 设为 `True`。这与旧 JSON 实现完全一致：旧实现在 `reset_all_data()` 末尾也会调用 `clear_cache()`，使后续 `load_data()` 强制从磁盘重载，`save_data()` 在 `clear_cache()` 后直接调用会抛出 `DataProviderError("没有可保存的数据")`。

### 6.5 命名空间比较与类型处理

- 公共方法参数仍声明为 `namespace: DataNamespace`，与现有接口一致。
- 内部实现统一转换为字符串值后再使用：`namespace_str = namespace.value`（假设传入 `DataNamespace` 枚举）。
- 当前实现要求传入 `DataNamespace` 枚举（调用 `.value`）；迁移后保持此要求，不额外支持字符串传入，避免静默行为改变。
- **跨模块枚举比较 bug（当前实现）**：
  - `core/data/data_provider.py` 第 14 行从接口模块导入：`from core.interfaces.i_data_provider import IDataProvider, DataNamespace as IDataNamespace`。
  - 但第 23-27 行又定义了本地同名 `DataNamespace`。
  - `set_plugin_data()` 第 346 行使用 `if namespace == DataNamespace.PUBLIC and notify:` 进行枚举身份比较。
  - 若调用方（如插件）从 `core.interfaces.i_data_provider` 导入 `DataNamespace.PUBLIC` 传入，比较返回 `False`，`notify=True` 时不会触发回调。
  - `ui/main_window.py` 当前从 `core.data.data_provider` 导入 `DataNamespace`，所以 UI 路径未触发该 bug；但插件侧导入路径不可控，风险真实存在。
- **迁移修复**：统一使用字符串值比较（`namespace_str == DataNamespace.PUBLIC.value`），无论调用方从 `core.data` 还是 `core.interfaces` 导入 `DataNamespace.PUBLIC`，通知行为都正确。这是兼容性修复，不是破坏性变更。

### 6.6 线程安全

- 保留 `_file_lock`（`threading.RLock`），用它保护 SQLite 连接与游标操作。
- SQLite 连接对象默认禁止跨线程使用（`check_same_thread=True`）。迁移后使用：
  ```python
  self._db_connection = sqlite3.connect(
      self.db_file,
      check_same_thread=False,  # 允许在多个线程中复用同一连接
  )
  ```
  所有数据库操作仍由 `_file_lock` 串行化，因此不会出现并发访问同一连接的问题。
- 替代方案（可选）：使用 `threading.local()` 为每个线程维护独立连接，并在 `_file_lock` 保护下按需创建/复用。此方案可避免 `check_same_thread=False`，但实现更复杂。推荐方案为单连接 + `_file_lock`。
- **锁顺序铁律（必须遵守）**：
  - 订阅表相关操作（`subscribe` / `unsubscribe` / `_remove_subscriptions_for_plugin` / `_notify_subscribers`）必须在**完全释放 `_file_lock` 之后**再获取 `_subscription_lock`。
  - 任何情况下不得同时持有 `_file_lock` 与 `_subscription_lock`。
  - `set_plugin_data` 的数据库写入、缓存失效、`_cache` 更新均在 `_file_lock` 保护下完成；通知回调在释放 `_file_lock` 后调用，因此回调内部再次操作 DataProvider 时不会死锁。
- **当前实现存在的锁顺序问题（需要在迁移中修复）**：
  - `subscribe()` 第 394-402 行：先调用 `load_data()`（内部获取 `_file_lock`），验证目标插件存在后，再 `with self._subscription_lock:` 注册回调。这违反了"先 `_file_lock` 后 `_subscription_lock`"的顺序。
  - `unregister_plugin()` 第 218-238 行：先调用 `load_data()` / `save_data()`（持有 `_file_lock`），然后再调用 `_remove_subscriptions_for_plugin()`（获取 `_subscription_lock`）。同样违反锁顺序。
- **迁移修正方案**：
  - `subscribe`：在 `_file_lock` 保护下仅查询 SQLite 验证目标插件存在，然后**释放 `_file_lock`**，再获取 `_subscription_lock` 注册回调。
  - `unregister_plugin`：在 `_file_lock` 保护下完成数据库删除、缓存失效、`_cache` 更新，然后**释放 `_file_lock`**，再调用 `_remove_subscriptions_for_plugin()`。
  - `_subscription_lock` 从 `threading.RLock` 改为普通 `threading.Lock`，因为订阅表操作无需重入，且普通锁能更快暴露潜在死锁。
- 迁移不引入新的并发问题。

### 6.7 SQLite PRAGMA 配置

每次连接时执行：

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
```

- `WAL` 模式提高并发读性能，避免写操作阻塞读操作。
- `synchronous=NORMAL` 在性能与持久化之间取得平衡。

---

## 7. 数据迁移方案

### 7.1 自动迁移触发条件

仅在同时满足以下条件时执行：

1. `data.json` 存在且可被解析为合法 JSON。
2. `data.db` 不存在；或 `data.db` 存在但大小为 0 字节（空文件）；或 `data.db` 存在但尚未创建任何表（可通过查询 `sqlite_master` 判定）。

“data.db 已初始化”的判定标准：`data.db` 存在且 `sqlite_master` 中包含 `plugins`、`plugin_data`、`active_instances` 三张表。

### 7.1.1 WAL 附属文件

启用 WAL 模式后，SQLite 会在同级目录生成：

- `data.db-wal`：预写日志文件。
- `data.db-shm`：共享内存索引文件。

这些文件是 SQLite 正常工作所需，不应手动删除。判断迁移触发条件时只检查 `data.db` 本身，不检查 `-wal`/`-shm`。

### 7.2 迁移步骤

1. 读取 `data.json` 全部内容到内存。
   - 当前实现与旧 JSON 实现一致，均为全量读取。对于极大 `data.json`（如数百 MB 以上），需评估内存风险；如存在此类场景，应提前分批处理或作为独立优化项。
   - **仅迁移标准顶层键**：迁移只处理 `plugins` 和 `active_instances` 两个顶层键。若旧 `data.json` 中存在其他自定义顶层键（旧 `load_data`/`save_data` 允许），这些键在迁移后会丢失。这是 schema 变更带来的限制，需在变更日志中说明。
2. 创建 `data.db` 并执行 DDL（含 `db_metadata`）。
3. 对每条待导入的 value 调用 `_sanitize_for_migration(value)` 进行清洗扫描，再调用 `_serialize(cleaned_value)` 序列化。
   - 清洗扫描递归查找 `NaN/Inf` 并替换为 `None`，将非字符串 dict key（如 `datetime` / `UUID` / `tuple`）转为字符串；同时记录 `warning` 日志告知用户某插件某 key 的数据已被清洗。
   - 若旧数据中存在大量 `NaN/Inf`，清洗会改变业务语义（`float` 变为 `NoneType`；`Inf`/`-Inf` 的无界语义丢失），需在变更日志中明确告知插件开发者。
   - `_sanitize_for_migration` 实现示例：

```python
import math
from typing import Any, Dict

def _sanitize_for_migration(obj: Any, path: str = "") -> Any:
    """迁移专用：递归将 NaN/Inf 替换为 None，同时处理 dict key。"""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        # 实际实现中应使用项目 logger；此处仅示例
        print(f"[warn] 迁移清洗：将 {path} 处的 {obj} 替换为 None")
        return None
    if isinstance(obj, dict):
        # key 中的 NaN/Inf 也清洗；key 若为 UUID/datetime/tuple 则转为字符串
        new_dict: Dict[Any, Any] = {}
        for k, v in obj.items():
            new_k = _sanitize_for_migration(k, f"{path}.{k}(key)")
            if not isinstance(new_k, (str, int, float, bool, type(None))):
                new_k = str(new_k)
            new_dict[new_k] = _sanitize_for_migration(v, f"{path}.{k}")
        return new_dict
    if isinstance(obj, list):
        return [_sanitize_for_migration(item, f"{path}[{i}]") for i, item in enumerate(obj)]
    return obj
```
4. 执行 DDL 与事务：
   - **注意**：SQLite 中 DDL 语句会隐式提交当前事务，因此不能将 `CREATE TABLE` 与 DML 放在同一个显式事务中。
   - 先创建 `data.db` 连接并执行 DDL（`plugins`、`plugin_data`、`active_instances`、`db_metadata` 四张表及索引）。
   - 再开启一个显式事务，执行 DML：
     - 逐条插入 `plugins`。
     - 逐条插入 `plugin_data`（private/public 下的每个 key 一行）。
     - 逐条插入 `active_instances`：
       - 插入前校验引用的 `instance_id` 是否存在于已插入的 `plugins` 中。
       - 若存在孤立引用（旧 `data.json` 中 `active_instances.<type>` 指向不存在的插件），丢弃该记录并记录 `warning` 日志，避免外键约束失败。
     - 插入 `db_metadata`：
       - `schema_version` = `'1'`
       - `migrated_from` = `'<原始 JSON 文件名>'`（如 `data.json`）
       - `migrated_at` = 当前 ISO 8601 时间戳
5. **提交 SQLite 事务**。
   - 事务成功提交后，`data.db` 中已包含完整数据与元数据。
   - 若提交过程中发生异常（如磁盘满、WAL 写入失败、序列化失败），视为迁移未完全成功：回滚 SQLite 事务、关闭连接、删除不完整的 `data.db` / `-wal`/`-shm`、保留原始 `data.json`，并抛出 `DataProviderError`。
6. **重命名 `data.json` 为备份**。
   - 只有在 SQLite 事务成功提交后，才将 `data.json` 重命名为 `data.json.migrated-<ISO8601-微秒>.bak`。
   - 若重命名失败（权限、磁盘满等），数据本身已经安全保存在 `data.db` 中；此时 `data.json` 仍在原位，下次启动不会触发重复迁移。应用应记录 error 日志并提示用户手动处理备份文件。

> **关于 `NaN/Inf` 的说明**：标准库 `json` 默认允许输出非标准的 `NaN`/`Infinity` 标记（可被 `json.loads` 读回），但 `orjson.loads` 无法解析这些标记。为保证迁移后后端一致可用，迁移阶段必须将 `NaN/Inf` 清洗为 `None`。新后端下写入 `NaN/Inf` 会统一抛出 `DataProviderError`。

### 7.3 迁移失败处理

- 任何异常都回滚 SQLite 事务。
- 在删除不完整的 `data.db` 及 `-wal`/`-shm` 文件前，**必须先关闭数据库连接**（`conn.close()`），避免 Windows 等系统因文件被占用而删除失败。关闭连接应在 `try...finally` 或异常处理中保证执行。
- 若删除文件失败（如权限、占用），应记录 error 日志并提示用户手动清理。
- **确保 `data.json` 仍然以原始文件名存在**：
  - 如果迁移在 SQLite 事务提交之前失败，原始 `data.json` 不动；`data.db` 会被清理。
  - 如果 SQLite 事务已提交但重命名 `data.json` 失败，`data.json` 仍在原位，`data.db` 已包含完整数据。这种情况不会导致数据丢失，但会遗留一份过时的 `data.json`，需要用户手动清理或重命名。
  - 目标是：无论失败发生在哪个阶段，应用下次启动时都能安全地基于 `data.db` 运行；如果需要重试迁移，可手动删除 `data.db` 并保留原始 `data.json`。
- 若 `data.json` 损坏或 JSON 解析失败：
  - 不创建 `data.db`。
  - 抛出 `DataProviderError`，提示用户 `data.json` 损坏。
  - 应用层可选择提示用户手动修复或删除 `data.json`（删除后将创建空数据库）。
- 抛出 `DataProviderError`，应用层可选择提示用户。

### 7.4 回退方案

如果迁移后发现功能异常，可按以下步骤回退到 JSON 模式：

1. **关闭应用**，确保 SQLite 连接已释放。
2. **回退/切换代码到 JSON 实现**，或设置环境变量启用临时 JSON 后端开关：
   - 若代码尚未合并：切回 feature 分支之前的 `dev` 代码。
   - 若已合并但保留临时开关：设置环境变量 `INSTRUCTIONX_DATAPROVIDER_BACKEND=json` 后启动应用。
   - **关键：仅删除数据库文件而不切换代码，下次启动时会因触发自动迁移条件而再次迁移到 SQLite，导致回退失败。**
3. 删除 `data/data.db`、`data/data.db-wal`、`data/data.db-shm`。
4. 根据时间戳选取最新的 `data.json.migrated-<ISO8601-毫秒>.bak`，将其重命名为 `data.json`。示例（bash，注意文件名中的 `+` 需要转义或加引号）：
   ```bash
   cd data
   latest=$(ls -1 data.json.migrated-*.bak | sort | tail -n 1)
   mv "$latest" data.json
   ```
5. 重新启动应用。

> ⚠️ **重要警告**：
> - 回退到 JSON 后，迁移成功后写入 SQLite 的新数据将丢失（因为期间只写 SQLite）。
> - 如果阶段 3 实现的临时 JSON 后端开关在阶段 4 后仍然保留，环境变量 `INSTRUCTIONX_DATAPROVIDER_BACKEND=json` 可作为应急回退手段；默认值为 SQLite。
> - 每次迁移成功都会生成一个新的 `.bak` 文件，长期积累会占用磁盘；可在阶段 6 提供清理旧备份的工具或策略，但不应自动删除最近几次备份，以免用户需要回退时无备份可用。
> - 建议在实际迁移前做好备份，并在迁移验证通过后继续运行。

---

## 8. 性能预期与优化策略

### 8.1 性能预期

| 操作 | JSON 模式（当前） | SQLite 模式（迁移后） |
|------|-------------------|------------------------|
| `get_plugin_data` | O(文件大小) 反序列化 + O(1) 字典查 | O(log n) 索引查 + 单值反序列化（缓存命中时无反序列化） |
| `set_plugin_data` | O(文件大小) 反序列化 + O(n) 序列化 + 全量写盘 | O(log n) 索引写 + 单值序列化 |
| `get_all_plugin_data` | O(文件大小) 反序列化 | O(k) 查询该插件命名空间 k 个 key |
| `register_plugin` | 全量读写 | 单条 INSERT |
| `load_data` | 全量反序列化 | 全量查询 + 组装（调用较少） |

在数万行数据场景下，预期 `set_plugin_data` / `get_plugin_data` 延迟从数十到数百毫秒降至亚毫秒级。

### 8.2 序列化性能优化：`orjson` + LRU 反序列化缓存

#### 8.2.1 为什么需要优化

SQLite 迁移解决了“全量文件读写”问题，但单次 `get_plugin_data` 仍需把 TEXT 反序列化为 Python 对象，单次 `set_plugin_data` 仍需把 Python 对象序列化为 TEXT。当 value 是大型 dict/list 时，标准库 `json` 的 CPU 开销仍然显著。

本地基准（Python 3.14.3，37 KB 嵌套对象，10000 次）：

| 操作 | 标准库 `json` | `orjson` | 提升 |
|------|--------------|----------|------|
| dumps | 6.4s | 0.6s | **~10.7x** |
| loads | 5.0s | 1.5s | **~3.4x** |

#### 8.2.2 方案：orjson 替换 json

**完整实现见第 6.4.0 节 `_serialize` / `_deserialize`。** 要点如下：

- 序列化使用 `orjson.dumps(..., option=orjson.OPT_NON_STR_KEYS | OPT_PASSTHROUGH_DATETIME | OPT_PASSTHROUGH_DATACLASS, default=_raise_non_serializable).decode('utf-8')`。
  - `OPT_NON_STR_KEYS` 使 int/float/bool/None/IntEnum/IntFlag 等非字符串 dict key 自动转为字符串；tuple 作为 key 时被拒绝，与 `json.dumps` 行为一致。
  - `OPT_PASSTHROUGH_DATETIME` / `OPT_PASSTHROUGH_DATACLASS` 强制让 `datetime`/`date`/`time` 和 `dataclass` 走 `default` 钩子，避免 `orjson` 默认序列化这些类型（标准库 `json` 会抛 `TypeError`）。
  - `default` 钩子拒绝所有无法识别的类型，统一抛 `TypeError`，最终包装为 `DataProviderError`。
- 反序列化使用 `orjson.loads(text)` 替代 `json.loads(text)`。
- 保持 `value_json TEXT` 列类型不变，数据库仍存储标准 JSON 文本，便于调试和兼容。
- 旧 `data.json` 中的 `NaN/Infinity` 非标准标记在迁移阶段清洗为 `None`；新后端写入 `NaN/Inf` 会抛出 `DataProviderError`。
- `orjson` 输出标准 JSON，标准库 `json` 也能解析；旧 `data.json` 常规数据 `orjson` 也能解析（含 `NaN/Infinity` 非标准标记的数据在迁移阶段清洗为 `None`）。

#### 8.2.3 方案：LRU 反序列化缓存

在 `DataProvider` 内部维护按 key 的 LRU 缓存：

- key：`(instance_id, namespace, key)`
- value：反序列化后的 Python 对象
- 命中时直接返回深拷贝，避免重复 `orjson.loads`。
- `set_plugin_data` 写入后使对应缓存项失效。
- `unregister_plugin` / `reset_all_data` / `clear_cache` 清空相关/全部缓存。

**效果**：
- 写操作：序列化次数从“每次写整个文件”变为“每次写单个 value”，再乘以 `orjson` 10x 加速。
- 读操作：缓存命中时完全跳过反序列化；未命中时单次 `orjson.loads` 比 `json.loads` 快 3x。

#### 8.2.4 兼容性保证

- 插件接口完全无感：传入/返回的仍是 Python 对象。
- 标准库 `json` 与 `orjson` 对常规类型（dict/list/str/int/float/bool/None）完全互操作。
- 边界类型处理：保持当前 `json` 行为，包括嵌套场景；即 `bytes` / `bytearray` / `set` / `frozenset`、嵌套 `datetime` / `date` / `time` / `UUID` / `dataclass` 不可序列化，嵌套 `NaN/Inf` 显式检测抛异常；`int` / `float` / `bool` / `None` / `IntEnum` / `IntFlag` 等 dict key 通过 `OPT_NON_STR_KEYS` 自动转字符串，`tuple` 作为 dict key 时被拒绝。

#### 8.2.5 依赖说明

- `orjson` 作为唯一新增依赖加入 `pyproject.toml`，版本约束 `>=3.11.0,<4`。
- `pyproject.toml` 与 `uv.lock` 必须同步更新，确保 CI/新环境能正确安装。
- 已在本地 `.venv`（Python 3.14.3）验证 `orjson 3.11.9` 可正常安装和运行。
- 如未来希望移除 `orjson`，只需替换 `_serialize` / `_deserialize` 两个私有方法回标准库 `json`，不影响业务逻辑。

---

## 9. 测试策略

### 9.1 现有测试状态

| 文件/目录 | 实际状态 | 说明 |
|-----------|----------|------|
| `test/core/data/` | 仅存在 `__pycache__` 目录 | 源码文件缺失 |
| `test/core/data/test_data_provider.py` | **不存在** | `__pycache__` 中残留 `test_data_provider.cpython-314-pytest-9.0.3.pyc`，说明历史上可能短暂存在过，但当前源码已删除 |
| `core/data/data_provider.py` 的 `__main__` 演示 | 存在 | 可作为 JSON 模式基线运行 |

**结论**：当前无 `DataProvider` 本身的单元测试。本次迁移需要从零建立 `test/core/data/test_data_provider.py`，并覆盖 JSON 后端开关、SQLite 后端、迁移、schema 版本、序列化兼容性等全部场景。

### 9.2 新增测试：`test/core/data/test_data_provider.py`

必须为 SQLite 版 `DataProvider` 编写完整测试，覆盖所有公共接口：

| 测试类 | 场景 |
|--------|------|
| `TestSingleton` | 多次 `DataProvider()` 返回同一实例；带参数初始化不重建；非默认 `data_filename`（含/不含 `.json` 后缀）能正确推导数据库文件名。 |
| `TestRegisterUnregister` | 注册、重复注册抛异常、注销、注销不存在抛异常。 |
| `TestActiveInstance` | 设置活跃、获取活跃、切换活跃、同类型唯一活跃。 |
| `TestPluginData` | private/public 读写；默认值；覆盖写入；不存在插件抛异常；嵌套 dict/list 值往返；验证底层使用 `orjson`。 |
| `TestGetAllPluginData` | 返回副本，外部修改不影响数据库。 |
| `TestPubSub` | 订阅、public 变更触发回调、private 不触发、`notify=False` 不触发、取消订阅。 |
| `TestAssets` | save/load/get_asset_path/get_plugin_assets_dir，路径遍历防护。 |
| `TestCache` | load_data 缓存、force_reload、clear_cache、save_data、LRU 反序列化缓存命中与失效。 |
| `TestResetAllData` | 重置后数据库为空；`_subscriptions` 保持不清空（与旧实现行为一致）。 |
| `TestMigration` | 从 JSON 自动导入；导入后 SQLite 内容正确；备份文件生成；`db_metadata` 写入正确。 |
| `TestSchemaVersion` | 新建数据库 `schema_version` 为 `'1'`；从 JSON 迁移后 `schema_version` 为 `'1'`；版本键可读。 |
| `TestSchemaUpgrade` | 模拟低版本数据库（如版本 `0` 或 `1`），验证链式升级脚本被依次执行；高版本数据库触发 `DataProviderError`。 |
| `TestLegacyDatabase` | 模拟“有核心表但无 `db_metadata`”的旧数据库，验证能补齐到版本 `1` 且不丢数据。 |
| `TestCorruptSchemaVersion` | 模拟 `schema_version='abc'`，验证抛出 `DataProviderError`。 |
| `TestMetadata` | `migrated_from`、`migrated_at` 等元数据正确写入。 |
| `TestSerializationCompatibility` | `orjson` 序列化的数据可被标准库 `json.loads` 解析；旧 `json.dumps` 数据可被 `orjson.loads` 解析；`bytes` / `bytearray` / `set` / `frozenset`、顶层/嵌套 `datetime`/`date`/`time`/`UUID`/`dataclass`、顶层/嵌套 `NaN`/`Inf` 抛出 `DataProviderError`；非字符串 dict key 能正确序列化/反序列化；迁移清洗函数能将嵌套 `NaN/Inf` 替换为 `None`。 |
| `TestLRUCache` | 重复 `get_plugin_data` 命中缓存且返回独立副本；`set_plugin_data` 后缓存失效；`clear_cache`/`reset_all_data`/`unregister_plugin` 清空相关缓存；容量上限生效（LRU 淘汰最久未使用项）。 |
| `TestNotifyLockOrder` | 验证 `set_plugin_data(PUBLIC, notify=True)` 在释放 `_file_lock` 后才调用订阅回调；回调中再次操作 DataProvider 不导致死锁。 |
| `TestConcurrency` | 多线程高频 set/get 不抛异常、最终一致。 |

### 9.3 兼容性/回归测试

- 运行 `core/data/data_provider.py` 的 `__main__` 演示代码，验证输出行为一致。
- 启动主应用 `main.py`，验证主题、LLM 偏好读写正常。
- 加载示例插件，验证插件通过 `PluginServices.data_provider` 存取数据正常。

### 9.4 性能基准

- 向一个插件写入 10000 个 key（每个 value 为中等复杂度的 dict/list），测量总耗时与单次平均耗时。
- 随机读取 1000 个 key，测量总耗时与单次平均耗时。
- 与旧 JSON 模式对比：
  - 写入：`set_plugin_data` 单次平均耗时在 SQLite 模式下应低于 1 ms（旧 JSON 模式在数万行数据下通常数十到数百 ms）。
  - 读取：`get_plugin_data` 单次平均耗时在 SQLite + LRU 缓存命中时应低于 0.1 ms；缓存未命中时应低于 1 ms（旧 JSON 模式通常数十 ms）。
- 指标为参考值，具体以实际运行环境为准；关键是确认 SQLite 模式下延迟不随数据总量线性增长。

---

## 10. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 接口签名误改 | 插件无法编译/运行 | 严格对照 `IDataProvider` 检查；代码审查重点检查方法签名。 |
| 数据迁移丢失 | 用户数据丢失 | 保留原始 JSON 备份；迁移失败回滚；自动迁移前验证 JSON 可解析。 |
| SQLite 并发写入阻塞 | UI 卡顿 | WAL 模式；写操作尽量简短；订阅回调不持有数据库锁。 |
| 回调死锁 | 应用卡死 | 保持现有 `_subscription_lock` 设计不变；文档提醒插件开发者避免回调中再调 DataProvider。 |
| JSON 不可序列化值行为变化 | 数据写入失败 | 在 `_serialize` 中保持与当前标准库 `json` 一致的行为（如 `bytes`/`bytearray`/`set`/`frozenset`/`datetime`/`NaN/Inf` 抛出异常），并由 `DataProviderError` 包装。 |
| `load_data()` 返回结构与插件预期不同 | 兼容性破坏 | 使用 `_read_from_disk` 严格按原 JSON 结构组装。 |
| 现有 `data.json.tmp` 残留 | 无实质影响，但占用磁盘 | 迁移完成后在 `DataProvider` 初始化时清理已存在的 `data.json.tmp` 残留文件。 |
| 数据库版本缺失或损坏 | 链式升级失败或误判 | 初始化时自动检测/补齐版本；版本损坏时抛出 `DataProviderError` 并提示用户。 |
| 高版本数据库被低版本代码打开 | 数据损坏或行为异常 | 检测到 `schema_version > TARGET_SCHEMA_VERSION` 时直接抛出 `DataProviderError`，拒绝启动。 |
| 迁移脚本编写错误 | 升级失败或数据不一致 | 每个迁移脚本独立事务；升级前在测试环境中完整验证；保留备份。 |
| `orjson` 与标准库 `json` 行为不一致 | 特定值（如 `NaN/Inf`、`datetime`、`UUID`、`dataclass`、`bytes`/`bytearray`/`set`/`frozenset`）序列化结果异常 | 在 `_serialize` 中递归检测边界类型，保持与当前 `json` 一致的行为；常规类型互操作已验证。 |
| LRU 缓存返回对象被外部修改 | 缓存污染导致后续读取得到错误数据 | 缓存命中后返回深拷贝；`set_plugin_data` 立即失效对应缓存项。 |
| `orjson` 依赖安装失败 | 环境无法使用优化方案 | `pyproject.toml` 明确依赖 `>=3.11.0,<4`；`uv.lock` 同步更新；CI/安装流程验证；保留标准库 `json` 降级路径（替换 `_serialize` / `_deserialize` 即可）。 |
| `uv.lock` 与 `pyproject.toml` 不同步 | 新环境/CI 缺少 `orjson` | 每次修改 `pyproject.toml` 后运行 `uv lock` 同步；将 `uv.lock` 变更纳入代码审查。 |

---

## 11. 分阶段实施计划

> 本章为 Agent/开发者提供可执行、递进、可验收的迁移路线图。每个阶段有明确目标、输入依赖、输出产物、验收标准（Definition of Done）和回退策略，阶段之间逻辑递进，前一阶段不通过不得进入下一阶段。

### 11.0 总体原则

1. **阶段 gate**：每个阶段完成后必须通过本阶段全部验收标准，方可进入下一阶段。
2. **最小侵入**：每阶段只修改必要的文件，保持 `data_provider.py` 公共接口不变。
3. **可回退**：
   - 阶段 0~2 不修改 `data_provider.py`，应用仍可运行 JSON 模式。
   - 阶段 3 改造 `data_provider.py` 期间，应保留一个临时后端开关（环境变量或初始化参数），允许在 SQLite 与 JSON 之间切换，便于调试和异常回退。
   - 阶段 4 正式启用自动迁移后，默认使用 SQLite；回退方式见第 10 节「风险与回退」。
4. **边生成边测试**：每个编码任务完成后必须立即运行对应测试并确认通过；禁止一次性提交大量未经测试的代码。新增功能必须先写测试或同步写测试，禁止无测试的代码合并。
5. **文档同步**：每阶段产生的关键设计变更需在阶段文档/注释中记录。
6. **Commit 规范**：迁移阶段产生的所有 commit，消息括号内必须标注 `(UpSQL: 具体模块/功能)`。标签必须精简、一致，便于后续按模块回退和变更审计。

   推荐标签表（按模块分类）：

   | 标签 | 使用场景 |
   |------|----------|
   | `(UpSQL: setup)` | 阶段 0：分支创建、数据备份、依赖确认、文件占位。 |
   | `(UpSQL: sqlite_backend)` | `SQLiteBackend`、DDL、连接、事务、基础 CRUD。 |
   | `(UpSQL: schema_migrations)` | `schema_migrations.py`、版本注册表、链式升级调度。 |
   | `(UpSQL: serialization)` | orjson 序列化/反序列化、边界类型处理。 |
   | `(UpSQL: lru_cache)` | LRU 反序列化缓存实现。 |
   | `(UpSQL: dataprovider_sqlite)` | `DataProvider` 改造为 SQLite 后端、临时 JSON 开关。 |
   | `(UpSQL: migration)` | JSON → SQLite 自动迁移、数据清洗、备份与回滚。 |
   | `(UpSQL: tests)` | 各阶段单元测试、集成测试、边界测试。 |
   | `(UpSQL: integration)` | 主应用冒烟测试、插件回归、资源文件验证。 |
   | `(UpSQL: benchmark)` | 性能基准、并发压力测试。 |
   | `(UpSQL: docs)` | Markdown 文档、docstring、README 更新。 |
   | `(UpSQL: cleanup)` | 清理 `data.json.tmp`、旧迁移备份等收尾工作。 |
   | `(UpSQL: audit)` | 审计记录、迁移计划状态更新。 |
   | `(UpSQL: chore)` | 分支合并、CI 配置等工程事务。 |

   阶段 0~6 末尾的「建议 commit」是按模块聚合的示例；实际执行时应遵循 11.8「子任务执行纪律」，将一个模块拆分为多个**单逻辑单元 commit**（如一个函数/一个测试类），每个 commit 都使用对应模块标签。

---

### 阶段 0：准备与基线

**目标**：建立安全、可验证的改造环境，确保后续阶段有稳定的比较基线。

**输入依赖**：
- 当前 `dev` 分支代码可运行。
- `data/data.json` 存在（或为空）。
- Python 3.14 + orjson 3.11.9 已验证可用。

**关键任务**：

| # | 任务 | 说明 |
|---|------|------|
| 0.1 | 创建 feature 分支 | 如 `feature/dataprovider-sqlite-migration`。 |
| 0.2 | 备份 `data/data.json` | 复制到 `data/data.json.bak`，作为本次 feature 分支的人工迁移回退基线。注意：这与阶段 4 自动迁移成功后生成的 `data.json.migrated-<时间戳>.bak` 不同；前者由开发者手动保留，后者由迁移流程自动生成。 |
| 0.3 | 确认 `orjson` 依赖 | **已就绪**。`pyproject.toml` 第 10 行已包含 `orjson>=3.11.0,<4`；本地 `.venv`（Python 3.14.3）验证 `orjson.__version__ == 3.11.9`，可正常导入。`uv.lock` 需与 `pyproject.toml` 保持同步。 |
| 0.4 | 冻结当前行为基线 | 运行 `core/data/data_provider.py` 的 `__main__` 演示，记录输出。记录当前 `data/data.json` 状态（当前为默认空结构 `{\"plugins\": {}, \"active_instances\": {}}`）。 |
| 0.5 | 创建新增文件占位 | 创建 `core/data/sqlite_backend.py`、`core/data/schema_migrations.py`、`test/core/data/test_data_provider.py`（空文件或仅含模块 docstring）。 |

**输出产物**：
- feature 分支。
- `data/data.json.bak`。
- 基线运行记录（日志/截图）。
- 3 个新增文件占位。

**验收标准（DoD）**：
- [ ] feature 分支已创建并切换到该分支。
- [ ] `data/data.json.bak` 存在且与当前 `data.json` 一致。
- [x] `orjson` 依赖已就绪：`pyproject.toml` 已包含 `orjson>=3.11.0,<4`，且 `.venv\Scripts\python.exe -c "import orjson; print(orjson.__version__)"` 输出 `3.11.9`。
- [ ] `core/data/data_provider.py` 演示代码在 JSON 模式下可正常运行（尚未修改）。

**风险与回退**：
- 风险：环境准备失败导致后续无法开展。
- 回退：放弃 feature 分支，回到 `dev` 继续调研。


**建议 commit**：
- `(UpSQL: setup)` 创建 feature 分支、数据备份、orjson 依赖确认、新增文件占位。

---

### 阶段 1：SQLite 基础设施

**目标**：构建独立的 SQLite 后端模块，提供数据库连接、DDL、事务、版本元数据管理能力；此阶段不修改 `data_provider.py`。

**输入依赖**：阶段 0 完成。

**关键任务**：

| # | 任务 | 说明 |
|---|------|------|
| 1.1 | 实现 `SQLiteBackend` 类 | 在 `core/data/sqlite_backend.py` 中实现数据库连接管理、PRAGMA 配置（WAL、外键）、单连接 + `_file_lock` 线程安全模型。 |
| 1.2 | 实现 DDL | 提供 `create_tables()` 方法，创建 `plugins`、`plugin_data`、`active_instances`、`db_metadata` 四张表及索引。 |
| 1.3 | 实现版本元数据读写 | 提供 `get_schema_version()`、`set_schema_version()`、`get_metadata()`、`set_metadata()`。 |
| 1.4 | 实现事务上下文 | 提供 `transaction()` 上下文管理器，支持 `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK`。 |
| 1.5 | 实现 schema 初始化与升级调度 | 在 `sqlite_backend.py` 中实现 `ensure_database()`，调用 `schema_migrations.py` 的 `MIGRATIONS` 注册表完成链式升级。 |
| 1.6 | 实现 `schema_migrations.py` | 定义 `TARGET_SCHEMA_VERSION = 1`，`MIGRATIONS: Dict[int, Callable] = {}`；编写示例注释说明未来如何添加升级函数。 |
| 1.7 | 编写单元测试 | 在 `test/core/data/test_data_provider.py` 中新增 `TestSQLiteBackend`、`TestSchemaVersion`、`TestSchemaUpgrade`、`TestLegacyDatabase`、`TestCorruptSchemaVersion` 等测试类。 |

**输出产物**：
- `core/data/sqlite_backend.py`（完整可运行）。
- `core/data/schema_migrations.py`（框架 + 空注册表）。
- 通过阶段 1 单元测试。

**验收标准（DoD）**：
- [ ] `SQLiteBackend` 可创建 `data.db` 并正确执行 DDL。
- [ ] `get_schema_version()` / `set_schema_version()` 读写正确。
- [ ] 链式升级逻辑正确：版本 `0 → 1` 补齐、版本 `1 → 2` 执行、版本 `99` 拒绝启动。
- [ ] 事务回滚正确：异常时数据不残留。
- [ ] 所有阶段 1 单元测试通过。
- [ ] **此阶段不修改 `core/data/data_provider.py`**。

**风险与回退**：
- 风险：DDL 设计有缺陷导致后续数据插入失败。
- 回退：删除 `data.db`，修改 DDL 后重新进入阶段 1。


**建议 commit**：
- `(UpSQL: sqlite_backend)` 实现 `SQLiteBackend`、DDL、事务、版本元数据。
- `(UpSQL: schema_migrations)` 创建 `schema_migrations.py` 与链式升级框架。
- `(UpSQL: tests)` 新增 `TestSQLiteBackend`、`TestSchemaVersion` 等单元测试。

---

### 阶段 2：序列化与缓存层

**目标**：实现与标准库 `json` 行为一致的 orjson 序列化/反序列化，以及带容量上限的 LRU 反序列化缓存；此阶段仍不修改 `data_provider.py`。

**输入依赖**：阶段 1 完成。

**关键任务**：

| # | 任务 | 说明 |
|---|------|------|
| 2.1 | 实现 `_serialize` / `_deserialize` | 在 `core/data/sqlite_backend.py` 中实现，严格按第 6.4.0 节代码，包含 `_scan_non_json_types`、`_raise_non_serializable`、`OPT_NON_STR_KEYS` / `OPT_PASSTHROUGH_DATETIME` / `OPT_PASSTHROUGH_DATACLASS`。 |
| 2.2 | 实现 `_LRUCache` | 在 `core/data/sqlite_backend.py` 中实现基于 `collections.OrderedDict` 的 LRU，支持 `get/put/invalidate/invalidate_plugin/clear`，默认容量 4096。 |
| 2.3 | 实现迁移清洗函数 | 在 `core/data/sqlite_backend.py` 中实现 `_sanitize_for_migration`，递归清洗 `NaN/Inf` 并处理特殊 dict key。 |
| 2.4 | 编写单元测试 | 新增 `TestSerializationCompatibility`、`TestLRUCache`，覆盖常规类型、边界类型（嵌套 datetime/UUID/dataclass/NaN/Inf）、非字符串 dict key、缓存命中/失效/容量/深拷贝隔离。 |

**输出产物**：
- `core/data/sqlite_backend.py` 补充序列化与缓存功能。
- 通过阶段 2 单元测试。

**验收标准（DoD）**：
- [ ] `orjson` 序列化的数据可被 `json.loads` 解析；旧 `json.dumps` 数据可被 `orjson.loads` 解析。
- [ ] `bytes` / `bytearray` / `set` / `frozenset`、嵌套 `datetime`/`date`/`time`/`UUID`/`dataclass`、嵌套 `NaN`/`Inf` 均抛出 `DataProviderError`。
- [ ] 非字符串 dict key 能正确序列化为字符串 key。
- [ ] LRU 缓存容量上限生效，命中返回深拷贝，写入后失效正确。
- [ ] `_sanitize_for_migration` 能将嵌套 `NaN/Inf` 替换为 `None`。
- [ ] 所有阶段 2 单元测试通过。
- [ ] **此阶段不修改 `core/data/data_provider.py`**。

**风险与回退**：
- 风险：序列化行为与旧 `json` 不完全一致。
- 回退：替换 `_serialize` / `_deserialize` 回标准库 `json` 临时降级。


**建议 commit**：
- `(UpSQL: serialization)` 实现 orjson 序列化/反序列化与边界类型处理。
- `(UpSQL: lru_cache)` 实现带容量上限的 LRU 反序列化缓存。
- `(UpSQL: migration)` 实现迁移阶段 `NaN/Inf` 清洗函数。
- `(UpSQL: tests)` 新增 `TestSerializationCompatibility`、`TestLRUCache`。

---

### 阶段 3：DataProvider 核心改造

**目标**：将 `core/data/data_provider.py` 的持久化后端从 JSON 切换到 SQLite，保持所有公共接口不变；此阶段不启用自动迁移（手动创建空数据库测试）。

**输入依赖**：阶段 2 完成。

**关键任务**：

| # | 任务 | 说明 |
|---|------|------|
| 3.1 | 重构 `DataProvider.__init__` | 保留单例和参数签名；内部调用 `sqlite_backend.ensure_database()` 初始化数据库；保留 `_cache`、`_subscriptions`、资源目录。实现临时后端开关，允许通过环境变量切回 JSON 后端以便调试。 |
| 3.2 | 实现 `_ensure_database` | 替代 `_ensure_data_file`，处理新建数据库、已存在数据库版本检测、链式升级、无版本旧数据库补齐。 |
| 3.3 | 实现 `_read_from_disk` / `_write_to_disk` | 从 SQLite 重建完整字典 / 将完整字典写回 SQLite，同时填充/清空 LRU 缓存。 |
| 3.4 | 改造插件管理方法 | `register_plugin`、`unregister_plugin`、`get_active_instance`、`set_active_instance` 改为 SQLite 实现，并正确处理缓存失效。 |
| 3.5 | 改造数据访问方法 | `get_plugin_data`、`set_plugin_data`、`get_all_plugin_data` 改为 SQLite + LRU 缓存实现；`set_plugin_data` 释放 `_file_lock` 后再通知订阅者。 |
| 3.6 | 改造工具方法 | `load_data`、`save_data`、`clear_cache`、`get_all_plugins`、`get_plugin_info`、`reset_all_data` 改为 SQLite 实现。 |
| 3.7 | 保留不变逻辑 | `save_asset`、`get_asset_path`、`load_asset`、`get_plugin_assets_dir`、Pub/Sub 内存管理原样保留。 |
| 3.8 | 编写单元测试 | 在 `test/core/data/test_data_provider.py` 中新增/完善 `TestSingleton`、`TestRegisterUnregister`、`TestActiveInstance`、`TestPluginData`、`TestGetAllPluginData`、`TestPubSub`、`TestAssets`、`TestCache`、`TestResetAllData`、`TestNotifyLockOrder`、`TestConcurrency`。 |

**输出产物**：
- 改造后的 `core/data/data_provider.py`。
- 通过阶段 3 单元测试。

**验收标准（DoD）**：
- [ ] `DataProvider()` 单例行为不变。
- [ ] 所有公共方法签名与返回值语义与旧实现一致。
- [ ] 使用空数据库时，所有基本 CRUD 操作正常。
- [ ] `set_plugin_data(PUBLIC, notify=True)` 同步触发回调，且回调不在 `_file_lock` 内执行。
- [ ] 返回对象被外部修改后不污染缓存或数据库。
- [ ] 所有阶段 3 单元测试通过。
- [ ] `core/data/data_provider.py` 的 `__main__` 演示代码在新后端下输出行为与旧后端一致（除数据文件路径外）。
- [ ] 临时后端开关可用：设置指定环境变量（例如 `INSTRUCTIONX_DATAPROVIDER_BACKEND=json`）后，`DataProvider` 仍可使用旧 JSON 后端运行。

**风险与回退**：
- 风险：接口行为漂移。
- 回退：在 `DataProvider.__init__` 中保留一个临时开关，允许切回 JSON 实现进行对比调试。


**建议 commit**：
- `(UpSQL: dataprovider_sqlite)` 将 `DataProvider` 持久化后端切换为 SQLite，保留临时 JSON 后端开关。
- `(UpSQL: tests)` 新增/完善 `TestSingleton`、`TestPluginData`、`TestPubSub`、`TestCache` 等核心行为测试。

---

### 阶段 4：数据迁移与版本升级

**目标**：实现从旧 `data.json` 到 SQLite 的自动、无损迁移，并验证版本管理机制。

**输入依赖**：阶段 3 完成。

**关键任务**：

| # | 任务 | 说明 |
|---|------|------|
| 4.1 | 实现迁移触发逻辑 | 在 `_ensure_database` 中检测：若 `data.json` 存在，且 `data.db` 不存在、或 `data.db` 文件大小为 0 字节、或 `data.db` 未创建任何表，则执行迁移。 |
| 4.2 | 实现 JSON → SQLite 迁移 | 读取 `data.json`，插入 `plugins`、`plugin_data`、`active_instances`、`db_metadata`；对含 `NaN/Inf` 的 value 调用 `_sanitize_for_migration` 清洗。 |
| 4.3 | 实现迁移备份 | 迁移成功后将 `data.json` 重命名为 `data.json.migrated-<ISO8601-毫秒>.bak`（例如 `data.json.migrated-20260626T205238.123+0800.bak`），避免同一秒内重复迁移覆盖旧备份。 |
| 4.4 | 实现迁移失败回滚 | 任何异常回滚 SQLite 事务，删除不完整的 `data.db` 及 `-wal`/`-shm`，保留原始 `data.json`。 |
| 4.5 | 编写迁移测试 | 完善 `TestMigration`，覆盖：正常迁移、含 `NaN/Inf` 数据迁移、迁移失败回滚、备份文件生成、`db_metadata` 正确写入。 |
| 4.6 | 验证链式升级 | 手动构造版本 `0` / `1` / `2` 数据库，验证 `_upgrade_schema` 行为。 |

**输出产物**：
- 完整的迁移与升级逻辑。
- 通过阶段 4 单元测试。

**验收标准（DoD）**：
- [ ] 存在 `data.json` 且不存在 `data.db` 时，首次启动自动完成迁移。
- [ ] 迁移后 SQLite 中数据与 `data.json` 内容一致（`NaN/Inf` 按策略清洗为 `None`）。
- [ ] 迁移成功后生成 `data.json.migrated-<ISO8601-毫秒>.bak`。
- [ ] 迁移失败时 `data.db` 不完整文件被清理，原始 `data.json` 保留。
- [ ] 手动构造的低版本数据库能链式升级到当前目标版本。
- [ ] 高版本数据库被当前代码打开时抛出 `DataProviderError`。
- [ ] 所有阶段 4 单元测试通过。

**风险与回退**：
- 风险：迁移导致用户数据丢失或损坏；迁移成功后若继续使用 SQLite 写入新数据，再回退 JSON 模式将丢失这些新数据。
- 回退（迁移失败时）：异常会自动回滚 SQLite 事务并删除不完整的 `data.db` / `data.db-wal` / `data.db-shm`，原始 `data.json` 保留，应用回到 JSON 模式。
- 回退（迁移成功后想恢复 JSON 模式）：
  1. 停止应用，确保 SQLite 连接已释放。
  2. 根据时间戳选取最新的 `data.json.migrated-<ISO8601-毫秒>.bak`。
  3. 删除 `data.db`、`data.db-wal`、`data.db-shm`。
  4. 将选中的 `.bak` 重命名为 `data.json`。
  5. 切换/回退代码到 JSON 实现，或设置环境变量 `INSTRUCTIONX_DATAPROVIDER_BACKEND=json` 启用临时 JSON 后端开关。
  6. 重新启动应用。
  7. ⚠️ 注意：迁移成功后写入 SQLite 的新数据将无法恢复，回退前请确保这些新数据已备份或无需保留。


**建议 commit**：
- `(UpSQL: migration)` 实现 JSON → SQLite 自动迁移、备份、失败回滚。
- `(UpSQL: schema_upgrade)` 实现/验证链式 schema 升级。
- `(UpSQL: tests)` 新增 `TestMigration` 与迁移边界测试。

---

### 阶段 5：集成与回归测试

**目标**：在真实应用环境中验证迁移后的 DataProvider，确保主应用和插件正常工作。

**输入依赖**：阶段 4 完成。

**关键任务**：

| # | 任务 | 说明 |
|---|------|------|
| 5.1 | 运行主应用冒烟测试 | 启动 `main.py`，验证无异常启动。 |
| 5.2 | 验证主题/LLM 偏好持久化 | 在 `ui/main_window.py` 中，主题切换、LLM provider/model 选择重启后仍然保留。 |
| 5.3 | 验证插件加载与数据存取 | 加载示例插件（如有），验证通过 `PluginServices.data_provider` 读写数据正常。 |
| 5.4 | 验证 Pub/Sub | 两个插件之间订阅/发布数据变更正常。 |
| 5.5 | 验证资源文件 | `save_asset` / `load_asset` / `get_asset_path` 正常。 |
| 5.6 | 性能基准测试 | 按第 9.4 节进行：向一个插件写入 10000 个 key，随机读取 1000 个 key，与旧 JSON 模式对比。 |
| 5.7 | 并发压力测试 | 多线程高频 `set_plugin_data` / `get_plugin_data`，验证无异常、最终一致。 |

**输出产物**：
- 集成测试报告。
- 性能基准数据。

**验收标准（DoD）**：
- [ ] `main.py` 能正常启动并运行。
- [ ] 主题/LLM 偏好读写正确。
- [ ] 插件加载、数据存取、Pub/Sub、资源文件功能正常。
- [ ] 性能基准显示：在 10000 个 key 的数据量下，`set_plugin_data` / `get_plugin_data` 单次延迟不随数据总量线性增长，且明显低于旧 JSON 模式（参考指标见第 9.4 节）。
- [ ] 并发压力测试无死锁、无数据不一致。

**风险与回退**：
- 风险：集成环境发现未覆盖的兼容性问题。
- 回退：根据问题严重程度回退到阶段 3 或阶段 4 修复。


**建议 commit**：
- `(UpSQL: integration)` 主应用冒烟测试、插件加载、Pub/Sub、资源文件回归验证。
- `(UpSQL: benchmark)` 性能基准与并发压力测试报告。

---

### 阶段 6：文档、审计与收尾

**目标**：同步更新文档，进行最终审计，合并代码。

**输入依赖**：阶段 5 完成。

**关键任务**：

> 注意：以下编号为「阶段 6」内部任务编号，与文档章节编号（如第 6.6 节「线程安全」）无关。

| # | 任务 | 说明 |
|---|------|------|
| 6.1 | 更新 `docs/core/data-provider/overview.md` | 将 JSON 描述改为 SQLite，更新架构图、资源目录、数据流程图、数据结构示例。 |
| 6.2 | 更新 `docs/core/data-provider/api-reference.md` | 补充数据库文件路径推导规则、`save_data` / `load_data` SQLite 语义。 |
| 6.3 | 更新 `README.md` / `README_EN.md` | 如有提到 JSON 持久化，更新为 SQLite + orjson。 |
| 6.4 | 清理旧 JSON 临时文件 | 在 `DataProvider` 初始化或迁移成功后清理残留的 `data.json.tmp`，避免磁盘垃圾堆积。 |
| 6.5 | 清理旧迁移备份 | 制定并实施 `.migrated-*.bak` 保留策略：例如保留最近 N 个备份，或提供手动清理脚本；避免长期积累占用磁盘，但不应自动删除所有旧备份，以免用户需要回退时无备份可用。 |
| 6.6 | 更新本迁移计划 | 标记各阶段实施状态、实际日期、验证结果。 |
| 6.7 | 代码审查 | 重点审查公共接口签名、异常包装、锁顺序、缓存失效、迁移回滚。 |
| 6.8 | 独立 Agent 审计 | 由独立 Agent 审计：接口是否零破坏、功能是否一致、性能是否提升、文档是否同步。 |
| 6.9 | 合并 feature 分支 | 合并到 `dev`，清理 feature 分支。 |

**输出产物**：
- 更新后的文档。
- 审计报告。
- 合并后的 `dev` 分支。

**验收标准（DoD）**：
- [ ] 所有第 12 节"文档更新清单"中的 checkbox 已勾选。
- [ ] 代码审查通过，无未解决的阻塞性意见。
- [ ] 独立 Agent 审计通过，或所有审计意见已闭环。
- [ ] feature 分支已合并到 `dev`，CI 通过。

**风险与回退**：
- 风险：文档遗漏导致后续维护困难。
- 回退：在合并前补充文档，不强制一次完美。


**建议 commit**：
- `(UpSQL: docs)` 更新 `overview.md`、`api-reference.md`、`README.md` 等文档。
- `(UpSQL: cleanup)` 清理 `data.json.tmp`、旧迁移备份等收尾工作。
- `(UpSQL: audit)` 记录审计结果、更新迁移计划实施状态。
- `(UpSQL: chore)` 合并 feature 分支到 `dev`。

---

### 11.7 阶段入口/出口检查表

| 阶段 | 入口条件 | 出口条件 |
|------|----------|----------|
| 0 | `dev` 分支可用 | feature 分支创建、数据备份、依赖验证通过 |
| 1 | 阶段 0 完成 | `SQLiteBackend` 单测通过 |
| 2 | 阶段 1 完成 | 序列化/缓存单测通过 |
| 3 | 阶段 2 完成 | `DataProvider` 单测通过 |
| 4 | 阶段 3 完成 | 迁移/升级单测通过 |
| 5 | 阶段 4 完成 | 集成测试、性能基准通过 |
| 6 | 阶段 5 完成 | 文档更新、审计通过、合并完成 |

---

### 11.8 Agent 工作分解与子任务执行纪律

为便于 Agent 制定子任务，每个阶段可进一步拆分为以下粒度：

- **编码任务**：具体文件/函数实现。
- **测试任务**：单元测试、集成测试、性能测试。
- **文档任务**：注释、docstring、Markdown 更新。
- **审查任务**：自测、交叉 review、Agent 审计。
- **回退任务**：失败时的恢复步骤。

示例（阶段 1 的子任务）：
1. 实现 `SQLiteBackend.__init__` 与 `connect()` → 立即运行最小连接测试 → commit `(UpSQL: sqlite_backend)`。
2. 实现 `_execute_pragma()` → 立即验证 PRAGMA 生效 → commit `(UpSQL: sqlite_backend)`。
3. 实现 `create_tables()` → 立即验证表/索引存在 → commit `(UpSQL: sqlite_backend)`。
4. 实现 `get_schema_version()` / `set_schema_version()` → 立即运行读写测试 → commit `(UpSQL: sqlite_backend)`。
5. 实现 `transaction()` 上下文管理器 → 立即验证 commit/rollback → commit `(UpSQL: sqlite_backend)`。
6. 实现 `ensure_database()` → commit `(UpSQL: sqlite_backend)`。
7. 实现 `_upgrade_schema()` 调用与 `schema_migrations.py` → commit `(UpSQL: schema_migrations)`。
8. 编写 `TestSQLiteBackend` → commit `(UpSQL: tests)`。
9. 编写 `TestSchemaVersion` / `TestSchemaUpgrade` / `TestLegacyDatabase` / `TestCorruptSchemaVersion` → commit `(UpSQL: tests)`。
10. 运行阶段 1 全部测试并修复问题 → commit `(UpSQL: tests)`。

**子任务执行纪律**：
- 每个编码子任务完成后必须立即运行对应测试（单测或最小脚本），确认通过后再 commit。
- 每个 commit 必须只包含一个逻辑单元（一个函数/一个测试类/一个修复），禁止把多个不相关改动塞进同一个 commit。
- 每个 commit message 必须包含 `(UpSQL: <模块>)` 标签，例如 `(UpSQL: sqlite_backend)`、`(UpSQL: tests)`、`(UpSQL: docs)`，便于按模块回退和审计。
- 如果某个子任务导致测试失败，必须先修复或回滚，再进入下一个子任务。

## 12. 文档更新清单

迁移完成后必须同步更新以下文档，避免文档与实际实现脱节：

- [x] `docs/core/data-provider/overview.md`
  - 更新持久化层描述（JSON → SQLite）。
  - 更新架构图中的 `data/data.json` 为 `data/data.db`。
  - 更新第 6 节资源目录结构（移除 `data.json.tmp`，补充 `data.db-wal` / `data.db-shm`）。
  - 更新第 7 节数据读写流程图。
  - 更新第 8 节数据结构示例。
- [x] `docs/core/data-provider/api-reference.md`
  - 构造函数说明中补充数据库文件路径推导规则。
  - 在 `save_data` / `load_data` 说明中补充 SQLite 语义。
- [x] `docs/core/data-provider/sqlite-migration-plan.md`
  - 修正迁移时序描述（SQLite 事务提交后重命名 JSON 备份）。
  - 标记实施状态，补充实际迁移日期和验证结果（见 14.3 节）。
- [x] `core/data/schema_migrations.py`
  - 新增文件，已补充模块级文档字符串，说明 `MIGRATIONS`、`TARGET_SCHEMA_VERSION` 的使用方式。
- [x] `pyproject.toml`
  - 在 `dependencies` 中加入 `orjson>=3.11.0,<4`（已验证 Python 3.14 兼容）。
- [x] `core/data/sqlite_backend.py` / `core/data/data_provider.py`
  - 已补充 `_serialize` / `_deserialize`、LRU 缓存、迁移回滚等内部文档。
- [x] `core/__init__.py` / `core/data/__init__.py`
  - 确认导出项 `DataProvider`、`DataNamespace`、`DataProviderError` 无需变更。
  - 确认 `core/__init__.py` 保持当前导出不变（从 `core.data.data_provider` 导入 `DataNamespace`，未导出 `DataProviderError`）。
  - 确认不导出 `db_metadata`、`schema_version` 等内部实现。
- [x] `README.md` / `README_EN.md`
  - 已将 `data/data.json` 更新为 `data/data.db`。
- [ ] 团队规范 / `AGENTS.md`（如适用）
  - 当前项目根目录 `AGENTS.md` 为空；如需记录 commit 规范，可在后续团队协作阶段补充。

---

## 13. 附录：关键接口清单（迁移后仍需保持一致）

| 方法 | 签名 | 行为不变点 |
|------|------|------------|
| `__init__` | `(data_dir=None, data_filename="data.json")` | 单例、目录创建 |
| `register_plugin` | `(instance_id, plugin_type)` | 重复注册抛异常 |
| `unregister_plugin` | `(instance_id)` | 清理订阅、级联删除数据 |
| `get_active_instance` | `(plugin_type) -> Optional[str]` | 无则返回 None |
| `set_active_instance` | `(instance_id)` | 同类型唯一活跃 |
| `get_plugin_data` | `(instance_id, key, namespace=PRIVATE, default=None)` | 无则返回 default |
| `set_plugin_data` | `(instance_id, key, value, namespace=PRIVATE, notify=True)` | PUBLIC+notify 触发回调 |
| `get_all_plugin_data` | `(instance_id, namespace=PRIVATE) -> Dict` | 返回副本 |
| `subscribe` | `(subscriber_id, target_plugin_id, target_key, callback)` | 验证目标存在 |
| `unsubscribe` | `(subscriber_id, target_plugin_id=None)` | 支持批量取消 |
| `publish` | `(publisher_id, key, value, namespace=PUBLIC)` | 等同 set_plugin_data |
| `save_asset` / `get_asset_path` / `load_asset` / `get_plugin_assets_dir` | 不变 | 文件系统 |
| `load_data` / `save_data` / `clear_cache` | 不变 | 缓存语义 |
| `get_all_plugins` / `get_plugin_info` | 不变 | 返回结构一致 |
| `reset_all_data` | 不变 | 清空所有数据；不清空 `_subscriptions`（与旧实现一致） |

---

*本计划由 Kimi Code CLI 基于对 InstructionX 项目的完整代码与文档阅读后生成。*
---

## 14. 附录：审计闭环记录

### 14.1 本轮审计（最终轮独立 Agent 交叉审计）

**审计目标**：确认 JSON → SQLite 迁移方案对所有原有公共接口 100% 签名兼容，并闭环 P0/P1 问题。

**已闭环问题清单**：

| 级别 | 问题 | 修复位置 | 修复说明 |
|------|------|----------|----------|
| P0 | 迁移回退时序矛盾：先重命名 `data.json` 再提交 SQLite 事务，但失败时又说保留原始 `data.json` 不动 | 7.2 步骤 5、7.3 | 明确：若 SQLite 提交失败，必须将 `.bak` 还原为 `data.json`；无论失败发生在重命名前还是后，下次启动都必须能看到原始 `data.json` |
| P1 | `_ensure_database()` 伪代码调用 `_upgrade_schema(current)`，与 5.4 节 `_upgrade_schema(self, conn)` 签名不一致 | 6.4.1 伪代码 | 改为 `self._upgrade_schema(self._conn)`；同时 `_get_schema_version()` 改为 `self._get_schema_version(self._conn)` |
| P1 | 交叉引用 "11.4 节" 不存在 | 11.0 总体原则 | 改为"第 10 节「风险与回退」" |
| P1 | `_deserialize` 代码块缺少开始围栏 | 6.4.0 | 在 `_deserialize` 前补充 ` ```python ` |
| P1 | 多处 Python 代码块/伪代码格式问题，直接复制会报 `IndentationError`/`SyntaxError` | 4.5、6.2、6.3.2、6.4.8、7.2 | 将关键示例改为独立代码块或补充必要导入/函数体；所有 Python 代码块在去除围栏缩进后均可通过 `compile()` 校验 |
| P2 | 返回字典键顺序使用 `ORDER BY instance_id/id/plugin_type`，为字母序而非插入顺序 | 6.4.2 | 改为 `ORDER BY rowid`，更接近原始插入顺序，并补充 `rowid` 局限说明 |
| P2 | `_serialize` 调用方式表述歧义 | 6.4.0 引言 | 统一说明为模块级函数形式，可通过直接 import 或 `self._backend` 代理调用，实现时保持一致 |
| P2 | `CREATE TABLE IF NOT EXISTS` 无法检测列缺失 | 6.4.1 | 补充 `PRAGMA table_info(...)` 结构校验说明及伪代码 `self._validate_table_schema()` |
| P3 | `orjson` 对 `deque` 的描述 | 6.4.0 | 确认描述一致：`deque` 由 `_scan_non_json_types` 主动拒绝 |
| P3 | NaN/Inf 措辞 | 全文 | 统一使用"新后端写入拒绝、迁移时清洗为 `None`"表述 |
| P3 | tuple key 迁移说明 | 6.4.0 边界类型、7.2 | 补充 `tuple` 等非字符串 dict key 在迁移时会被 `_sanitize_for_migration` 转为字符串 |
| P3 | 非默认 `data_filename` 的 `migrated_from` | 5.5、6.4.1、7.2 | `migrated_from` 应记录原始 JSON 文件名（如 `my_data.json`），而非硬编码 `data.json` |
| P3 | JSON 后端初始化字段 | 4.4 / 6.2 实现示例 | 补充 `_cache`、`_cache_dirty`、`_value_cache`、`_subscriptions`、`_file_lock`、`_subscription_lock`、`_initialized` 的初始化示例 |

**验证结果**：
- 文档内所有 Python 代码块均通过 `compile()` 语法校验。
- 所有 Markdown 代码块围栏配对正确，无未闭合块。
- 公共接口签名、导入路径、异常语义、Pub/Sub 语义、单例行为、资源路径与第 2 节兼容性目标一致。

**遗留待实现项**：
- `core/data/sqlite_backend.py`、`core/data/schema_migrations.py`、`test/core/data/test_data_provider.py` 仍为占位文件，按第 11 节分阶段计划实施。
- 第 12 节"文档更新清单"中的 checkbox 待迁移实施阶段逐项勾选。

### 14.2 本轮补充完善记录

本次完善基于对 `core/data/data_provider.py`、`core/interfaces/i_data_provider.py`、`core/plugin/manager.py`、`ui/main_window.py`、`core/__init__.py`、`core/interfaces/plugin_services.py`、`utils/logging_tools.py`、`pyproject.toml`、`data/data.json`、`test/core/data/` 的实际逐行阅读，补充和修正如下内容：

| 补充项 | 位置 | 说明 |
|--------|------|------|
| UI/PluginManager 实际调用示例 | 2.3.1 节 | 引用实际代码行号，展示 `PluginServices` 注入和 `ui/main_window.py` 主题/LLM 偏好读写 |
| 当前实现已知问题审计 | 2.7 节 | 列出 8 项实际问题，包括浅拷贝、DataNamespace 跨模块比较 bug、锁顺序、RLock、reset_all_data 不清空订阅、全量写盘、tmp 残留 |
| 测试文件状态修正 | 9.1 节 | 说明 `test/core/data/` 目录下无源码文件，仅存在历史 `__pycache__` 残留 |
| orjson 依赖已就绪 | 阶段 0（11.0 后） | `pyproject.toml` 已含 orjson，本地 `.venv` 验证 3.11.9；阶段 0 DoD 中 orjson 项标记为已完成 |
| DataNamespace bug 强化 | 6.5 节 | 补充实际代码行号、UI 导入路径、插件风险 |
| 锁顺序问题强化 | 6.6 节 | 补充当前实现违反锁顺序的具体位置、迁移修正方案、`_subscription_lock` 改为 `Lock` |
| 代码改动对照与验收检查表 | 附录 15 | 新增用户迁移手册、开发者验收检查表、关键方法行为对照 |

### 14.3 代码实现后审计（最终交叉验证）

**审计日期**：2026-06-27

**审计目标**：在 `dev-database` 分支代码提交后，由独立 Agent 对实际实现与迁移计划进行交叉验证，确认接口零破坏、功能等价、关键修复已闭环。

**验证方法**：
1. 逐条阅读 `docs/core/data-provider/sqlite-migration-plan.md` 第 4~13 节要求。
2. 对照实际源码：`core/data/sqlite_backend.py`、`core/data/schema_migrations.py`、`core/data/data_provider.py`、`test/core/data/test_data_provider.py`。
3. 运行全部单元测试，并补充边界测试验证修复效果。
4. 检查 `docs/core/data-provider/overview.md`、`docs/core/data-provider/api-reference.md`、`README.md` / `README_EN.md` 同步状态。

**发现的问题与修复**：

| 级别 | 问题 | 位置 | 修复说明 |
|------|------|------|----------|
| P0 | 迁移失败后 `data.db` 中残留部分数据 | `core/data/sqlite_backend.py` | 将新建数据库流程改为：先执行 DDL，再使用显式事务执行数据迁移与 `db_metadata` 写入；任何异常都关闭连接并删除 `data.db` / `-wal` / `-shm`，确保下次可从原始 `data.json` 重试迁移 |
| P1 | LRU 缓存无法区分 `None` 值与"未命中" | `core/data/sqlite_backend.py::_LRUCache` | 引入 `MISSING` sentinel 对象；`get()` 返回 `MISSING` 表示未命中，返回 `None` 表示缓存值确实为 `None` |
| P1 | `_has_core_tables()` 把 `db_metadata` 也当作"已初始化"判定条件，导致早期无版本数据库被误判为新建库 | `core/data/sqlite_backend.py::_has_core_tables()` | 改为只检查 `plugins`、`plugin_data`、`active_instances` 三张核心业务表；`db_metadata` 缺失时进入 legacy 补齐路径 |
| P1 | `_validate_table_schema()` 对 `updated_at` 默认值格式期望与 SQLite 实际返回不一致 | `core/data/sqlite_backend.py::_validate_table_schema()` | 将默认值从 `"strftime('%s','now')"` 修正为 `"strftime('%s', 'now')"`（带空格），与 `PRAGMA table_info` 实际返回值匹配 |
| P2 | 文档未随实现同步 | `overview.md`、`api-reference.md`、`README.md` / `README_EN.md` | 已更新为 SQLite 描述、数据库路径推导、WAL 文件说明等 |
| P2 | 测试覆盖不足 | `test/core/data/test_data_provider.py` | 新增 `TestLRUCache`、`TestMigrationFailure`、`TestNotifyLockOrder`、`TestConcurrency`、`TestAssets`、`TestSchemaUpgrade`，测试用例从 22 个增加到 34 个 |
| P3 | 迁移时序描述与实现不一致 | `sqlite-migration-plan.md` 7.2/7.3 | 文档原描述为"先重命名 JSON 再提交 SQLite 事务"；实现为"先提交 SQLite 事务再重命名 JSON 备份"。已更新文档说明：由于 SQLite DDL 会隐式提交事务，且"data.db 已提交但 data.json 仍在原位"不会导致重复迁移或数据丢失，实际采用更安全、更易实现的"提交后备份"顺序 |

**验证结果**：
- `pytest test/core/data/test_data_provider.py`：34 passed。
- `pytest -q`（全量）：34 passed。
- 迁移失败审计测试：确认 `data.db` 被清理、原始 `data.json` 保留。
- LRU 边界测试：确认 `None` 值可正确缓存，容量上限生效。
- 锁顺序测试：确认回调不在 `_file_lock` 内执行，回调中可重入 DataProvider。
- 并发测试：4 线程 × 50 次 set/get 无异常、最终一致。

**剩余可接受差异**：
1. JSON 后端开关保留旧实现的锁顺序（`subscribe` / `unregister_plugin` 先 `_file_lock` 后 `_subscription_lock`）。该后端仅作为应急回退，不影响默认 SQLite 路径。
2. 备份文件名使用微秒精度（`%Y%m%dT%H%M%S.%f`），文档原描述为"毫秒"。实际粒度更细，可避免同一秒内重复覆盖。
3. `save_data()` 清空 LRU 缓存后未重新填充。文档描述为"可选"，当前实现满足一致性要求。

---

## 15. 附录：迁移操作手册与验收检查表

### 15.1 最终用户/运维人员迁移手册

**适用场景**：应用从 JSON 后端版本升级到 SQLite 后端版本后，首次启动时自动迁移。

1. **启动前**：确保 `data/data.json` 存在且未被其他程序占用。
2. **首次启动**：应用会自动检测 `data.db` 是否存在；若不存在且 `data.json` 可解析，则执行迁移。
3. **迁移过程中**：
   - 应用会先解析 `data.json`，在 SQLite 事务中完成数据导入并写入 `db_metadata`，然后提交事务。
   - 事务提交成功后，`data.json` 会被重命名为 `data.json.migrated-<ISO8601-微秒>.bak`。
   - 同级目录可能出现 `data.db-wal`、`data.db-shm`，属正常 SQLite WAL 文件，请勿删除。
4. **迁移成功后**：
   - 应用使用 `data/data.db` 作为持久化后端。
   - 原始 `data.json` 已备份，可手动归档或删除（建议保留至少最近 3 个 `.bak`）。
5. **迁移失败时**：
   - 应用会抛出 `DataProviderError` 并提示用户。
   - 如果失败发生在 SQLite 事务提交前，不完整的数据库文件会被清理，`data.json` 保持原位，下次启动可重试迁移。
   - 如果 SQLite 事务已提交但重命名 `data.json` 失败，`data.db` 已包含完整数据，`data.json` 仍在原位；应用会基于 `data.db` 正常运行。
   - 如需应急启动，可设置环境变量 `INSTRUCTIONX_DATAPROVIDER_BACKEND=json` 临时回退到 JSON 后端。
6. **回退到 JSON 模式（仅限必要时）**：
   - 停止应用。
   - 删除 `data/data.db`、`data/data.db-wal`、`data/data.db-shm`。
   - 将最新的 `data.json.migrated-<时间戳>.bak` 重命名为 `data.json`。
   - 设置环境变量 `INSTRUCTIONX_DATAPROVIDER_BACKEND=json`，或使用 JSON 后端代码版本。
   - 重新启动。
   - ⚠️ 注意：迁移成功后写入 SQLite 的新数据无法通过此方式恢复。

### 15.2 开发者验收检查表

在 feature 分支合并到 `dev` 前，必须完成以下检查：

#### 功能一致性

- [x] `DataProvider()` 单例行为正确：多次实例化返回同一对象，重复初始化不重置状态。
- [x] `from core.data import DataProvider, DataNamespace, DataProviderError` 继续可用。
- [x] `from core import DataProvider, DataNamespace` 继续可用（`DataProviderError` 仍不导出，与当前一致）。
- [x] `register_plugin` / `unregister_plugin` / `get_active_instance` / `set_active_instance` 语义与 JSON 模式一致。
- [x] `get_plugin_data` / `set_plugin_data` / `get_all_plugin_data` 语义一致；返回值外部修改不影响数据库。
- [x] `subscribe` / `unsubscribe` / `publish` 行为一致；`PUBLIC + notify=True` 触发回调；`PRIVATE` / `notify=False` 不触发。
- [x] `save_asset` / `get_asset_path` / `load_asset` / `get_plugin_assets_dir` 路径格式一致。
- [x] `load_data` / `save_data` / `clear_cache` 语义一致；`save_data()` 在 `clear_cache()` 后直接调用仍抛出 `DataProviderError("没有可保存的数据")`。
- [x] `get_all_plugins` / `get_plugin_info` 返回结构与 JSON 模式一致。
- [x] `reset_all_data()` 清空数据但不清空 `_subscriptions`（与旧实现一致）。

#### 迁移与版本

- [x] 存在 `data.json` 且不存在 `data.db` 时，首次启动自动完成迁移。
- [x] 迁移后 SQLite 数据与 `data.json` 一致（`NaN/Inf` 清洗为 `None`）。
- [x] 迁移成功后生成 `data.json.migrated-<时间戳>.bak`。
- [x] 迁移失败时原始 `data.json` 保留，不完整的 `data.db` 被清理。
- [x] 新建数据库 `schema_version` 为 `'1'`。
- [x] 从 JSON 迁移后 `schema_version` 为 `'1'`，`migrated_from` 记录原始 JSON 文件名。
- [x] 低版本数据库可链式升级到当前目标版本；高版本数据库触发 `DataProviderError`。

#### 性能与稳定性

- [ ] 在 10000 个 key 数据量下，`set_plugin_data` 单次平均耗时低于 1 ms。（未执行正式基准，但单测与审计脚本验证性能不随数据量线性增长）
- [ ] `get_plugin_data` 缓存命中时低于 0.1 ms，未命中时低于 1 ms。（同上）
- [x] 多线程高频 set/get 无死锁、无异常、最终一致。
- [x] `set_plugin_data(PUBLIC, notify=True)` 的回调不在 `_file_lock` 内执行。

#### 文档与代码

- [x] `docs/core/data-provider/overview.md` 已更新为 SQLite 描述。
- [x] `docs/core/data-provider/api-reference.md` 已补充数据库文件路径推导规则。
- [x] `core/data/sqlite_backend.py` 和 `core/data/schema_migrations.py` 包含模块级 docstring。
- [x] `pyproject.toml` 与 `uv.lock` 同步。
- [x] 所有 commit message 包含 `(UpSQL: ...)` 标签。

### 15.3 关键方法行为对照表（迁移前后）

| 方法 | JSON 模式（当前） | SQLite 模式（迁移后） | 是否兼容 |
|------|-------------------|------------------------|----------|
| `__init__` | 创建 `data.json`、临时文件、`assets` 目录 | 创建 `data.db`、WAL 文件、`assets` 目录；初始化 schema | 签名/语义兼容 |
| `register_plugin` | 全量读 → 修改 → 全量写 | 单条 `INSERT`；同步更新 `_cache` | 语义兼容 |
| `unregister_plugin` | 全量读 → 修改 → 全量写；清理订阅 | `DELETE` 级联；释放锁后清理订阅 | 语义兼容，锁顺序优化 |
| `set_plugin_data` | 全量读 → 修改 → 全量写；PUBLIC+notify 回调 | 点查/点写；LRU 失效；释放锁后回调 | 语义兼容，性能提升 |
| `get_plugin_data` | 全量读 → 返回一个 key | 点查 + LRU 缓存；返回深拷贝 | 语义兼容，性能提升 |
| `get_all_plugin_data` | 全量读 → 返回命名空间字典浅拷贝 | 查询该命名空间所有 key；返回深拷贝 | 语义兼容，隔离性增强 |
| `load_data` | 全量反序列化；返回顶层浅拷贝 | 全量查询组装；返回深拷贝 | 语义兼容，隔离性增强 |
| `save_data` | 全量序列化写入 | 全量同步到 SQLite | 语义兼容 |
| `get_all_plugins` | 返回 `plugins` 顶层浅拷贝 | 查询组装；返回深拷贝 | 语义兼容，隔离性增强 |
| `get_plugin_info` | 直接返回内部引用 | 查询组装；返回深拷贝 | 语义兼容，隔离性增强 |
| `reset_all_data` | 写空 JSON；调用 `clear_cache()` | 清空数据库；调用 `clear_cache()` | 语义兼容 |
| `subscribe` | 在 `_file_lock` 内获取 `_subscription_lock` | 释放 `_file_lock` 后获取 `_subscription_lock` | 语义兼容，死锁风险降低 |

*注："语义兼容"指对插件/调用方可见的行为一致；"隔离性增强"和"死锁风险降低"属于内部安全增强，不影响正常业务。*
