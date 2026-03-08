# 主窗口

> InstructionXMainWindow 的结构和功能

---

## 1. 概述

`InstructionXMainWindow` 是应用程序的主窗口类，负责整体界面的布局和组件协调。

**文件位置**: `ui/main_window.py`

**基类**: `QMainWindow` (PySide6)

---

## 2. 窗口结构

```mermaid
graph TB
    subgraph Window["InstructionXMainWindow"]
        Menu["菜单栏<br/>文件 编辑 用户中心 帮助"]
        SP["SkillsPanel<br/>技能面板 120-150px"]
        Divider["分割线"]
        WA["WorkArea<br/>工作区"]
    end

    Menu --> SP
    SP --> Divider
    Divider --> WA
```

---

## 3. 核心组件

### 3.1 菜单栏

```python
def _create_menus(self) -> None:
    # 文件菜单
    menu_file = self.menuBar().addMenu("文件")
    menu_file_load_action = QAction("加载录制文件", self)
    menu_file.addAction(menu_file_load_action)

    # 编辑菜单
    menu_edit = self.menuBar().addMenu("编辑")
    menu_edit_plugin_order_action = QAction("插件排序", self)
    menu_edit.addAction(menu_edit_plugin_order_action)

    # 用户中心菜单
    menu_user = self.menuBar().addMenu("用户中心")

    # 帮助菜单
    menu_help = self.menuBar().addMenu("帮助")
    menu_help_about_action = QAction("关于", self)
    menu_help.addAction(menu_help_about_action)
```

### 3.2 技能面板 (SkillsPanel)

- **位置**: 窗口顶部
- **高度**: 最小 120px，最大 150px
- **功能**: 显示所有已加载的插件作为技能按钮
- **通信**: 通过 `skill_clicked` 信号与主窗口通信

### 3.3 工作区 (WorkArea)

- **位置**: 窗口中部（技能面板下方）
- **特性**: 可伸缩，占用剩余空间
- **功能**: 显示当前选中插件的 Widget

---

## 4. 初始化流程

```mermaid
flowchart TD
    A[__init__] --> B[super().__init__]
    B --> C[设置窗口尺寸]
    C --> D[_create_menus 创建菜单]
    D --> E[_create_main_layout]

    E --> F[创建中心部件]
    F --> G[初始化 PluginManager]
    G --> H[load_plugins 加载插件]
    H --> I[apply_custom_order 应用顺序]

    I --> J[创建 SkillsPanel]
    J --> K[设置回调]
    K --> L[连接信号]
    L --> M[完成]
```

```python
def __init__(self):
    super().__init__()

    # 设置初始窗口大小
    self.setMinimumSize(800, 600)
    self.resize(1024, 768)

    # 创建菜单
    self._create_menus()

    # 创建主布局
    self._create_main_layout()


def _create_main_layout(self) -> None:
    # 创建中心部件
    central_widget = QWidget()
    self.setCentralWidget(central_widget)

    # 垂直布局
    main_layout = QVBoxLayout(central_widget)
    main_layout.setContentsMargins(5, 5, 5, 5)
    main_layout.setSpacing(5)

    # 初始化插件管理器
    self.plugin_manager = PluginManager()
    self.plugin_manager.load_plugins()
    self.plugin_manager.apply_custom_order()

    # 创建技能面板
    self.skills_panel = SkillsPanel(central_widget)
    self.skills_panel.set_plugin_manager(self.plugin_manager)
    self.skills_panel.load_skills_from_manager()
    self.skills_panel.setMaximumHeight(150)
    self.skills_panel.setMinimumHeight(120)
    main_layout.addWidget(self.skills_panel)

    # 添加分割线
    separator = QFrame()
    separator.setFrameShape(QFrame.Shape.HLine)
    main_layout.addWidget(separator)

    # 创建工作区
    self.work_area = WorkArea(central_widget)
    main_layout.addWidget(self.work_area.get_widget(), stretch=1)

    # 设置回调
    self.work_area.set_clear_highlight_callback(
        self.skills_panel.clear_active_state
    )

    # 连接信号
    self.skills_panel.skill_clicked.connect(self._on_skill_clicked)
```

---

## 5. 信号处理

### 5.1 技能按钮点击

```mermaid
sequenceDiagram
    participant User
    participant SP as SkillsPanel
    participant MW as MainWindow
    participant WA as WorkArea
    participant Plugin

    User->>SP: 点击技能按钮
    SP-->>MW: skill_clicked 信号
    MW->>WA: clear_keep_highlight
    MW->>Plugin: get_widget 获取 Widget
    Plugin-->>MW: 返回 Widget
    MW->>WA: add_widget 添加 Widget
```

```python
def _on_skill_clicked(self, plugin):
    """
    处理技能按钮点击事件
    在工作区显示插件的 widget
    """
    # 清空工作区（不清除按钮高亮）
    self.work_area.clear_keep_highlight()

    # 获取插件的 widget 并显示在工作区
    plugin_widget = plugin.get_widget(parent=self.work_area.get_widget())

    if plugin_widget:
        self.work_area.add_widget(plugin_widget)
    else:
        # 如果插件 widget 创建失败，显示错误信息
        error_label = QLabel(f"无法加载插件：{plugin.plugin_name}")
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.work_area.add_widget(error_label)
```

### 5.2 插件排序

```python
def _open_plugin_order_dialog(self):
    """打开插件排序对话框"""
    dialog = PluginOrderDialog(self.plugin_manager, self)

    if dialog.exec() == QDialog.DialogCode.Accepted:
        # 用户点击了保存，重新加载 skills panel
        self.skills_panel.load_skills_from_manager()
```

---

## 6. 布局属性

| 属性 | 值 |
|------|------|
| 最小尺寸 | 800 x 600 |
| 默认尺寸 | 1024 x 768 |
| 边距 | 5px |
| 间距 | 5px |
| 技能面板高度 | 最小 120px，最大 150px |

---

## 7. 相关文档

- [技能面板](skills-panel.md)
- [工作区](work-area.md)
- [系统架构概述](../architecture/overview.md)

---

*本文档由 Claude Code 自动生成*
