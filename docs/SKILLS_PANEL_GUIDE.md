# Skills Panel 使用指南

## 概述

Skills Panel 是一个类似 MS Office 工具栏的技能面板，支持横向滚动，包含两个标签页：
- **官方技能**：存放官方提供的插件
- **第三方技能**：存放用户自定义的第三方插件

## 系统架构

```
SkillsPanel
├── TabWidget (标签页容器)
│   ├── 官方技能标签页
│   │   └── QScrollArea → QHBoxLayout → SkillButton[]
│   └── 第三方技能标签页
│       └── QScrollArea → QHBoxLayout → SkillButton[]
└── PluginManager (插件管理器)
    ├── load_official_plugins()
    ├── load_thirdparty_plugins()
    └── get_skill_buttons()
```

## 目录结构

```
InstructionX/
├── core/
│   └── plugin/
│       ├── plugin_interface.py    # 插件接口定义
│       └── manager.py              # 插件管理器
├── ui/
│   ├── main_window.py            # 主窗口
│   ├── dialog/                   # 对话框模块
│   │   ├── __init__.py
│   │   └── plugin_order_dialog.py # 插件排序对话框
│   ├── work_area/                # 工作区模块
│   │   ├── __init__.py
│   │   └── work_area.py         # 工作区管理类
│   └── skills_panel/
│       ├── __init__.py
│       └── panel.py               # SkillsPanel UI 实现
├── plugin/                        # 官方插件目录
│   ├── text_formatting/          # 文本格式化插件
│   │   ├── __init__.py          # Python 包标识文件
│   │   └── entrance.py          # 插件入口文件
│   └── [其他官方插件]
└── custom_plugin/                 # 第三方插件目录
    ├── color_converter/
    │   ├── __init__.py          # Python 包标识文件
    │   └── entrance.py          # 插件入口文件
    └── [其他第三方插件]
```

## 如何创建新插件

### 步骤 1：创建插件目录

**对于官方插件：**
```bash
mkdir plugin/your_plugin_name
```

**对于第三方插件：**
```bash
mkdir custom_plugin/your_plugin_name
```

### 步骤 2：创建 `__init__.py` 和 `entrance.py` 文件

在插件目录中创建两个文件：

1. **`__init__.py`**：Python 包标识文件（可以为空或包含注释）
2. **`entrance.py`**：插件入口文件，实现 `IPlugin` 接口

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from core.plugin.plugin_interface import IPlugin

class YourPlugin(IPlugin):
    """你的插件描述"""
    
    @property
    def plugin_name(self) -> str:
        """返回插件名称"""
        return "你的插件名称"
    
    @property
    def skill_icon(self) -> Optional[QIcon]:
        """
        返回技能按钮的图标
        如果返回 None，系统会使用默认图标
        """
        from PySide6.QtWidgets import QApplication
        return QApplication.style().standardIcon(
            QApplication.style().StandardPixmap.SP_FileIcon
        )
    
    @property
    def skill_description(self) -> str:
        """返回技能的简短描述"""
        return "插件功能的简短描述"
    
    def get_widget(self, parent=None, data_provider=None) -> QWidget:
        """
        获取插件的主 widget
        
        Args:
            parent: 父控件
            data_provider: 主程序提供的数据对象（可选）
            
        Returns:
            插件的 QWidget 控件
        """
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        
        # 添加你的控件
        label = QLabel("你的插件内容")
        layout.addWidget(label)
        
        # 添加按钮或其他控件
        button = QPushButton("点击我")
        button.clicked.connect(lambda: print("按钮被点击"))
        layout.addWidget(button)
        
        return widget
```

### 步骤 3：重启应用

插件会在应用启动时自动加载。如果应用正在运行，重启它以加载新插件。

## SkillsPanel 功能说明

### 主要特性

1. **双标签页设计**
   - 官方技能标签页
   - 第三方技能标签页

2. **横向滚动**
   - 支持大量技能按钮
   - 平滑的滚动体验
   - 自适应布局

3. **MS Office 风格**
   - 图标在上，文字在下
   - 悬停高亮效果
   - 点击反馈动画
   - 现代化外观

4. **技能按钮**
   - 显示插件图标
   - 显示插件名称
   - 工具提示显示完整描述
   - 点击触发插件功能

### 使用方法

1. **点击技能按钮**
   - 点击任何技能按钮会打开一个对话框
   - 对话框中显示插件的主 widget
   - 可以在对话框中使用插件功能

2. **刷新技能列表**
   ```python
   # 在代码中调用
   skills_panel.refresh_skills()
   ```

## 插件接口详细说明

### IPlugin 接口

```python
class IPlugin(ABC):
    """插件抽象基类"""
    
    @property
    @abstractmethod
    def plugin_name(self) -> str:
        """插件名称（必须实现）"""
        pass
    
    @abstractmethod
    def get_widget(self, parent=None, data_provider=None) -> QWidget:
        """获取插件控件（必须实现）"""
        pass
    
    @property
    def skill_icon(self) -> Optional[QIcon]:
        """技能按钮图标（可选）"""
        return None
    
    @property
    def skill_description(self) -> str:
        """技能描述（可选）"""
        return self.plugin_name
