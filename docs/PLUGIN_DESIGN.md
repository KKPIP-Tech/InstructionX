# 插件设计说明

## 设计理念

插件系统遵循**关注点分离（Separation of Concerns）**的设计原则，将插件的 UI 界面、业务逻辑与插件元数据完全解耦，以提高代码的可维护性、可测试性和可复用性。

## 核心设计原则

1. **单一职责原则（SRP）**
   - `entrance.py` 只负责 UI 界面构建和用户交互
   - `service.py` 只负责业务逻辑实现
   - `information.py` 只负责插件元数据和配置信息

2. **低耦合高内聚**
   - UI 层不包含任何业务逻辑代码
   - 业务逻辑层不依赖任何 UI 组件
   - 元数据层与实现层分离

3. **可测试性**
   - 业务逻辑可以独立进行单元测试
   - UI 测试和逻辑测试互不影响

4. **可复用性**
   - Service 类可以在不同场景下复用
   - 业务逻辑可以脱离 UI 独立使用
   - 插件信息可以被 MCP 和其他系统读取

5. **可扩展性**
   - 支持多种图标类型
   - 支持丰富的插件元数据
   - 便于系统集成和自动化管理

## 插件架构设计

### 架构图

```
插件目录结构
├── __init__.py              # Python 包标识文件
├── entrance.py              # UI 界面入口
├── service.py               # 业务逻辑入口
└── information.py          # 插件元数据和配置
```

### 模块关系

```
┌─────────────────────────────────────────┐
│       information.py (元数据层)         │
│  ┌──────────────────────────────────┐   │
│  │ - 插件版本信息                    │  │
│  │ - 开发者信息                      │  │
│  │ - 插件描述                        │  │
│  │ - 图标配置                        │  │
│  │ - API 接口定义                    │  │
│  └──────────────────────────────────┘  │
└─────────────────────────────────────────┘
         ▲                     ▲
         │ 供读取              │ 供读取
         │                     │
┌────────┴─────────────────────┴────────┐
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
│       ├── service.py           # 业务逻辑入口
│       └── information.py       # 插件元数据
└── custom_plugin/                 # 第三方插件目录
    └── color_converter/          # 颜色转换插件示例
        ├── __init__.py          # Python 包标识
        ├── entrance.py          # UI 界面入口
        ├── service.py           # 业务逻辑入口
        └── information.py       # 插件元数据
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

#### 4. `information.py` - 插件元数据
- **职责**：提供插件的完整元数据信息
- **特点**：
  - 实现 `IPluginInfo` 接口
  - 包含版本、开发者信息
  - 定义图标配置
  - 描述插件功能和 API
  - 可被 MCP 系统读取
  - **类名自动查找**：系统会自动查找实现了 `IPluginInfo` 接口的类，类名可以使用任意命名

**重要说明：插件信息类的命名规则**

系统会自动扫描 `information.py` 文件中所有实现了 `IPluginInfo` 接口的类，因此类名可以自由命名。推荐的命名规范是：

```python
# 推荐命名：{插件名}PluginInfo
class TextFormattingPluginInfo(IPluginInfo):  # 文本格式化插件
    ...

class CodeFormatterPluginInfo(IPluginInfo):  # 代码格式化插件
    ...

class ColorConverterPluginInfo(IPluginInfo):  # 颜色转换插件
    ...

class ImageCompressorPluginInfo(IPluginInfo):  # 图片压缩插件
    ...

class UnitConverterPluginInfo(IPluginInfo):  # 单位转换插件
    ...
```

**自动查找机制说明：**

插件系统使用以下逻辑查找插件信息类：
1. 动态加载 `information.py` 模块
2. 遍历模块中所有的类定义
3. 查找实现了 `IPluginInfo` 接口且不是 `IPluginInfo` 本身的类
4. 如果找到，就使用该类作为插件信息源

因此，您可以使用任何类名，只要它实现了 `IPluginInfo` 接口即可。系统会自动识别正确的类。

```python
"""
插件名称 - 插件元数据
"""

from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon
from typing import Dict, Any, Optional

