# GitHub 插件安装器

> 从 GitHub 仓库安装插件的完整说明

---

## 1. 概述

`GitHubPluginInstaller` 是插件系统的扩展组件，负责插件安装：既支持从 GitHub 仓库**远程安装**，
也支持**本地插件包**（zip）安装。

**文件位置**: `core/plugin/github_plugin_installer.py`
（本地包识别逻辑独立在 `core/plugin/package_discovery.py`，纯文件系统实现、可单测）

**核心功能**:
- 支持单插件仓库（仓库根目录有 `IXPlugin.json`）
- 支持多插件仓库（仓库根目录有 `IXRepo.json`）
- **本地插件包自动识别**：自动判断 zip 是单插件还是插件集，适配 GitHub 下载的仓库压缩包
  （`repo-<branch>/`）、用户二次打包、`__MACOSX` 等任意层嵌套；插件集可勾选后**一次装完**
- 自动判定安装目录（KKPIP-Tech → plugin/，其他 → custom_plugin/）
- 后台下载和安装，不阻塞 UI

---

## 2. 插件描述文件规范

### 2.1 IXPlugin.json（单个插件描述）

适用于单插件仓库，放在仓库根目录。

```json
{
  "id": "my-awesome-plugin",
  "name": "My Awesome Plugin",
  "version": "release.1.0.0",
  "main": "entrance.py",
  "description": "一个强大的插件",
  "author": "John Doe",
  "homepage": "https://github.com/user/my-awesome-plugin",
  "keywords": ["text", "utility"],
  "dependencies": {
    "requests": ">=2.25.0"
  }
}
```

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 插件唯一标识符（字母、数字、下划线、连字符，允许大写字母） |
| `name` | string 或 object | 是 | 插件显示名称；支持多语言字典形式 `{"zh": "...", "en": "..."}`（`I18nFieldValue = Union[str, Dict[str, str]]`，经 `resolve_i18n_field()` 解析） |
| `version` | string | 是 | 版本号，格式：`<类型>.<大>.<小>.<补丁>`，如 `release.1.0.0` |
| `main` | string | 是 | 插件入口文件路径，当前必须固定为 `entrance.py`；框架加载器只识别该文件名 |
| `description` | string 或 object | 否 | 插件简短描述；同样支持多语言字典形式（同 `name`） |
| `author` | string | 否 | 插件作者 |
| `homepage` | string | 否 | 插件主页 URL |
| `keywords` | array | 否 | 关键词列表 |
| `dependencies` | object | 否 | Python 依赖，key 为包名，value 为版本约束 |

> **当前实现说明**：上表 `id`（`^[a-zA-Z0-9_-]+$`）与 `version`（`^(release|pre-release|beta|alpha|internal)\.\d+\.\d+\.\d+$`）约束由 `core/plugin/package_discovery.py` 的 `validate_descriptor()` 做**代码级正则硬校验**；安装器的 `GitHubPluginInstaller.validate_descriptor()` 直接委托同一实现（本地包识别与安装校验共用一套规则，避免两处分叉）。格式不符会被拒绝安装；在**本地插件集**场景下仅该插件标记为不可安装，不影响其余插件。

### 2.2 IXRepo.json（多插件仓库索引）

适用于多插件仓库，放在仓库根目录。

```json
{
  "plugins": [
    {
      "path": "plugin-a",
      "id": "plugin-a",
      "name": "Plugin A"
    },
    {
      "path": "plugin-b",
      "id": "plugin-b",
      "name": "Plugin B"
    }
  ]
}
```

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `plugins` | array | 是 | 插件列表 |
| `plugins[].path` | string | 是 | 插件相对于仓库根目录的路径 |
| `plugins[].id` | string | 是 | 插件唯一标识符 |
| `plugins[].name` | string 或 object | 是 | 插件显示名称；同 IXPlugin.json 的 `name`，支持多语言字典形式 |

---

## 3. 核心数据结构

### 3.1 InstallResult

