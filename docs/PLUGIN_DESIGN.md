# 插件设计说明

## 设计理念

插件系统遵循**关注点分离（Separation of Concerns）**的设计原则，将插件的 UI 界面与业务逻辑完全解耦，以提高代码的可维护性、可测试性和可复用性。

## 核心设计原则

1. **单一职责原则（SRP）**
   - `entrance.py` 只负责 UI 界面构建和用户交互
   - `service.py` 只负责业务逻辑实现

2. **低耦合高内聚**
   - UI 层不包含任何业务逻辑代码
   - 业务逻辑层不依赖任何 UI 组件

3. **可测试性**
   - 业务逻辑可以独立进行单元测试
   - UI 测试和逻辑测试互不影响

4. **可复用性**
   - Service 类可以在不同场景下复用
   - 业务逻辑可以脱离 UI 独立使用

## 插件架构设计

### 架构图

```
插件目录结构
├── __init__.py              # Python 包标识文件
├── entrance.py              # UI 界面入口
└── service.py               # 业务逻辑入口
```

### 模块关系

```
┌─────────────────────────────────────────┐
│           entrance.py (UI层)            │
│  ┌──────────────────────────────────┐   │
│  │ - UI 组件创建和布局                │  │
│  │ - 用户事件处理                      │ │
│  │ - 调用 Service 类方法               │ │
│  └──────────────┬─────────────────────┘ │
└─────────────────┼───────────────────────┘
                  │ 调用
                  ▼
┌─────────────────────────────────────────┐
│           service.py (逻辑层)           │
│  ┌──────────────────────────────────┐  │
│  │ - Service 类定义                   │  │
│  │ - 业务逻辑实现                      │  │
│  │ - 数据处理和转换                    │  │
│  └──────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

## 文件结构说明

### 目录结构

```
InstructionX/
├── plugin/                        # 官方插件目录
│   └── text_formatting/          # 文本格式化插件示例
│       ├── __init__.py          # Python 包标识
│       ├── entrance.py          # UI 界面入口
│       └── service.py           # 业务逻辑入口
└── custom_plugin/                 # 第三方插件目录
    └── color_converter/          # 颜色转换插件示例
        ├── __init__.py          # Python 包标识
        ├── entrance.py          # UI 界面入口
        └── service.py           # 业务逻辑入口
```

### 文件职责

#### 1. `__init__.py`
- **作用**：标识目录为 Python 包
- **内容**：可以为空，或包含包级别的导出

```python
# __init__.py
"""
插件名称
"""

# 可选：导出主要内容
# from .service import Service
```

#### 2. `service.py` - 业务逻辑入口
- **职责**：实现所有业务逻辑和功能
- **特点**：
  - 不依赖任何 Qt UI 组件
  - 只包含纯 Python 代码
  - 提供清晰的 API 接口
  - 易于单元测试

```python
"""
插件名称 - 业务逻辑实现
"""

class Service:
    """服务类，提供插件功能的实现"""
    
    def method_name(self, param: str) -> str:
        """
        方法功能描述
        
        Args:
            param: 参数说明
            
        Returns:
            返回值说明
        """
        # 业务逻辑实现
        return result
```

#### 3. `entrance.py` - UI 界面入口
- **职责**：构建 UI 界面和处理用户交互
- **特点**：
  - 实现 `IPlugin` 接口
  - 创建和管理 UI 组件
  - 处理用户事件
  - 调用 Service 类方法实现功能
  - 不包含任何业务逻辑代码

```python
"""
插件名称 - UI 界面入口
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout
from core.plugin.plugin_interface import IPlugin
from .service import Service

class PluginName(IPlugin):
    """插件类"""
    
    @property
    def plugin_name(self) -> str:
        return "插件名称"
    
    def get_widget(self, parent=None, data_provider=None) -> QWidget:
        # 创建服务实例
        service = Service()
        
        # 构建 UI
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        
        # UI 组件创建
        # ...
        
        # 事件处理中调用服务方法
        button.clicked.connect(
            lambda: output.setText(service.method_name(input.text()))
        )
        
        return widget
```

## 完整示例

### 示例 1：文本格式化插件

#### `service.py`
```python
"""
文本格式化服务 - 功能实现
"""

class Service:
    """文本格式化服务类，提供文本格式化功能的实现"""
    
    def to_uppercase(self, text: str) -> str:
        """
        将文本转换为大写
        
        Args:
            text: 输入文本
            
        Returns:
            大写文本
        """
        return text.upper()
    
    def to_lowercase(self, text: str) -> str:
        """
        将文本转换为小写
        
        Args:
            text: 输入文本
            
        Returns:
            小写文本
        """
        return text.lower()
```

#### `entrance.py`
```python
"""
文本格式化插件 - 官方插件示例
提供常用的文本格式化功能
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, 
    QPushButton, QGroupBox, QLineEdit
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt
from core.plugin.plugin_interface import IPlugin
from .service import Service


