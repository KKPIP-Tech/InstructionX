# ILogger 接口

> 日志记录的抽象接口，用于依赖注入

---

## 1. 概述

`ILogger` 定义了日志记录的抽象接口。插件和核心服务通过此接口进行日志记录，而非直接依赖 `LoggerManager` 实现。

**文件位置**: `utils/i_logger.py`（通过 `core/interfaces/__init__.py` 重导出）

**推荐导入**:
```python
from core.interfaces import ILogger  # 推荐
# 或通过具体实现
from utils.logging_tools import LoggerManager
```

---

## 2. 接口方法

### 2.1 info

```python
@abstractmethod
def info(self, name: str, message: str) -> None:
    """记录信息日志"""
    pass
```

**参数**:
- `name`: 调用方模块名称（用于日志分组）
- `message`: 日志消息内容

---

### 2.2 debug

```python
@abstractmethod
def debug(self, name: str, message: str) -> None:
    """记录调试日志"""
    pass
```

**参数**:
- `name`: 调用方模块名称
- `message`: 日志消息内容

---

### 2.3 warning

```python
@abstractmethod
def warning(self, name: str, message: str) -> None:
    """记录警告日志"""
    pass
```

**参数**:
- `name`: 调用方模块名称
- `message`: 日志消息内容

---

### 2.4 error

```python
@abstractmethod
def error(self, name: str, message: str) -> None:
    """记录错误日志"""
    pass
```

**参数**:
- `name`: 调用方模块名称
- `message`: 日志消息内容

---

### 2.5 critical

```python
@abstractmethod
def critical(self, name: str, message: str) -> None:
    """记录严重错误日志"""
    pass
```

**参数**:
- `name`: 调用方模块名称
- `message`: 日志消息内容

---

## 3. 重要说明

### 3.1 name 参数的作用

所有 `ILogger` 方法均包含 `name` 参数（调用方模块名），用于在日志中标识消息来源。这与 `LoggerManager` 的日志方法保持一致。

```python
# 使用示例
logger = services.logger  # 获取注入的 ILogger 实例
logger.info("MyPlugin", "插件初始化完成")
logger.error("MyPlugin", "连接失败: timeout")
```

### 3.2 与 LoggerManager 的关系

- **`ILogger`**：抽象接口，定义日志 API 契约
- **`LoggerManager`**：`ILogger` 的具体实现类

插件通过 `PluginServices.logger` 获取注入的日志实例，而非直接实例化 `LoggerManager`。

### 3.3 LoggerManager 扩展方法

以下方法仅存在于 `LoggerManager` 实现中，**不属于 `ILogger` 接口契约**：

#### log

`log(level, module_name, message)` 提供了动态级别指定方式。

```python
# LoggerManager 独有方法（非 ILogger 接口方法）
logger.log('WARNING', 'MyModule', '警告信息')
```

#### get_logger

`get_logger()` 返回底层的 `logging.Logger` 实例，供需要直接操作 Python 标准日志系统的场景使用。

```python
# 获取底层 logger 实例
py_logger = logger.get_logger()
py_logger.handlers  # 访问日志处理器
```

### 3.4 日志等级

| 方法 | 等级 | 典型用途 |
|------|------|---------|
| `debug` | DEBUG | 开发调试信息 |
| `info` | INFO | 一般运行信息 |
| `warning` | WARNING | 警告信息（不影响运行） |
| `error` | ERROR | 错误信息（影响功能） |
| `critical` | CRITICAL | 严重错误（可能导致崩溃） |

---

## 4. 使用示例

### 4.1 在插件中使用

```python
from core.plugin.plugin_interface import IPlugin
from utils.logging_tools import LoggerManager

class MyPlugin(IPlugin):
    def _create_widget(self, parent=None, data_provider=None):
        # 直接获取 logger 实例（LoggerManager 为线程安全单例）
        logger = LoggerManager()

        logger.info("MyPlugin", "开始创建 UI")

        # ... 创建 UI ...

        logger.info("MyPlugin", "UI 创建完成")
```

### 4.2 错误记录

```python
from utils.logging_tools import LoggerManager

class MyPlugin(IPlugin):
    def __init__(self):
        self.logger = LoggerManager()

    def some_operation(self):
        try:
            result = risky_function()
            self.logger.info("MyPlugin", f"操作成功: {result}")
        except Exception as e:
            self.logger.error("MyPlugin", f"操作失败: {e}")
```

---

## 5. 相关文档

- [接口层概述](overview.md)
- [PluginServices](./overview.md)
- [日志工具](../../utils/logging-tools.md)