```python
@dataclass
class InstallResult:
    success: bool = False
    message: str = ""
    plugin_id: Optional[str] = None
    plugin_name: Optional[str] = None
    relation: str = ""  # new / upgrade / downgrade / reinstall

    @staticmethod
    def ok(plugin_id: str, plugin_name: str, message: str = "安装成功") -> "InstallResult":
        """构造成功结果"""
        ...

    @staticmethod
    def error(message: str) -> "InstallResult":
        """构造失败结果"""
        ...
```

### 3.2 PluginInfo

```python
@dataclass
class PluginInfo:
    plugin_id: str
    name: I18nFieldValue                # str 或 Dict[str, str]（多语言）
    version: str
    main: str
    description: Optional[I18nFieldValue] = None   # str 或 Dict[str, str]（多语言）
    author: Optional[str] = None
    homepage: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    dependencies: Dict[str, str] = field(default_factory=dict)
    path: str = ""  # 相对于仓库根目录的路径

# I18nFieldValue = Union[str, Dict[str, str]]
#   - str：所有语言共用同一文案（旧形式，向后兼容）
#   - Dict[str, str]：按当前语言 → 默认语言 → 字典首个值的顺序解析
# 解析入口：core.i18n.ixplugin_i18n.resolve_i18n_field(value, language, default_language)
# 解析时机：PluginRegistry 回填路径按默认语言解析；安装对话框展示层按当前语言解析
```

### 3.3 RepoInspectionResult

```python
@dataclass
class RepoInspectionResult:
    repo_type: str  # "multi", "single", 或 "invalid"
    plugins: List[PluginInfo] = field(default_factory=list)
    error_message: Optional[str] = None
```

### 3.4 LocalInstallPlan

本地插件包中**单个插件**的安装计划，由 `inspect_local_package()` 产出，供安装对话框展示与勾选。

```python
@dataclass
class LocalInstallPlan:
    candidate: PluginCandidate          # 识别层候选（见 package_discovery.PluginCandidate）
    relation: str = "new"               # new / upgrade / downgrade / reinstall
    prev_version: str = ""              # 已安装版本（未安装时为空串）
    target_scope: str = "thirdparty"    # official / thirdparty
    default_selected: bool = True       # 有索引时仅索引声明项为 True
```

### 3.5 LocalPackageInspection

```python
@dataclass
class LocalPackageInspection:
    kind: str                                   # single / multi / invalid
    plans: List[LocalInstallPlan] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error: str = ""                             # kind == invalid 时的中文诊断信息
    has_index: bool = False                     # 包内是否存在 IXRepo.json
```

> **识别层的值对象**（纯文件系统，定义在 `core/plugin/package_discovery.py`）：
> `PluginCandidate`（候选插件：`descriptor_id`/`name`/`version`/`main`/`description`/`dependencies`/
> `rel_path`（相对包根路径，`""` 表示插件就在包根）/`valid`/`error`/`declared_in_index`）与
> `PackageInspection`（`kind`/`candidates`/`warnings`/`error`/`has_index`）。

---

## 4. 核心 API

### 4.1 inspect_repository()

```python
def inspect_repository(self, github_url: str) -> RepoInspectionResult:
    """
    检查仓库返回可安装的插件列表

    Args:
        github_url: GitHub 仓库 URL

    Returns:
        RepoInspectionResult: 包含仓库类型和插件列表
    """
```

**检测优先级**:
1. 优先检查 `IXRepo.json`（多插件仓库索引）
2. 其次检查 `IXPlugin.json`（单插件仓库）
3. 都无 → 返回 `repo_type="invalid"`

### 4.2 install_from_url()