class TextFormattingPlugin(IPlugin):
    """文本格式化插件"""
    
    @property
    def plugin_name(self) -> str:
        return "文本\n格式化"
    
    @property
    def skill_icon(self) -> QIcon:
        from PySide6.QtWidgets import QApplication
        return QApplication.style().standardIcon(
            QApplication.style().StandardPixmap.SP_FileIcon
        )
    
    @property
    def skill_description(self) -> str:
        return "提供文本格式化工具"
    
    def get_widget(self, parent=None, data_provider=None) -> QWidget:
        # 创建服务实例
        service = Service()
        
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        
        # 标题
        title = QLabel("文本格式化工具")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        # 转大写功能
        uppercase_group = QGroupBox("转换为大写")
        uppercase_layout = QVBoxLayout()
        
        uppercase_input = QLineEdit()
        uppercase_input.setPlaceholderText("输入文本...")
        uppercase_layout.addWidget(uppercase_input)
        
        uppercase_btn = QPushButton("转换为大写")
        # 调用服务方法
        uppercase_btn.clicked.connect(
            lambda: uppercase_input.setText(
                service.to_uppercase(uppercase_input.text())
            )
        )
        uppercase_layout.addWidget(uppercase_btn)
        
        uppercase_group.setLayout(uppercase_layout)
        layout.addWidget(uppercase_group)
        
        # 转小写功能
        lowercase_group = QGroupBox("转换为小写")
        lowercase_layout = QVBoxLayout()
        
        lowercase_input = QLineEdit()
        lowercase_input.setPlaceholderText("输入文本...")
        lowercase_layout.addWidget(lowercase_input)
        
        lowercase_btn = QPushButton("转换为小写")
        # 调用服务方法
        lowercase_btn.clicked.connect(
            lambda: lowercase_input.setText(
                service.to_lowercase(lowercase_input.text())
            )
        )
        lowercase_layout.addWidget(lowercase_btn)
        
        lowercase_group.setLayout(lowercase_layout)
        layout.addWidget(lowercase_group)
        
        layout.addStretch()
        return widget
```

### 示例 2：颜色转换插件

#### `service.py`
```python
"""
颜色转换服务 - 功能实现
"""

class Service:
    """颜色转换服务类，提供颜色格式转换功能的实现"""
    
    def hex_to_rgb(self, hex_str: str) -> str:
        """
        将 HEX 颜色格式转换为 RGB 格式
        
        Args:
            hex_str: HEX 颜色字符串（如 #FF5733 或 FF5733）
            
        Returns:
            RGB 格式字符串（如 rgb(255, 87, 51)），如果格式无效则返回错误信息
        """
        # 移除 # 前缀
        if hex_str.startswith('#'):
            hex_str = hex_str[1:]
        
        # 验证长度
        if len(hex_str) != 6:
            return "无效的 HEX 格式"
        
        try:
            # 转换为 RGB
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
            return f"rgb({r}, {g}, {b})"
        except ValueError:
            return "无效的 HEX 格式"