class PluginNamePluginInfo(IPluginInfo):
    """插件元数据类"""
    
    @property
    def version(self) -> PluginVersion:
        """插件版本"""
        return PluginVersion.from_string("release.1.0.0")
    
    @property
    def developer(self) -> str:
        """开发者名称"""
        return "开发者名称"
    
    @property
    def developer_email(self) -> str:
        """开发者邮箱"""
        return "developer@example.com"
    
    @property
    def developer_website(self) -> str:
        """开发者网站"""
        return "https://example.com"
    
    @property
    def is_free(self) -> bool:
        """是否免费"""
        return True
    
    @property
    def description(self) -> str:
        """插件详细描述"""
        return """
        插件功能描述
        """
    
    @property
    def service_api(self) -> Dict[str, Any]:
        """Service API 定义"""
        return {
            "method_name": {
                "description": "方法描述",
                "parameters": {
                    "param": {
                        "type": "str",
                        "description": "参数描述",
                        "required": True
                    }
                },
                "returns": {
                    "type": "str",
                    "description": "返回值描述"
                }
            }
        }
    
    @property
    def skill_icon(self) -> PluginIcon:
        """插件图标配置"""
        return PluginIcon.builtin("SP_FileIcon")
    
    @property
    def skill_description(self) -> str:
        """插件简短描述"""
        return "插件功能简介"
    
    @property
    def tags(self) -> Optional[list[str]]:
        """插件标签"""
        return ["tag1", "tag2", "tag3"]
    
    @property
    def dependencies(self) -> Optional[Dict[str, str]]:
        """依赖项"""
        return None
```

## 插件元数据详解

### 必需属性

#### 1. `version` - 版本号
使用 `PluginVersion` 类定义版本号，格式为 `type.major.minor.patch`：
- `type`: 版本类型（`release`, `beta`, `alpha`, `dev`）
- `major`: 主版本号
- `minor`: 次版本号
- `patch`: 补丁号

```python
PluginVersion.from_string("release.1.0.0")
```

#### 2. `developer` - 开发者名称
插件开发者的名称或团队名称。

```python
def developer(self) -> str:
    return "KKPIP-Tech"
```

#### 3. `developer_email` - 开发者邮箱
用于联系的邮箱地址。

```python
def developer_email(self) -> str:
    return "support@example.com"
```

#### 4. `developer_website` - 开发者网站
开发者的官方网站或项目地址。

```python
def developer_website(self) -> str:
    return "https://github.com/KKPIP-Tech/InstructionX"
```

#### 5. `is_free` - 是否免费
标识插件是否为免费软件。

```python
def is_free(self) -> bool:
    return True  # 或 False
```

#### 6. `description` - 详细描述
插件的详细功能描述，用于文档和 MCP 系统。可以使用多行字符串。

```python
def description(self) -> str:
    return """
    文本格式化插件提供常用的文本处理工具，包括：
    - 文本大小写转换（大写、小写）
    - 支持批量文本处理
    
    该插件适用于需要快速格式化文本的场景，
    如数据处理、内容编辑等。
    """
```

#### 7. `service_api` - API 接口定义
定义 Service 类中所有公开方法的接口规范，供 MCP 系统或其他自动化工具使用。

```python
def service_api(self) -> Dict[str, Any]:
    return {
        "to_uppercase": {
            "description": "将文本转换为大写",
            "parameters": {
                "text": {
                    "type": "str",
                    "description": "输入文本",
                    "required": True
                }
            },
            "returns": {
                "type": "str",
                "description": "大写后的文本"
            }
        }
    }
```

#### 8. `skill_icon` - 图标配置
使用 `PluginIcon` 类配置插件图标。支持多种图标类型。

##### 图标类型

1. **系统内置图标（BUILTIN）**
```python
from core.plugin.plugin_icon import PluginIcon

def skill_icon(self) -> PluginIcon:
    return PluginIcon.builtin("SP_FileIcon")
```

常用系统图标：
- `SP_FileIcon` - 文件图标
- `SP_DialogApplyButton` - 应用按钮
- `SP_DialogSaveButton` - 保存按钮
- `SP_MediaPlay` - 播放图标
- `SP_ArrowForward` - 前进箭头
- `SP_BrowserReload` - 刷新图标
- `SP_DialogOpenButton` - 打开按钮
- `SP_DialogResetButton` - 重置按钮

2. **文件图标（FILE）**
```python
def skill_icon(self) -> PluginIcon:
    return PluginIcon.from_file("icons/icon.png")
