# 技能面板

> SkillsPanel 的结构和功能

---

## 1. 概述

`SkillsPanel` 是应用程序的技能面板组件，提供类似工具栏的插件快捷访问方式。

**文件位置**: `ui/skills_panel/panel.py`

---

## 2. 面板结构

```mermaid
graph TB
    subgraph SkillsPanel [SkillsPanel]
        SW[QStackedWidget<br/>堆叠窗口控件]
        OB["_official_btn<br/>官方功能 Pill 按钮]
        TB["_thirdparty_btn<br/>第三方功能 Pill 按钮"]
    end

    subgraph Page1 [官方功能 页面]
        SA1[ScrollArea<br/>可滚动区域]
        CT1["QWidget#skillsContainer<br/>水平布局容器"]
        B1[技能按钮 1]
        B2[技能按钮 2]
        B3[技能按钮 N]
        SA1 --> CT1
        CT1 --> B1
        CT1 --> B2
        CT1 --> B3
    end

    subgraph Page2 [第三方功能 页面]
        SA2[ScrollArea<br/>可滚动区域]
        CT2["QWidget#skillsContainer<br/>水平布局容器"]
        C1[技能按钮 1]
        C2[技能按钮 2]
        C3[技能按钮 M]
        SA2 --> CT2
        CT2 --> C1
        CT2 --> C2
        CT2 --> C3
    end

    OB -->|切换显示| Page1
    TB -->|切换显示| Page2
    SW --> Page1
    SW --> Page2
```

> **注意**: 标签切换使用自定义 Pill 按钮（非 `QTabWidget` 的 `QTabBar`），通过 `QStackedWidget.setCurrentIndex()` 控制显示页面。

**标签页结构**:
- **官方功能**: 来自 `plugin/` 目录的官方插件
- **第三方功能**: 来自 `custom_plugin/` 目录的第三方插件

---

## 3. 核心组件

### 3.1 SkillButton

每个技能按钮代表一个插件，包含：
- **图标**: 通过 `IPlugin.skill_icon` 属性动态加载（从插件的 `information.py` 读取，带文件 mtime 缓存）
- **名称**: `IPlugin.plugin_name` 属性
- **描述**: 通过 `IPlugin.skill_description` 属性动态加载（从 `information.py` 读取，失败时回退为插件名称）
- **提示**: 鼠标悬停时显示的名称和描述（格式为 `plugin_name\nskill_description`）

**文本自动处理**:
- 允许插件设计者自行决定换行位置（使用 `\n`）
- 如果文本不含 `\n` 且长度大于 13 个字符（单行模式）或 8 个字符/行（双行模式），在中间位置分割（midpoint split，非 Unicode 感知）
- 单行模式每行最多 13 个字符，双行模式每行最多 8 个字符，超出部分末尾自动添加省略号（`...`）
- 最多显示 2 行
- 避免按钮因文本过长而破坏布局

### 3.2 按钮状态

| 状态 | 说明 |
|------|------|
| 正常 | 默认透明背景，无边框，`windowText` 颜色 |
| 悬停 | 背景变为 `{skillButtonHover}`，无边框 |
| 选中/活跃 | 渐变背景 `qlineargradient`（左侧 4% 为 `{accent}`，其余为 `{controlFillSelected}`），无边框，`{skillButtonActiveText}` 文字颜色，`font-weight: 500` |

---

## 4. 信号

### skill_clicked

```python
skill_clicked = Signal(object)
```

当用户点击技能按钮时发出。

**参数**:
- `plugin`: 被点击的插件实例 (IPlugin)

---

## 5. 核心方法

### 5.1 设置插件管理器

```python
def set_plugin_manager(self, plugin_manager):
    """
    设置插件管理器

    Args:
        plugin_manager: PluginManager 实例
    """
    self.plugin_manager = plugin_manager
```

### 5.2 加载技能

```python
def load_skills_from_manager(self):
    """从 PluginManager 加载技能按钮"""
    if self.plugin_manager is None:
        return

    try:
        # 清空现有按钮
        self._clear_layout(self.official_layout)
        self._clear_layout(self.thirdparty_layout)

        # 清除激活状态（重要：因为旧按钮已被删除）
        self._active_button = None

        # 加载官方技能
        official_plugins = self.plugin_manager.get_official_plugins()
        for plugin in official_plugins:
            self.add_skill_button(plugin, is_official=True)

        # 加载第三方技能
        thirdparty_plugins = self.plugin_manager.get_thirdparty_plugins()
        for plugin in thirdparty_plugins:
            self.add_skill_button(plugin, is_official=False)
    except Exception as e:
        self._logger.error(get_name(), f'Error loading skills from manager: {e}')
```

