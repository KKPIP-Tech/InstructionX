# DependencyManager 插件依赖管理器

> 插件依赖检查和自动安装模块

---

## 1. 概述

`DependencyManager` 负责检查插件依赖是否满足，并在需要时自动安装缺失的 Python 包。

**文件位置**: `core/plugin/dependency_manager.py`

**核心功能**:
- 检查插件依赖是否已满足
- 获取缺失的依赖包列表
- 自动安装缺失的依赖（通过 pip）
- 支持版本约束检查（如 `>=2.25.0`）

---

## 2. 核心组件

### 2.1 DependencyCheckResult

依赖检查结果数据类。

```python
@dataclass
class DependencyCheckResult:
    satisfied: bool     # 所有依赖是否已满足
    missing: List[str]   # 缺失的依赖包名列表（不含版本约束）
```

### 2.2 DependencyInstallResult

依赖安装结果数据类。

```python
@dataclass
class DependencyInstallResult:
    success: bool                          # 安装是否成功
    message: str = ""                      # 结果消息
    failed_packages: List[str] = None       # 安装失败的包名列表
```

---

## 3. API 参考

### 3.1 check_dependencies()

检查依赖是否满足。

```python
def check_dependencies(self, dependencies: Dict[str, str]) -> DependencyCheckResult
```

**参数**:
- `dependencies`: 依赖字典，key 为包名，value 为版本约束
  - 例如: `{"requests": ">=2.25.0", "numpy": ""}`

**返回**:
- `DependencyCheckResult`: 包含 `satisfied`（是否满足）和 `missing`（缺失列表）

**示例**:
```python
from core.plugin.dependency_manager import DependencyManager

dep_mgr = DependencyManager()
result = dep_mgr.check_dependencies({"requests": ">=2.25.0", "numpy": ""})
print(f"依赖满足: {result.satisfied}")
print(f"缺失: {result.missing}")
```

### 3.2 get_missing_dependencies()

获取缺失的依赖包名列表。

```python
def get_missing_dependencies(self, dependencies: Dict[str, str]) -> List[str]
```

**参数**:
- `dependencies`: 依赖字典

**返回**:
- 缺失的包名列表（不含版本约束）

**示例**:
```python
missing = dep_mgr.get_missing_dependencies({"requests": ">=2.25.0", "numpy": ""})
print(f"需要安装: {missing}")  # ['requests', 'numpy']
```

### 3.3 install_dependencies()

安装缺失的依赖。

```python
def install_dependencies(
    self,
    dependencies: Dict[str, str],
    callback: Optional[Callable[[str], None]] = None
) -> DependencyInstallResult
```

**参数**:
- `dependencies`: 依赖字典，key 为包名，value 为版本约束
- `callback`: 可选的进度回调，接收安装消息字符串

**返回**:
- `DependencyInstallResult`: 安装结果

**示例**:
```python
def progress_callback(message):
    print(f"[安装进度] {message}")

result = dep_mgr.install_dependencies(
    {"requests": ">=2.25.0", "numpy": ""},
    callback=progress_callback
)
print(f"安装结果: {result.message}")
```

---

## 4. 版本约束支持

### 4.1 支持的约束格式

| 约束 | 示例 | 说明 |
|------|------|------|
| `>=` | `>=2.25.0` | 大于等于 |
| `>` | `>2.25.0` | 大于 |
| `<=` | `<=2.25.0` | 小于等于 |
| `<` | `<2.25.0` | 小于 |
| `==` | `==2.25.0` | 等于 |
| `!=` | `!=2.25.0` | 不等于 |
| 空字符串 | `""` | 仅检查包是否存在 |

### 4.2 版本比较规则

- 版本号按点分数字比较（如 `2.26.0` > `2.25.0`）
- 自动忽略预发布版本后缀（如 `2.26.0rc1` → `2.26.0`）

---

## 5. 与 GitHub 插件安装器的集成

`DependencyManager` 由 `GitHubPluginInstaller` 自动使用，在安装插件时自动检查和安装依赖。

实际集成发生在 `GitHubPluginInstaller._install_plugin_dir()` 方法中（简化示意）：

```python
from .dependency_manager import DependencyManager

# 在 _install_plugin_dir 方法内部
dependencies = descriptor.get("dependencies", {})
if dependencies:
    dep_mgr = DependencyManager()
    check_result = dep_mgr.check_dependencies(dependencies)
    if not check_result.satisfied:
        # 报告进度
        if progress_callback:
            progress_callback(f"正在安装缺失依赖...")
        # 安装缺失依赖
        install_result = dep_mgr.install_dependencies(dependencies)
        if not install_result.success:
            return InstallResult.error(f"依赖安装失败: {install_result.message}")
        if progress_callback:
            progress_callback("依赖安装完成")
```

---

## 6. 使用示例

### 6.1 检查单个插件依赖

```python
from core.plugin.dependency_manager import DependencyManager

dep_mgr = DependencyManager()

# 定义插件依赖
dependencies = {
    "requests": ">=2.25.0",
    "numpy": "",
    "pandas": ">=1.5.0",
}

# 检查依赖
result = dep_mgr.check_dependencies(dependencies)
if not result.satisfied:
    print(f"缺失依赖: {result.missing}")
    # 安装缺失依赖
    install_result = dep_mgr.install_dependencies(dependencies)
    print(install_result.message)
else:
    print("所有依赖已满足")
```

### 6.2 完整安装流程（带进度回调）

```python
from core.plugin.dependency_manager import DependencyManager

dep_mgr = DependencyManager()

def on_progress(message):
    print(f"[安装进度] {message}")

dependencies = {
    "requests": ">=2.25.0",
    "beautifulsoup4": ">=4.9.0",
}

result = dep_mgr.install_dependencies(dependencies, callback=on_progress)

if result.success:
    print("依赖安装成功！")
else:
    print(f"部分依赖安装失败: {result.failed_packages}")
```

---

## 7. 相关文档

- [GitHub 插件安装器](plugin-installer.md)
- [插件开发指南](plugin-development.md)
- [PluginManager](plugin-manager.md)

---

*本文档由 Claude Code 自动生成*