```
图标文件应放在插件目录下的 `icons/` 子目录中。

3. **Qt 资源图标（RESOURCE）**
```python
def skill_icon(self) -> PluginIcon:
    return PluginIcon.from_resource(":/icons/icon.png")
```

4. **Base64 编码图标（BASE64）**
```python
def skill_icon(self) -> PluginIcon:
    return PluginIcon.from_base64("iVBORw0KGgoAAAANS...")
```

5. **无图标（NONE）**
```python
def skill_icon(self) -> PluginIcon:
    return PluginIcon.none()
```

#### 9. `skill_description` - 简短描述
插件功能的简短描述，用于 UI 工具提示。

```python
def skill_description(self) -> str:
    return "提供文本格式化工具"
```

#### 10. `tags` - 标签
用于插件分类和搜索的标签列表。

```python
def tags(self) -> Optional[list[str]]:
    return ["text", "formatting", "utility"]
```

#### 11. `dependencies` - 依赖项
插件的外部依赖，格式为 `{包名: 版本要求}`。

```python
def dependencies(self) -> Optional[Dict[str, str]]:
    return {
        "Pillow": ">=9.0.0",
        "numpy": ">=1.20.0"
    }
```

### 可选属性

#### `name` - 插件显示名称
默认返回插件类名（去掉 `PluginInfo` 后缀）。可以覆盖以自定义显示名称。

```python
def name(self) -> str:
    return "我的插件"
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

#### `information.py`
```python
"""
文本格式化插件元数据
"""

from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon
from typing import Dict, Any, Optional

class TextFormattingPluginInfo(IPluginInfo):
    """文本格式化插件元数据"""
    
    @property
    def version(self) -> PluginVersion:
        return PluginVersion.from_string("release.1.0.0")
    
    @property
    def developer(self) -> str:
        return "KKPIP-Tech"
    
    @property
    def developer_email(self) -> str:
        return "support@example.com"
    
    @property
    def developer_website(self) -> str:
        return "https://github.com/KKPIP-Tech/InstructionX"
    
    @property
    def is_free(self) -> bool:
        return True
    
    @property
    def description(self) -> str:
        return """
        文本格式化插件提供常用的文本处理工具，包括：
        - 文本大小写转换（大写、小写）
        - 支持批量文本处理
        
        该插件适用于需要快速格式化文本的场景，
        如数据处理、内容编辑等。
        """
    
    @property
    def service_api(self) -> Dict[str, Any]:
        return {
            "to_uppercase": {
                "description": "将文本转换为大写",
                "parameters": {
                    "text": {
                        "type": "str",
                        "description": "输入文本",
                        "required": True
                    }
                },
                "returns": {
                    "type": "str",
                    "description": "大写后的文本"
                }
            },
            "to_lowercase": {
                "description": "将文本转换为小写",
                "parameters": {
                    "text": {
                        "type": "str",
                        "description": "输入文本",
                        "required": True
                    }
                },
                "returns": {
                    "type": "str",
                    "description": "小写后的文本"
                }
            }
        }
    
    @property
    def skill_icon(self) -> PluginIcon:
        return PluginIcon.builtin("SP_MediaPlay")
    
    @property
    def skill_description(self) -> str:
        return "提供文本格式化工具"
    
    @property
    def tags(self) -> Optional[list[str]]:
        return ["text", "formatting", "utility"]
    
    @property
    def dependencies(self) -> Optional[Dict[str, str]]:
        return None
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
from PySide6.QtCore import Qt
from core.plugin.plugin_interface import IPlugin
from .service import Service

class TextFormattingPlugin(IPlugin):
    """文本格式化插件"""
    
    @property
    def plugin_name(self) -> str:
        return "文本\n格式化"
    
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

#### `information.py`
```python
"""
颜色转换插件元数据
"""

from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon
from typing import Dict, Any, Optional

