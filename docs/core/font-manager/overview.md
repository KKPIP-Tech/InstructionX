# 字体子系统概述

> FontManager 的架构设计、公开 API 与插件集成方式

---

## 1. 概述

`FontManager` 是 InstructionX 的框架级字体子系统，负责字体的安装、卸载、注册表持久化与系统字体回退。**框架本身不捆绑任何第三方字体**——所有字体均由用户在字体管理对话框中安装，或由插件经 API 安装。

**模块位置**: `core/font/`

**模式**: 单例模式（`FontManager._instance` + `get_font_manager()` 访问器）

**核心功能**:
- 字体安装 / 卸载（复制到 `data/fonts/`，注册进 QFontDatabase）
- 注册表持久化（`data/fonts/fonts.json`，原子写，启动时惰性恢复）
- 应用级字体注册（进程内生效，不写系统字体目录）
- 字体可用性检查与带回退链的家族名解析

---

## 2. 模块结构

```
core/font/
├── __init__.py       # 对外导出 FontManager / get_font_manager / FontRecord / FontInstallError
├── font_record.py    # FontRecord dataclass（frozen, slots）：字体注册记录数据模型
├── exceptions.py     # FontInstallError：字体安装失败异常
└── manager.py        # FontManager 单例 + get_font_manager() 访问器
```

支持安装的字体格式由常量 `SUPPORTED_SUFFIXES = (".ttf", ".otf", ".ttc")` 定义（`core/font/manager.py`）。

---

## 3. FontRecord 数据模型

每条 `FontRecord` 对应一个经框架安装到 `data/fonts/` 的字体文件（`core/font/font_record.py`）。

```python
@dataclass(frozen=True, slots=True)
class FontRecord:
    font_id: str        # 字体标识（字体文件名去扩展名，安装时由文件名生成）
    family: str         # Qt 字体家族名（注册后从 QFontDatabase 读取的真实名称）
    style: str          # 字体样式名（如 Regular / Bold）
    filename: str       # data/fonts/ 目录下的字体文件名
    source: str         # 安装来源（"user" 表示用户在字体管理窗口安装，插件安装时为插件 id）
    installed_at: str   # 安装时间（ISO 8601 字符串）
```

提供 `to_dict()` 序列化与 `from_dict()` 反序列化（必需字段缺失时抛 `KeyError`），用于注册表持久化。

---

## 4. FontManager 公开 API

### 4.1 install_font(path, source="user") -> FontRecord

安装字体文件：复制到 `data/fonts/` 并注册进 `QFontDatabase`。

| 参数 | 类型 | 说明 |
|------|------|------|
| `path` | `str` | 字体文件路径（.ttf/.otf/.ttc） |
| `source` | `str` | 安装来源（`"user"` 或插件 id），默认 `"user"` |

**返回**: 安装成功的 `FontRecord`；同一 `font_id`（文件名去扩展名）已安装时直接返回既有记录，不重复复制。

**异常**: `FontInstallError` —— 文件不存在、格式不支持、复制失败、Qt 注册失败或注册表写入失败时抛出。

### 4.2 uninstall_font(font_id) -> bool

卸载字体：从 `QFontDatabase` 移除、删除 `data/fonts/` 下的文件、更新注册表。

| 参数 | 类型 | 说明 |
|------|------|------|
| `font_id` | `str` | 字体标识（`FontRecord.font_id`） |

**返回**: 是否成功卸载；字体不存在时返回 `False`。

### 4.3 list_fonts() -> list[FontRecord]

返回全部已安装字体的记录列表。

### 4.4 installed_families() -> list[str]

返回框架安装字体的家族名列表（`FontRecord.family`）。

### 4.5 is_available(family) -> bool

检查字体家族是否可用：**框架安装 ∪ 系统字体**（后者经 `QFontDatabase.families()` 判断）。

### 4.6 resolve_family(requested, fallbacks=None) -> str

按回退链解析字体家族名，**保证返回值始终是一个当前可用的家族名**。

| 参数 | 类型 | 说明 |
|------|------|------|
| `requested` | `str` | 期望使用的字体家族名 |
| `fallbacks` | `list[str] \| None` | 可选的回退家族名列表（按优先级排列） |

**回退顺序**: 请求字体 → `fallbacks` 列表 → `QFont().defaultFamily()`（系统默认字体）。

### 4.7 get_font(family, point_size=0, weight=Normal, fallbacks=None) -> QFont

构造带回退机制的 `QFont`（家族名为 `resolve_family` 的实际解析结果）。

| 参数 | 类型 | 说明 |
|------|------|------|
| `family` | `str` | 期望的字体家族名（不可用时自动回退） |
| `point_size` | `int` | 字号（磅值），`<=0` 时保持默认 |
| `weight` | `QFont.Weight` | 字重，默认 `QFont.Weight.Normal` |
| `fallbacks` | `list[str] \| None` | 可选的回退家族名列表 |