### 5.3 添加技能

```python
def add_skill_button(self, plugin, is_official: bool):
    """
    添加技能按钮到指定标签页

    Args:
        plugin: 插件实例
        is_official: 是否为官方插件（True = 官方功能标签，False = 第三方功能标签）
    """
    # 获取插件图标和描述
    try:
        icon = getattr(plugin, 'skill_icon', None)
        if icon is None or (isinstance(icon, QIcon) and icon.isNull()):
            style = self.style()
            icon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        name = plugin.plugin_name
        description = getattr(plugin, 'skill_description', name)
    except Exception as e:
        self._logger.error(get_name(), f'Error getting plugin info: {e}')
        return

    # 创建技能按钮
    skill_btn = SkillButton(icon, name, description, self)
    skill_btn.clicked.connect(lambda checked=False, btn=skill_btn, p=plugin: self._on_skill_clicked(btn, p))

    # 添加到相应布局
    if is_official:
        self.official_layout.addWidget(skill_btn)
    else:
        self.thirdparty_layout.addWidget(skill_btn)
```

### 5.4 刷新技能

```python
def refresh_skills(self):
    """刷新技能列表"""
    if self.plugin_manager:
        self.plugin_manager.reload_plugins()
        self.load_skills_from_manager()
```

### 5.5 清除高亮

```python
def clear_active_state(self):
    """
    公共方法：清除所有按钮的激活状态
    用于当工作区被清空时，取消所有按钮的高亮
    """
    self._clear_all_active_states()

def _clear_all_active_states(self):
    """内部方法：清除所有按钮的激活状态"""
    active_count = 0
    for layout in [self.official_layout, self.thirdparty_layout]:
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item:
                widget = item.widget()
                if isinstance(widget, SkillButton):
                    if widget.is_active():
                        active_count += 1
                    widget.set_active(False)
    self._active_button = None
```

---

## 6. 使用示例

### 6.1 在主窗口中使用

```python
from ui.skills_panel.panel import SkillsPanel
from core.plugin.manager import PluginManager

# 创建技能面板（传入容器，而非 central_widget）
self.skills_panel = SkillsPanel(self._container)

# 设置插件管理器
self.plugin_manager = PluginManager()
self.plugin_manager.load_plugins()
self.plugin_manager.apply_custom_order()  # 应用自定义顺序
self.skills_panel.set_plugin_manager(self.plugin_manager)

# 加载技能
self.skills_panel.load_skills_from_manager()

# 设置清除高亮的回调
self.work_area.set_clear_highlight_callback(
    self.skills_panel.clear_active_state
)

# 连接信号
self.skills_panel.skill_clicked.connect(self._on_skill_clicked)
```

### 6.2 处理技能点击

```python
def _on_skill_clicked(self, plugin):
    """处理技能按钮点击"""
    # 清除工作区（不清除按钮高亮）
    self.work_area.clear_keep_highlight()

    # 获取并显示插件 Widget
    plugin_widget = plugin.get_widget(parent=self.work_area.get_widget())
    if plugin_widget:
        self.work_area.add_widget(plugin_widget)
    else:
        # 如果插件 widget 创建失败，显示错误信息
        error_label = QLabel(f"无法加载插件：{plugin.plugin_name}")
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_label.setProperty("error", "true")
        error_label.style().unpolish(error_label)
        error_label.style().polish(error_label)
        self.work_area.add_widget(error_label)
```

---

## 7. 技能按钮外观

### 7.1 按钮结构

```
┌────────────────────┐
│                    │
│       [图标]       │  <- 28x28（固定）
│                    │
│   插件名称         │  <- 可换行
│                    │
└────────────────────┘
```

### 7.2 悬停提示

鼠标悬停时显示：
```
插件名称
技能描述
```

---

## 8. 深色模式支持

SkillsPanel 完全支持深色模式，通过 StyleQSS 的颜色变量自动适配主题。

### 8.1 颜色变量