```python
def install_from_url(
    self,
    github_url: str,
    selected_plugins: List[str] = None,
    official_dir: Path = None,
    thirdparty_dir: Path = None,
    progress_callback=None
) -> List[InstallResult]:
    """
    从 GitHub URL 安装插件

    安装过程中会自动检查并安装插件依赖（通过 DependencyManager）。

    Args:
        github_url: GitHub 仓库 URL
        selected_plugins: 要安装的插件路径列表（多插件仓库时）
                        为 None 时安装所有插件
                        （与 IXRepo.json 的 path 比较前双方均会去掉
                        尾斜杠规范化，"a" 与 "a/" 视为同一路径）
        official_dir: 官方插件目录
        thirdparty_dir: 第三方插件目录
        progress_callback: 可选的进度回调函数，接收消息字符串

    Returns:
        List[InstallResult]: 每个插件的安装结果
    """
```

### 4.3 parse_github_url()

```python
def parse_github_url(self, url: str) -> Optional[Tuple[str, str]]:
    """
    解析 GitHub URL，返回 (owner, repo)

    支持格式:
    - https://github.com/owner/repo
    - https://github.com/owner/repo.git
    - https://github.com/owner/repo/releases
    - git@github.com:owner/repo.git
    """
```

### 4.4 validate_descriptor()

```python
def validate_descriptor(self, descriptor: Dict[str, Any]) -> Tuple[bool, str]:
    """
    验证插件描述文件格式

    检查必需字段（id, name, version, main）是否存在，
    并验证 version 格式和 id 格式。

    规则实现位于 core.plugin.package_discovery.validate_descriptor，
    本方法仅做委托（本地包识别与安装校验共用同一套规则）。

    Args:
        descriptor: 从 IXPlugin.json 解析的字典

    Returns:
        (is_valid, error_message): 验证是否通过及错误信息
    """
```

### 4.5 inspect_local_package()

```python
def inspect_local_package(self, zip_path) -> LocalPackageInspection:
    """
    识别本地插件包：单插件 / 插件集 / 无效，并预演各插件的安装关系

    只读操作：解压到临时目录 → 识别 → 清理；不写入插件目录、不改注册表。

    Args:
        zip_path: 本地插件包路径（.zip）

    Returns:
        LocalPackageInspection: 分类结果、逐个插件的安装计划与警告；
        kind == "invalid" 时 error 含可诊断的具体原因
    """
```

- 识别与安装**各自解压一次**（换取接口无状态、避免跨调用持有临时目录造成泄漏）；插件包通常仅数 MB，成本可接受；
- 每个计划含安装关系（新装/升级/降级/重装）、目标范围（官方/第三方）与默认勾选建议；
- 识别失败时给出**可诊断**信息：已扫描目录数与层数、跳过的噪声目录数、是否发现索引，
  以及「请确认压缩包内包含 IXPlugin.json；若为插件集，建议在仓库根提供 IXRepo.json」的指引。

### 4.6 install_from_zip()

```python
def install_from_zip(
    self,
    zip_path,
    target_dir: Path = None,
    progress_callback=None,
    selected_plugins: Optional[List[str]] = None
) -> List[InstallResult]:
    """
    从本地 zip 插件包安装/升级/降级插件（支持单插件与插件集）

    Args:
        zip_path: 本地插件包路径
        target_dir: 目标目录；为 None 时逐个自动判定
        progress_callback: 进度回调（逐插件调用）
        selected_plugins: 只安装这些插件（按包内相对路径或插件 id 匹配，
            两侧均忽略首尾斜杠）；None 表示安装全部可安装候选

    Returns:
        List[InstallResult]: 每个插件一条结果（顺序与识别顺序一致）；
        包无法识别时为单条错误结果；未选中任何插件时为空列表
    """
```

- 单插件包：行为与历史版本一致（结果是单元素列表）；
- 插件集包：**逐个安装**，每个插件独立成败互不阻断（依赖安装失败只影响该插件）；
- 不可安装的候选（描述文件缺失/非法、ID 重复、索引声明的目录不存在）被自动跳过；
- 注册表登记 `source_type="local_zip"`、`source_path=<包内相对路径>`，便于排查与后续比对；
- 本方法**只新增可选参数**，旧调用 `install_from_zip(zip_path)` 语义不变。