```

### PluginManager 方法

```python
plugin_manager = PluginManager()

# 加载所有插件
plugin_manager.load_plugins()

# 加载官方插件
official_plugins = plugin_manager.load_official_plugins()

# 加载第三方插件
thirdparty_plugins = plugin_manager.load_thirdparty_plugins()

# 获取所有插件
all_plugins = plugin_manager.get_all_plugins()

# 根据名称获取插件
plugin = plugin_manager.get_plugin_by_name("插件名称")

# 重新加载插件
plugin_manager.reload_plugins()

# 手动注册插件
plugin_manager.register_plugin(plugin_instance, is_official=False)

# 注销插件
plugin_manager.unregister_plugin("插件名称")
```

## 示例插件

### 官方插件示例：文本格式化

位置：`plugin/text_formatting/entrance.py`

功能：
- 文本转大写
- 文本转小写

### 第三方插件示例：颜色转换

位置：`custom_plugin/color_converter/entrance.py`

功能：
- HEX 颜色转 RGB 格式

## 样式定制

### 修改技能按钮样式

在 `ui/skills_panel/panel.py` 中的 `SkillButton._apply_style()` 方法中修改：

```python
def _apply_style(self):
    """应用 MS Office 风格的样式"""
    self.setStyleSheet("""
        QToolButton {
            border: 1px solid transparent;
            border-radius: 4px;
            padding: 4px;
            background-color: transparent;
            color: #333333;
        }
        QToolButton:hover {
            background-color: #E5F3FF;
            border: 1px solid #B3D9FF;
        }
        QToolButton:pressed {
            background-color: #CCE8FF;
            border: 1px solid #99CCFF;
        }
    """)
```

### 修改标签页样式

在 `ui/skills_panel/panel.py` 的 `_init_ui()` 方法中修改标签页样式表。

## 最佳实践

1. **插件命名**
   - 使用描述性的名称
   - 保持简洁明了
   - 使用中文或英文均可

2. **插件图标**
   - 提供清晰、易识别的图标
   - 图标尺寸建议 48x48 像素
   - 可以使用系统标准图标

3. **插件描述**
   - 简短描述插件功能
   - 不要超过两行
   - 使用用户友好的语言

4. **插件布局**
   - 保持界面简洁
   - 合理使用布局管理器
   - 考虑响应式设计

5. **错误处理**
   - 在插件中添加适当的错误处理
   - 提供友好的错误提示
   - 避免插件崩溃影响主程序

## 故障排除

### 插件没有加载

1. 检查插件目录结构是否正确
2. 确认 `entrance.py` 文件存在（插件入口）
3. 确认 `__init__.py` 文件存在（Python 包标识）
4. 检查是否正确实现了 `IPlugin` 接口
5. 查看控制台输出的错误信息

### 插件图标不显示

1. 确认图标路径正确
2. 检查图标文件格式是否支持（PNG, SVG 等）
3. 如果使用系统图标，确认 `QApplication` 已初始化

### 技能按钮点击无反应

1. 检查信号连接是否正确
2. 确认 `get_widget()` 方法返回有效的 QWidget
3. 查看控制台是否有错误信息

## 扩展功能建议

可以考虑添加以下功能来增强系统：

1. **插件搜索/过滤**
   - 添加搜索框
   - 按名称或描述搜索技能

2. **收藏/常用技能**
   - 允许用户收藏常用技能
   - 快速访问收藏的插件

3. **技能分类**
   - 在标签页内按类别组织技能
   - 添加分组标题

4. **插件更新**
   - 检查插件更新
   - 支持插件热重载

5. **插件市场**
   - 在线浏览和安装插件
   - 插件评分和评论

## 技术支持

如有问题或建议，请通过以下方式联系：
- 提交 Issue 到项目仓库
- 查看项目文档
- 联系开发团队