SkillsPanel 使用以下颜色变量：

| 颜色变量 | 浅色主题 | 深色主题 | 用途 |
|---------|---------|---------|------|
| `skillPanel` | `#F5F7FA` | `#2C2C2C` | 面板背景 |
| `skillPanelHeaderBg` | `#EBEEF2` | `#363636` | Pill 按钮容器背景 |
| `windowText` | `#000000` | `#FFFFFF` | 文字颜色 |
| `textSecondary` | `#666666` | `#999999` | Pill 按钮未激活文字 |
| `accent` | `#0078D4` | `#0078D4` | 激活/选中强调色 |
| `accentDark` | `#005A9E` | `#005A9E` | 激活 Pill 按钮悬停背景 |
| `skillButtonHover` | `#E8F4FD` | `#1A3A5C` | 技能按钮悬停背景 |
| `skillButtonActiveText` | `#0078D4` | `#FFFFFF` | 技能按钮激活文字 |
| `controlFillHover` | `rgba(0,0,0,12)` | `rgba(255,255,255,12)` | 通用悬停效果 |

### 8.2 色彩层次

SkillsPanel 与工作区保持色彩层次区分：

**浅色模式：**
- SkillsPanel: `#F5F7FA`（浅灰）
- WorkArea: `#FFFFFF`（白色）

**深色模式：**
- SkillsPanel: `#2C2C2C`（深灰）
- WorkArea: `#202020`（深灰）

### 8.3 样式文件

SkillsPanel 和 SkillButton 的样式定义在 `utils/style_qss/styles/custom.qss`（由 QssRegistry 按优先级 20 加载）：

```css
/* SkillsPanel 容器 */
SkillsPanel {
    background-color: {skillPanel};
    border-bottom: 1px solid {borderLight};
}

/* SkillsPanel 头部区域 */
SkillsPanel QWidget#skillsPanelHeader {
    background-color: {skillPanel};
}

/* Pill 按钮容器 */
SkillsPanel QWidget#skillsPillContainer {
    background-color: {skillPanelHeaderBg};
    border-radius: 14px;
}

/* Pill 按钮（官方功能 / 第三方功能 切换） */
SkillsPanel QPushButton#skillsPillButton {
    background-color: transparent;
    color: {textSecondary};
    border: none;
    border-radius: 10px;
    padding: 4px 14px;
    font-size: 12px;
    font-weight: 500;
}
SkillsPanel QPushButton#skillsPillButton:hover {
    background-color: {controlFillHover};
}
SkillsPanel QPushButton#skillsPillButton[active="true"] {
    background-color: {accent};
    color: #FFFFFF;
}
SkillsPanel QPushButton#skillsPillButton[active="true"]:hover {
    background-color: {accentDark};
}

/* 分隔线与计数标签 */
SkillsPanel QLabel#skillsSeparator {
    color: {borderLight};
    font-size: 12px;
    background: transparent;
}
SkillsPanel QLabel#skillsCountLabel {
    color: {textSecondary};
    font-size: 11px;
    background: transparent;
}

/* 滚动区域样式 */
SkillsPanel QScrollArea {
    border: none;
    background: {skillPanel};
}

/* 技能按钮容器 */
SkillsPanel QWidget#skillsContainer {
    background-color: {skillPanel};
}

/* 非激活状态的技能按钮 */
SkillButton {
    border: none;
    border-radius: 8px;
    padding: 2px;
    background-color: transparent;
    color: {windowText};
    text-align: top;
    font-size: 10px;
}
SkillButton:hover {
    background-color: {skillButtonHover};
    border: none;
}
SkillButton:pressed {
    background-color: {controlFillPressed};
    border: none;
}

/* 激活状态的技能按钮（通过 setProperty("active", "true") 触发） */
SkillButton[active="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {accent}, stop:0.04 {accent},
        stop:0.04 {controlFillSelected}, stop:1 {controlFillSelected});
    border: none;
    border-radius: 8px;
    color: {skillButtonActiveText};
    text-align: top;
    font-weight: 500;
    font-size: 10px;
    padding: 2px;
}
```

---

## 9. 相关文档

- [主窗口](main-window.md)
- [工作区](work-area.md)
- [IPlugin 接口](../core/plugin-system/iplugin.md)

---

*本文档由 Claude Code 自动生成*