### 4.7 本地插件包识别规则矩阵

对应 `core/plugin/package_discovery.py` 的识别逻辑；验证见 `scripts/smoke_plugin_management.py`
（第 8–11 节）与 `test/core/plugin/test_package_discovery.py`（test 分支）。

| zip 内容形态 | 判定 | 结果 |
|---|---|---|
| 根目录 / `repo-main/` / `外层/repo-main/` 含 `IXPlugin.json` | single | 直接安装 |
| `repo-main/` 下并列多个插件目录（GitHub 下载的插件集仓库） | multi | 勾选后一次装完 |
| `repo-main/IXRepo.json` + 索引项 | multi | 索引驱动：顺序按索引，索引项默认勾选 |
| 索引 + 未声明的插件目录 | multi | 未声明项仍作为候选，但默认**不**勾选并给出警告 |
| `repo-main/packages/plugins/a` 等多层嵌套 | multi | 递归扫描命中 |
| `__MACOSX/`、`.git/`、`node_modules/`、`_`/`.` 前缀目录 | — | 噪声目录跳过，不影响判定 |
| 插件目录内部再嵌套插件目录 | — | 命中描述文件即停止下潜，不误判 |
| 包内两个目录 `id` 相同 | multi | 保留首个（索引项优先），其余标注"重复"且不可安装 |
| 描述文件缺 `id/name/version/main` 或格式非法 | — | 该候选不可安装并显示原因，其余照常 |
| 索引声明的目录不存在 / 索引路径越界 | multi/invalid | 逐条报错：目录不存在 / 路径越出包根已拒绝 |
| 空包 / 无任何插件 | invalid | 诊断信息 + 指引 |

**扫描上限**（防病态压缩包）：单次识别最多遍历 `MAX_SCAN_DIRS = 20000` 个目录、下潜
`MAX_DISCOVERY_DEPTH = 6` 层、穿过包装层 `MAX_WRAPPER_DEPTH = 6` 层；超限时截断并在
`warnings` 中提示"可能存在未扫描到的插件"。

---

## 5. 安装目录规则

| GitHub 组织/用户 | 目标目录 |
|----------------|---------|
| `https://github.com/KKPIP-Tech/*` | `project_root/plugin/` |
| 其他所有仓库 | `project_root/custom_plugin/` |

---

## 6. 使用示例

### 6.1 检查仓库

```python
from core.plugin.github_plugin_installer import GitHubPluginInstaller

installer = GitHubPluginInstaller()
result = installer.inspect_repository("https://github.com/user/my-plugin")

if result.repo_type == "invalid":
    print(f"无效仓库: {result.error_message}")
elif result.repo_type == "single":
    plugin = result.plugins[0]
    print(f"单插件: {plugin.name} v{plugin.version}")
elif result.repo_type == "multi":
    print(f"多插件仓库，共 {len(result.plugins)} 个插件:")
    for p in result.plugins:
        print(f"  - {p.name} ({p.path})")
```

### 6.2 安装插件

```python
from core.plugin.github_plugin_installer import GitHubPluginInstaller

installer = GitHubPluginInstaller()

# 安装单插件
results = installer.install_from_url("https://github.com/user/my-plugin")

# 安装多插件（选择性安装）
results = installer.install_from_url(
    "https://github.com/user/multi-plugin-repo",
    selected_plugins=["plugin-a", "plugin-b"]  # 只安装这两个
)

for r in results:
    if r.success:
        print(f"✓ {r.plugin_name}: {r.message}")
    else:
        print(f"✗ {r.message}")
```

---

## 7. 对话框组件

**文件位置**: `ui/dialog/github_plugin_install_dialog.py`

`GitHubPluginInstallDialog` 提供图形界面的安装流程：

