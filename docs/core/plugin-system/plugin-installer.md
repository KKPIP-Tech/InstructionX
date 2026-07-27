# GitHub 插件安装器

> 从 GitHub 仓库安装插件的完整说明

---

## 1. 概述

`GitHubPluginInstaller` 是插件系统的扩展组件，负责从 GitHub 仓库远程安装插件。

**文件位置**: `core/plugin/github_plugin_installer.py`

**核心功能**:
- 支持单插件仓库（仓库根目录有 `IXPlugin.json`）
- 支持多插件仓库（仓库根目录有 `IXRepo.json`）
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
| `name` | string | 是 | 插件显示名称 |
| `version` | string | 是 | 版本号，格式：`<类型>.<大>.<小>.<补丁>`，如 `release.1.0.0` |
| `main` | string | 是 | 插件入口文件路径，当前必须固定为 `entrance.py`；框架加载器只识别该文件名 |
| `description` | string | 否 | 插件简短描述 |
| `author` | string | 否 | 插件作者 |
| `homepage` | string | 否 | 插件主页 URL |
| `keywords` | array | 否 | 关键词列表 |
| `dependencies` | object | 否 | Python 依赖，key 为包名，value 为版本约束 |

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
| `plugins[].name` | string | 是 | 插件显示名称 |

---

## 3. 核心数据结构

### 3.1 InstallResult

```python
@dataclass
class InstallResult:
    success: bool
    message: str = ""
    plugin_id: Optional[str] = None
    plugin_name: Optional[str] = None
```

### 3.2 PluginInfo

```python
@dataclass
class PluginInfo:
    plugin_id: str
    name: str
    version: str
    main: str
    description: Optional[str] = None
    author: Optional[str] = None
    homepage: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    dependencies: Dict[str, str] = field(default_factory=dict)
    path: str = ""  # 相对于仓库根目录的路径
```

### 3.3 RepoInspectionResult

```python
@dataclass
class RepoInspectionResult:
    repo_type: str  # "multi", "single", 或 "invalid"
    plugins: List[PluginInfo] = field(default_factory=list)
    error_message: Optional[str] = None
```

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

    Args:
        descriptor: 从 IXPlugin.json 解析的字典

    Returns:
        (is_valid, error_message): 验证是否通过及错误信息
    """
```

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

## 10. 升级 / 降级与卸载

- **版本注册表**：每次安装成功后，安装器将插件的版本、来源（GitHub URL / 本地 zip）、安装时间写入 `config/plugin_registry.json`（以插件 UUID 为键）；老版本插件在启动时自动回填。
- **升级/降级**：
  - GitHub 来源插件：插件管理对话框「检查更新 / 升级 / 降级…」列出仓库 Release 版本（通过 Contents API 读取各 tag 的 `IXPlugin.json` 版本号），任选版本安装；
  - 本地插件包：「安装本地插件包…」上传 zip，自动解析包内 `IXPlugin.json` 版本号，识别为升级/降级/重装并提示；
  - 覆盖安装沿用 `.bak` 备份回滚机制，并保留原插件 UUID（排序、分组、数据不受影响）。
- **卸载**：插件管理对话框「卸载…」，官方与第三方插件均可卸载；可选同时删除插件数据（DataProvider）。卸载会清理插件目录、UUID 文件、排序/分组/注册表记录、API/MCP 注册与 `sys.modules` 缓存。
- **pip 依赖**：安装/升级时自动安装缺失依赖（优先 uv，回退 pip）；卸载时**不自动卸载依赖**（可能被其他插件使用）。
- **GitHub Token**：设置环境变量 `INSTRUCTIONX_GITHUB_TOKEN` 可提升 API 限流阈值并支持私有仓库。

---

## 9. 相关文档

- [插件系统概述](overview.md)
- [PluginManager](plugin-manager.md)
- [插件开发指南](plugin-development.md)
- [对话框组件](../../ui/dialogs.md)

---

*本文档由 Claude Code 自动生成*