```

#### `entrance.py`
```python
"""
颜色转换插件 - 第三方插件示例
提供颜色格式转换功能
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, 
    QPushButton, QGroupBox, QLineEdit
)
from PySide6.QtCore import Qt
from core.plugin.plugin_interface import IPlugin
from .service import Service


class ColorConverterPlugin(IPlugin):
    """颜色转换插件"""
    
    @property
    def plugin_name(self) -> str:
        return "颜色转换"
    
    @property
    def skill_description(self) -> str:
        return "HEX/RGB 颜色格式转换"
    
    def get_widget(self, parent=None, data_provider=None) -> QWidget:
        # 创建服务实例
        service = Service()
        
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        
        # 标题
        title = QLabel("颜色格式转换工具")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        # HEX 转 RGB
        hex_group = QGroupBox("HEX 转 RGB")
        hex_layout = QVBoxLayout()
        
        hex_input = QLineEdit()
        hex_input.setPlaceholderText("输入 HEX 颜色 (如 #FF5733)")
        hex_layout.addWidget(hex_input)
        
        rgb_output = QLineEdit()
        rgb_output.setReadOnly(True)
        rgb_output.setPlaceholderText("RGB 结果")
        hex_layout.addWidget(rgb_output)
        
        hex_btn = QPushButton("转换")
        # 调用服务方法
        hex_btn.clicked.connect(
            lambda: rgb_output.setText(
                service.hex_to_rgb(hex_input.text().strip())
            )
        )
        hex_layout.addWidget(hex_btn)
        
        hex_group.setLayout(hex_layout)
        layout.addWidget(hex_group)
        
        layout.addStretch()
        return widget
```

## 设计优势

### 1. 关注点分离
- UI 代码和业务逻辑代码完全分离
- 每个文件职责明确，易于理解

### 2. 可维护性
- 修改 UI 时不需要触碰业务逻辑
- 修改业务逻辑时不需要改动 UI 代码
- 降低代码维护成本

### 3. 可测试性
- Service 类的方法可以独立进行单元测试
- 不需要启动 UI 框架即可测试业务逻辑
- 提高测试覆盖率

### 4. 可复用性
- Service 类可以在其他插件中复用
- 业务逻辑可以脱离 UI 独立使用
- 提高代码复用率

### 5. 可扩展性
- 新功能只需在 Service 类中添加方法
- UI 可以轻松调用新方法
- 支持功能的无缝扩展

## 最佳实践

### Service 类设计规范

1. **方法命名**
   - 使用动词开头，清晰表达功能
   - 例如：`to_uppercase()`, `hex_to_rgb()`

2. **参数类型注解**
   - 使用 Python 类型注解
   - 提高代码可读性和 IDE 支持

3. **文档字符串**
   - 为每个方法添加 docstring
   - 包含参数说明和返回值说明

4. **错误处理**
   - 在方法内部处理异常
   - 返回友好的错误信息
   - 不要让异常传播到 UI 层

5. **无状态设计**
   - 方法应该是无状态的（纯函数）
   - 避免依赖实例变量
   - 便于测试和复用

### entrance.py 设计规范

1. **服务实例化**
   - 在 `get_widget()` 方法开始时创建 Service 实例
   - 不要在类级别实例化

2. **UI 构建**
   - 只包含 UI 组件的创建和布局
   - 不包含任何业务逻辑代码

3. **事件处理**
   - 使用 lambda 函数调用服务方法
   - 保持代码简洁清晰

4. **资源管理**
   - 及时释放不再使用的资源
   - 避免内存泄漏

5. **错误提示**
   - 在 UI 层显示友好的错误信息
   - 不要直接显示原始异常

## 常见问题

### Q1: 为什么要分离 entrance.py 和 service.py？

A: 这种分离设计带来以下好处：
- UI 和逻辑解耦，提高代码质量
- 便于单独测试业务逻辑
- 业务逻辑可以在其他场景复用
- 降低维护成本

### Q2: Service 类可以是静态方法吗？

A: 可以，但建议使用实例方法，因为：
- 实例方法更灵活，便于未来扩展
- 可以添加实例变量存储状态
- 更符合面向对象设计原则

### Q3: 一个插件可以有多个 Service 类吗？

A: 可以。如果插件功能复杂，可以按功能模块划分多个 Service 类：
```python
from .services.format_service import FormatService
from .services.convert_service import ConvertService

format_service = FormatService()
convert_service = ConvertService()
```

### Q4: Service 类可以调用数据库或网络接口吗？

A: 可以。Service 类是处理业务逻辑的地方，完全可以：
- 访问数据库
- 调用网络 API
- 处理文件 I/O
- 执行任何必要的业务操作

### Q5: 如何处理 Service 类中的异常？

A: 推荐做法：
```python
class Service:
    def method(self, param: str) -> str:
        try:
            # 业务逻辑
            return result
        except SpecificException as e:
            # 返回友好的错误信息
            return f"错误：{e}"
        except Exception:
            # 返回通用错误信息
            return "操作失败，请重试"
```

## 迁移指南

如果您有旧版本的插件（只有一个 entrance.py 文件），可以按照以下步骤迁移：

### 步骤 1：创建 service.py
```python
# 将 business logic 从 entrance.py 提取到 service.py
class Service:
    def method_name(self, param):
        # 业务逻辑代码
        pass
```

### 步骤 2：重构 entrance.py
```python
from .service import Service

class Plugin(IPlugin):
    def get_widget(self, parent=None, data_provider=None):
        service = Service()
        
        # UI 代码
        button.clicked.connect(
            lambda: output.setText(service.method_name(input.text()))
        )
```

### 步骤 3：测试
- 运行程序验证功能正常
- 测试各种边界情况
- 确保没有引入新问题

## 技术支持

如有问题或建议，请：
- 查看示例插件代码
- 阅读相关文档
- 提交 Issue 到项目仓库