```
┌─────────────────────────────────────────────┐
│  从 GitHub 安装插件                           │
├─────────────────────────────────────────────┤
│  GitHub URL: [________________________] [检查] │
│                                             │
│  ── 插件信息 ──────────────────────────────  │
│  将安装到: 第三方插件目录 (custom_plugin/)    │
│                                             │
│  单插件模式:                                 │
│  ┌─────────────────────────────────────┐   │
│  │ 名称: My Awesome Plugin               │   │
│  │ 版本: release.1.0.0                   │   │
│  │ 描述: 一个强大的插件...                │   │
│  └─────────────────────────────────────┘   │
│                                             │
│  多插件模式:                                 │
│  ☑ plugin-a  (Plugin A)                    │
│  ☑ plugin-b  (Plugin B)                    │
│  ☐ plugin-c  (Plugin C)  ← 未选中          │
│                                             │
│              [取消]  [安装]                  │
└─────────────────────────────────────────────┘
```

**信号**:
```python
plugin_installed = Signal(list)  # List[InstallResult]
```

**使用方式**:
```python
from ui.dialog.github_plugin_install_dialog import GitHubPluginInstallDialog

dialog = GitHubPluginInstallDialog(parent_window)
dialog.plugin_installed.connect(self._on_plugin_installed)
dialog.exec()
```

### 7.1 本地插件包安装对话框

**文件位置**: `ui/dialog/local_package_install_dialog.py`
**入口**: 插件管理对话框 →「安装本地插件包」按钮（`PluginManagementDialog._on_install_zip()`）

```
┌──────────────────────────────────────────────────┐
│  本地插件包安装                                     │
├──────────────────────────────────────────────────┤
│  collection.zip                        [选择压缩包…] │
│  识别结果：插件集（未找到 IXRepo.json，由目录扫描识别） │
│  ┌────────────────────────────────────────────┐  │
│  │ ☑ 演示插件五 (v release.1.0.0)              │  │
│  │    一个演示插件                              │  │
│  │    id: demo-five · 包内路径 demo-five ·       │  │
│  │    新安装 · 第三方目录                        │  │
│  ├────────────────────────────────────────────┤  │
│  │ ☑ 演示插件六 (v release.1.0.0)              │  │
│  └────────────────────────────────────────────┘  │
│  已选 2 / 共 2（0 项不可安装）      [全选][取消全选] │
├──────────────────────────────────────────────────┤
│  [进度]  正在安装…          [安装所选]  [关闭]      │
└──────────────────────────────────────────────────┘
```

**行为要点**:

| 场景 | 界面表现 |
|------|---------|
| 单插件包 | 一行插件信息（名称/版本/关系/目标目录/依赖），默认勾选，直接安装 |
| 插件集包 | 多行勾选列表 + 全选/取消全选 + 计数行；**一次装完**所选插件 |
| 有 `IXRepo.json` | 按索引识别与排序；索引项默认勾选，未声明项默认不勾选并标注 |
| 无任何插件 | 切到诊断页：显示扫描统计与指引，安装按钮不可用 |
| 部分插件不可安装 | 该行置灰并显示原因（缺字段/版本号非法/ID 重复/索引目录不存在），其余可正常安装 |
| 安装中 | 进度条可见、按钮禁用、禁止关闭窗口（运行中关闭会先请求中断并等待线程结束） |

**实现约定**: 识别与安装都在后台 `QThread` 中执行；界面只消费 `LocalInstallPlan`
（不写业务逻辑），安装完成发 `plugin_installed` 信号交给调用方刷新插件列表。

**信号与用法**:

```python
from ui.dialog.local_package_install_dialog import LocalPackageInstallDialog

dialog = LocalPackageInstallDialog(parent_window, installer=installer)
dialog.plugin_installed.connect(lambda results: self._refresh_after_change())
dialog.exec()
# 也可直接驱动识别（便于自动化验证）：
dialog.start_inspect("/path/to/package.zip")
```

---

## 8. 与现有系统的整合

### 8.1 模块定位

- 新增 `GitHubPluginInstaller` 类，不修改现有 `PluginManager`
- 新增 `GitHubPluginInstallDialog` UI 组件

### 8.2 模块关联