class ColorConverterPluginInfo(IPluginInfo):
    """颜色转换插件元数据"""
    
    @property
    def version(self) -> PluginVersion:
        return PluginVersion.from_string("release.1.0.0")
    
    @property
    def developer(self) -> str:
        return "KKPIP-Tech"
    
    @property
    def developer_email(self) -> str:
        return "support@example.com"
    
    @property
    def developer_website(self) -> str:
        return "https://github.com/KKPIP-Tech/InstructionX"
    
    @property
    def is_free(self) -> bool:
        return True
    
    @property
    def description(self) -> str:
        return """
        颜色转换插件提供颜色格式转换工具，包括：
        - HEX 颜色转 RGB 格式
        
        该插件适用于需要在不同颜色格式之间转换的场景，
        如设计工作、开发调试、颜色管理等。
        """
    
    @property
    def service_api(self) -> Dict[str, Any]:
        return {
            "hex_to_rgb": {
                "description": "将 HEX 颜色格式转换为 RGB 格式",
                "parameters": {
                    "hex_str": {
                        "type": "str",
                        "description": "HEX 颜色字符串（如 #FF5733 或 FF5733）",
                        "required": True
                    }
                },
                "returns": {
                    "type": "str",
                    "description": "RGB 格式字符串（如 rgb(255, 87, 51)），如果格式无效则返回错误信息"
                }
            }
        }
    
    @property
    def skill_icon(self) -> PluginIcon:
        return PluginIcon.builtin("SP_ArrowForward")
    
    @property
    def skill_description(self) -> str:
        return "提供颜色转换工具"
    
    @property
    def tags(self) -> Optional[list[str]]:
        return ["color", "conversion", "utility"]
    
    @property
    def dependencies(self) -> Optional[Dict[str, str]]:
        return None
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
- UI 代码、业务逻辑和元数据完全分离
- 每个文件职责明确，易于理解

### 2. 可维护性
- 修改 UI 时不需要触碰业务逻辑或元数据
- 修改业务逻辑时不需要改动 UI 代码
- 修改元数据时不需要改动实现代码
- 降低代码维护成本

### 3. 可测试性
- Service 类的方法可以独立进行单元测试
- 不需要启动 UI 框架即可测试业务逻辑
- 元数据可以独立验证
- 提高测试覆盖率

### 4. 可复用性
- Service 类可以在其他插件中复用
- 业务逻辑可以脱离 UI 独立使用
- 元数据可以被 MCP 系统读取
- 提高代码复用率

### 5. 可扩展性
- 新功能只需在 Service 类中添加方法
- UI 可以轻松调用新方法
- 支持功能的无缝扩展
- 支持多种图标类型
- 支持丰富的元数据

### 6. 系统集成
- 元数据可以被 MCP 系统自动读取
- 支持插件自动发现和加载
- 支持插件版本管理
- 支持依赖关系管理

## 最佳实践

### information.py 设计规范

1. **版本管理**
   - 遵循语义化版本规范
   - 使用正确的版本类型（release/beta/alpha/dev）
   - 在有重大更改时更新主版本号

2. **开发者信息**
   - 提供真实的联系方式
   - 保持邮箱和网站信息的有效性
   - 便于用户反馈问题

3. **描述信息**
   - 使用清晰易懂的语言
   - 列出所有主要功能
   - 说明适用场景
   - 使用格式化（项目符号、代码块等）提高可读性

4. **API 定义**
   - 列出所有公开方法
   - 提供详细的参数说明
   - 明确返回值类型和含义
   - 标注必需参数和可选参数

5. **图标选择**
   - 选择与功能相关的图标
   - 优先使用系统内置图标
   - 确保图标在不同主题下可见
   - 避免使用过于相似的图标

6. **标签设置**
   - 使用小写字母
   - 使用英文标签
   - 选择准确的分类标签
   - 避免使用过多标签（3-5个为宜）

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

### Q1: 为什么要分离 entrance.py、service.py 和 information.py？

A: 这种三分离设计带来以下好处：
- UI、逻辑和元数据完全解耦
- 便于单独测试业务逻辑
- 业务逻辑可以在其他场景复用
- 元数据可以被 MCP 等系统自动读取
- 降低维护成本，提高可维护性

### Q2: information.py 中的信息会被哪些系统使用？

A: information.py 中的信息会被以下系统使用：
- **主程序**：显示插件图标、描述、开发者信息
- **MCP 系统**：读取 service_api 定义，自动生成调用接口
- **插件管理器**：管理插件版本、依赖关系
- **用户界面**：显示插件图标、工具提示等