---

## 5. 存储与注册机制

### 5.1 注册表存储格式

字体文件复制存储到 `data/fonts/`，注册表为 `data/fonts/fonts.json`（schema v1，顶层 `version` + `fonts` 数组）：

```json
{
    "version": 1,
    "fonts": [
        {
            "font_id": "SmileySans-Oblique",
            "family": "SmileySans-Oblique",
            "style": "",
            "filename": "SmileySans-Oblique.otf",
            "source": "user",
            "installed_at": "2026-08-01T10:00:00"
        }
    ]
}
```

注册表写入为**原子写**（临时文件 + `os.replace`，见 `FontManager._save_registry`），避免写入中断产生半个文件；注册表缺失或损坏时按空注册表运行，不阻断启动（记 error 日志）。

### 5.2 应用级注册

字体经 `QFontDatabase.addApplicationFont` 注册：**仅在进程内生效，不写入操作系统字体目录**，不需要管理员权限，卸载（`removeApplicationFont` + 删除文件）后无系统残留。

### 5.3 惰性加载与启动恢复

首次访问任意 API 时经 `_ensure_loaded()` 惰性加载注册表并重新注册全部字体（`FontManager._register_all`）；**字体文件缺失的记录自动剔除**并记 warning 日志。QFontDatabase 的应用字体 id 每次注册动态分配，不参与持久化。

---

## 6. 回退机制

`resolve_family` / `get_font` 的回退链：

```mermaid
flowchart TD
    A[请求字体家族 requested] --> B{框架安装或系统可用？}
    B -->|是| C[返回该家族]
    B -->|否| D{fallbacks 列表中还有候选？}
    D -->|有，逐一检查| B
    D -->|全部不可用| E[QFont().defaultFamily<br/>系统默认字体]
```

插件侧无需自行判断字体是否存在——`get_font` 保证返回一个可用的 `QFont`。

---

## 7. 插件用法

### 7.1 通过 PluginServices 注入（推荐）

`PluginServices` 末尾新增 `font_manager` 字段（`core/interfaces/plugin_services.py`），由 `PluginManager._create_plugin_services()` 注入 `get_font_manager()`。该字段**无降级保护、始终注入**（同 `logger`）：

```python
class MyPlugin(IPlugin):
    def __init__(self, services: PluginServices | None = None):
        super().__init__()
        self._font_manager = services.font_manager if services else None

    def _create_widget(self):
        label = QLabel("示例文本")
        font = self._font_manager.get_font("得意黑", point_size=16)
        label.setFont(font)  # 未安装时自动回退系统默认字体
        return label
```

### 7.2 直接获取单例

```python
from core.font import get_font_manager

font_manager = get_font_manager()

# 安装字体（source 传插件 id，便于追溯来源）
record = font_manager.install_font("C:/path/to/font.otf", source=self.plugin_id)

# 可用性检查与回退解析
if font_manager.is_available("SmileySans-Oblique"):
    ...
family = font_manager.resolve_family("得意黑", fallbacks=["Microsoft YaHei"])
```

---

## 8. 字体管理对话框

框架提供图形化管理入口 `FontManagerDialog`（`ui/dialog/font_manager_dialog.py`，主窗口「编辑 → 字体管理...」打开）：

- 左栏（280px）：搜索框 + 字体列表，分「已安装字体」（框架管理，来自 `FontRecord`）与「系统字体」（`QFontDatabase.families()`，只读）两个分组；
- 右栏：示例文本编辑 + 字号调节（8-72，默认 24）+ 实时预览卡片 + 解析结果提示（回退时显示「字体 X 不可用，已回退到系统字体：Y」）；
- 底部：「安装字体...」（多选文件对话框，过滤 .ttf/.otf/.ttc）/「卸载」（仅选中已安装分组时可用，需确认）/「关闭」。

详见 [对话框组件文档](../../ui/dialogs.md)。

---

## 9. 冒烟验证

`scripts/smoke_font_manager.py` 为无网冒烟脚本，验证链路：安装（含非法格式/文件缺失/重复安装）→ 查询 → 回退解析 → 注册表持久化（单例重置后恢复）→ 卸载清理 → `PluginServices.font_manager` 注入字段存在性。

```powershell
.venv\Scripts\python.exe scripts/smoke_font_manager.py
```

> 注意：冒烟脚本以 Windows 系统字体（`C:/Windows/Fonts/` 下的 msyh/simhei/simsun）作为安装来源（仅复制不修改），需要 `QApplication` 实例（`QFontDatabase` 依赖）。

---

## 10. 相关文档

- [接口层概述](../interfaces/overview.md)（PluginServices 字段清单）
- [对话框组件](../../ui/dialogs.md)（FontManagerDialog）
- [插件开发指南](../plugin-system/plugin-development.md)
- [主窗口](../../ui/main-window.md)（菜单入口）