| 组件 | 依赖关系 |
|------|---------|
| `GitHubPluginInstaller` | 依赖 `PluginManager` 获取 `official_plugin_dir` 和 `thirdparty_plugin_dir` |
| `GitHubPluginInstallDialog` | 依赖 `GitHubPluginInstaller` 进行仓库检查和安装 |
| 主窗口 | 依赖 `GitHubPluginInstallDialog` 提供 UI |

### 8.3 数据流转

```
用户输入 URL
    ↓
GitHubPluginInstallDialog._on_check_repo()
    ↓
GitHubPluginInstaller.inspect_repository()
    ↓ (GitHub API)
返回 RepoInspectionResult
    ↓
显示插件信息
    ↓
用户点击安装
    ↓
GitHubPluginInstallDialog._on_install()
    ↓
GitHubPluginInstaller.install_from_url()
    ↓ (下载 ZIP，解压，复制到目标目录)
返回 List[InstallResult]
    ↓
发送 plugin_installed 信号
    ↓
主窗口._on_github_plugin_installed()
    ↓
PluginManager.reload_plugins()   # 重新扫描目录加载新插件
    ↓
SkillsPanel.load_skills_from_manager()   # 按分组+顺序重新渲染
```

> 安装成功后新插件**立即可见**，无需重启应用。

### 8.4 菜单入口

- 安装：**编辑 → 从 GitHub 安装插件...**
- 管理（升级/降级/卸载/分组/排序）：**编辑 → 插件管理...**（`PluginManagementDialog`）

---

## 9. 升级 / 降级与卸载

- **版本注册表**：每次安装成功后，安装器将插件的版本、来源（GitHub URL / 本地 zip）、安装时间写入 `config/plugin_registry.json`（以插件 UUID 为键）；老版本插件在启动时自动回填。
- **升级/降级**：
  - GitHub 来源插件：插件管理对话框「检查更新 / 升级 / 降级…」列出仓库 Release 版本（通过 Contents API 读取各 tag 的 `IXPlugin.json` 版本号），任选版本安装；
  - 本地插件包：「安装本地插件包…」上传 zip，自动解析包内 `IXPlugin.json` 版本号，识别为升级/降级/重装并提示；
  - 覆盖安装沿用 `.bak` 备份回滚机制，并保留原插件 UUID（排序、分组、数据不受影响）。
- **卸载**：插件管理对话框「卸载…」，官方与第三方插件均可卸载；可选同时删除插件数据（DataProvider）。卸载会清理插件目录、UUID 文件、排序/分组/注册表记录、API/MCP 注册与 `sys.modules` 缓存。
- **pip 依赖**：安装/升级时自动安装缺失依赖（优先 uv，回退 pip）；卸载时**不自动卸载依赖**（可能被其他插件使用）。
- **GitHub Token**：设置环境变量 `INSTRUCTIONX_GITHUB_TOKEN` 可提升 API 限流阈值并支持私有仓库。

---

## 10. 相关文档

**插件系统内部**：
- [插件系统概述](overview.md)
- [IPlugin 接口](iplugin.md)（`GitHubPluginInstaller` 安装后由 `PluginManager` 加载 `IPlugin` 实例）
- [PluginManager](plugin-manager.md)（安装完成后调用 `uninstall_plugin()` 删除）
- [插件开发指南](plugin-development.md)（被安装的插件必须遵守的开发约定）

**相关子系统**：
- [MCP 协议模块概述](../mcp/overview.md)（`IXRepo.json` / `IXPlugin.json` 描述的插件如何注册为 MCP 工具）
- [DataProvider 概述](../data-provider/overview.md)（安装/卸载时 `PluginManager` 同步注册/注销 DataProvider 命名空间）

**UI 集成**：
- [对话框组件](../../ui/dialogs.md)（`GitHubPluginInstallDialog` 调 `GitHubPluginInstaller` 后台安装）
- [主窗口](../../ui/main-window.md)（安装完成后刷新技能面板）