### Q3: 如何选择合适的系统图标？

A: 选择系统图标的建议：
- 根据插件功能选择相关图标
- 参考常见图标的使用惯例
- 测试不同主题下的显示效果
- 优先选择语义明确的图标

### Q4: Service 类可以是静态方法吗？

A: 可以，但建议使用实例方法，因为：
- 实例方法更灵活，便于未来扩展
- 可以添加实例变量存储状态
- 更符合面向对象设计原则

### Q5: 一个插件可以有多个 Service 类吗？

A: 可以。如果插件功能复杂，可以按功能模块划分多个 Service 类：
```python
from .services.format_service import FormatService
from .services.convert_service import ConvertService

format_service = FormatService()
convert_service = ConvertService()
```

### Q6: 如何在 service_api 中定义可选参数？

A: 使用 `default` 字段指定默认值：
```python
{
    "compress_image": {
        "description": "压缩图片",
        "parameters": {
            "file_path": {
                "type": "str",
                "description": "图片文件路径",
                "required": True
            },
            "quality": {
                "type": "int",
                "description": "压缩质量 (1-100)",
                "required": False,
                "default": 85
            }
        },
        "returns": {
            "type": "bool",
            "description": "是否成功"
        }
    }
}
```

### Q7: Service 类可以调用数据库或网络接口吗？

A: 可以。Service 类是处理业务逻辑的地方，完全可以：
- 访问数据库
- 调用网络 API
- 处理文件 I/O
- 执行任何必要的业务操作

### Q8: 如何处理 Service 类中的异常？

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

### Q9: 图标加载失败会发生什么？

A: 如果图标加载失败，系统会自动回退到默认的 `SP_FileIcon` 图标，确保插件始终有图标显示。

### Q10: 如何更新插件版本？

A: 按照 semver 规则更新版本号：
- **主版本号（major）**：不兼容的 API 修改
- **次版本号（minor）**：向下兼容的功能性新增
- **修订号（patch）**：向下兼容的问题修正

例如：
```python
# 新增功能
PluginVersion.from_string("release.1.1.0")

# 修复 bug
PluginVersion.from_string("release.1.0.1")

# 重大更改
PluginVersion.from_string("release.2.0.0")
```

## 迁移指南

如果您有旧版本的插件（只有 entrance.py 和 service.py），可以按照以下步骤添加 information.py：

### 步骤 1：创建 information.py
```python
"""
插件名称 - 插件元数据
"""

from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon
from typing import Dict, Any, Optional

class PluginNamePluginInfo(IPluginInfo):
    """插件元数据类"""
    
    @property
    def version(self) -> PluginVersion:
        return PluginVersion.from_string("release.1.0.0")
    
    @property
    def developer(self) -> str:
        return "您的名称"
    
    @property
    def developer_email(self) -> str:
        return "your.email@example.com"
    
    @property
    def developer_website(self) -> str:
        return "https://your-website.com"
    
    @property
    def is_free(self) -> bool:
        return True
    
    @property
    def description(self) -> str:
        return """
        插件功能描述
        """
    
    @property
    def service_api(self) -> Dict[str, Any]:
        return {
            # 根据 service.py 中的方法定义 API
        }
    
    @property
    def skill_icon(self) -> PluginIcon:
        return PluginIcon.builtin("SP_FileIcon")
    
    @property
    def skill_description(self) -> str:
        return "插件功能简介"
    
    @property
    def tags(self) -> Optional[list[str]]:
        return ["tag1", "tag2"]
    
    @property
    def dependencies(self) -> Optional[Dict[str, str]]:
        return None
```

### 步骤 2：定义 service_api
根据 service.py 中的方法，逐一在 service_api 中定义接口规范。

### 步骤 3：选择图标
根据插件功能选择合适的图标。

### 步骤 4：测试
- 运行程序验证图标显示正常
- 验证插件信息正确显示
- 测试 MCP 系统能否正确读取元数据

## 技术支持

如有问题或建议，请：
- 查看示例插件代码
- 阅读相关文档
- 提交 Issue 到项目仓库
- 参考插件开发指南