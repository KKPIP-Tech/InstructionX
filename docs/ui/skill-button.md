# SkillButton 技能按钮

> 支持宽松图标上文下文、紧凑仅图标、激活高亮和完整名称提示的技能按钮

---

## 1. 概述

`SkillButton` 是 `QToolButton` 的子类，用于在技能面板中展示插件入口。宽松模式为图标上文下文，紧凑模式仅显示图标并提供完整名称 Tooltip；两种外观可往返切换且保留激活状态。

**文件位置**: `ui/skills_panel/skill_button.py`

---

## 2. 核心特性

- **宽松外观**: 图标在上、名称在下，固定 78×64，图标 28×28
- **紧凑外观**: 仅显示图标，宽度 32；高度由 SkillsPanel 的两个切换按钮实际行高统一提供，图标最大 20×20且不超出行高
- **激活状态**: 宽松模式使用浅色主色渐变，紧凑模式使用更深的 `color.primary` 主色背景（hover 为 `color.primary.hover`）；模式切换不改变激活状态
- **文本截断**: 仅宽松模式使用；单行文本超过 13 个字符时截断并追加省略号，含 `\n` 时最多显示两行，每行超过 8 个字符时追加省略号
- **完整提示**: 紧凑 Tooltip 保留未截断的 `skill_name`，宽松 Tooltip 为 `skill_name\nskill_description`

---

## 3. 构造函数

```python
def __init__(
    self,
    icon: QIcon,
    name: str,
    description: str,
    parent=None
)
```

**参数**:
- `icon`: 插件的图标（`QIcon`）
- `name`: 插件显示名称
- `description`: 插件描述（用于工具提示，**必填参数**）
- `parent`: 父控件（可选）

**示例**:
```python
button = SkillButton(
    icon=QIcon(":/icons/plugin.png"),
    name="LLM\nChat",
    description="LLM 智能对话",
    parent=self
)

# 注意：description 为必填参数
button2 = SkillButton(
    icon=QIcon(":/icons/my_plugin.png"),
    name="我的\n插件",
    description="我的插件功能描述"
)
```

---

## 4. 核心方法

### set_active()

```python
def set_active(self, active: bool)
```

设置按钮的激活状态。

**参数**:
- `active`: `True` 为激活状态（渐变高亮背景，无边框），`False` 为普通状态

**示例**:
```python
button.set_active(True)   # 激活
button.set_active(False)  # 取消激活
```

### set_compact()

```python
def set_compact(self, compact: bool, row_height: int) -> None
def is_compact(self) -> bool
```

切换宽松/紧凑外观。`row_height` 由 `SkillsPanel` 根据两个切换按钮的实际高度统一传入；紧凑模式下必须大于上下图标边距，否则抛出 `ValueError`。宽松调用保留原接口行为，不需要调用方保存按钮文本或激活状态。

```python
button.set_compact(True, row_height)
assert button.is_compact() is True
assert button.toolTip() == button.skill_name
button.set_compact(False, row_height)
assert button.toolTip() == f"{button.skill_name}\n{button.skill_description}"
```

### is_active()

```python
def is_active(self) -> bool
```

返回当前是否为激活状态。

### tool_tip

按钮的悬浮提示由 `_update_tooltip()` 按当前外观设置：宽松为 `"名称\n描述"`，紧凑为未截断的完整 `skill_name`。

```python
tooltip = self.skill_name if self._compact else f"{self.skill_name}\n{self.skill_description}"
self.setToolTip(tooltip)
```

**注意**: `SkillButton` 本身不感知 `IPlugin` 接口，tooltip 所需的数据由 `SkillsPanel` 从 `IPlugin` 相关属性中提取后，以普通字符串形式传入。`SkillsPanel` 构造 `SkillButton` 时的 description 参数来源为 `plugin.skill_description`。

### skill_name / skill_description

`SkillButton` 在构造函数中保存传入的 `name` 和 `description` 为实例属性：

```python
self.skill_name = name
self.skill_description = description
```

这两个属性由 `_update_tooltip()` 消费，用于在模式切换后恢复完整名称和描述；紧凑模式不会用截断后的按钮文本覆盖它们。

---

## 5. 内部方法

### _process_display_text()

自动处理宽松按钮文本的换行和截断；紧凑模式通过 `ToolButtonIconOnly` 隐藏文本，不删除这些处理结果：

- 如果文本包含 `\n`，按换行符分割，最多取前 2 行；每行超过 8 个字符时截断为前 8 个字符并追加 `...`
- 如果不含 `\n`（单行模式），长度超过 13 个字符时直接截断为前 13 个字符并追加 `...`，不自动换行
- 最多显示 2 行

**示例**:
```python
# "LLM\nChat" -> 显示为两行
# "这是一个非常非常长的插件名称"（14 字符）-> 显示为 "这是一个非常非常长的插件名..."（前 13 字符 + ...）
```

### _apply_style()

更新按钮样式属性并触发 Qt 样式重算。

- 根据 `_is_active` 设置 `active` 属性（`"true"` 或 `"false"`）
- 通过 `setProperty("active", value)` + `style().unpolish()` + `style().polish()` 触发样式更新，确保 QSS 重新匹配

---

## 6. 样式定义

按钮的样式通过 QSS 样式表控制，关键状态：

| 状态 | 说明 |
|------|------|
| 普通状态 | 默认透明背景，无边框 |
| 悬停状态 | `T("color.primary.subtle")` 背景高亮，无边框 |
| 按下状态 | `T("color.border")` 背景，无边框 |
| 激活状态 | 渐变背景 `qlineargradient`（左侧 4% 为 `T("color.primary")`，其余为 `T("color.primary.subtle")`），无边框，`T("color.primary")` 文字颜色 |

样式定义位于 `ui/uikit_theme.py` 的排除区兼容附录（`_compat_skills_panel_qss()`，结构沿用旧 custom.qss，颜色实时取 UIKit 令牌，详见 [UIKit 主题系统](../utils/uikit-theme.md)）。紧凑模式追加 `SkillButton[compact="true"]` 的 padding/radius 规则，导航按钮使用 `QToolButton#skillsScrollButton`；激活与分组展开渐变保持不变：

```css
/* 非激活状态 */
SkillButton {
    border: none;
    border-radius: 8px;
    padding: 2px;
    background-color: transparent;
    color: {T("color.text.primary")};
    text-align: top;
    font-size: 10px;
}
SkillButton:hover {
    background-color: {T("color.primary.subtle")};
    border: none;
}
SkillButton:pressed {
    background-color: {T("color.border")};
    border: none;
}

/* 激活状态 */
SkillButton[active="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {T("color.primary")}, stop:0.04 {T("color.primary")},
        stop:0.04 {T("color.primary.subtle")}, stop:1 {T("color.primary.subtle")});
    border: none;
    border-radius: 8px;
    color: {T("color.primary")};
    text-align: top;
    font-weight: 500;
    font-size: 10px;
    padding: 2px;
}
SkillButton[active="true"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {T("color.primary")}, stop:0.04 {T("color.primary")},
        stop:0.04 {T("color.primary.subtle")}, stop:1 {T("color.primary.subtle")});
    border: none;
    padding: 2px;
}

/* 分组按钮展开态（plugin_group_widget.py） */
SkillButton#skillGroupButton[expanded="true"] {
    background: qlineargradient(x1:1, y1:0, x2:0, y2:0,
        stop:0 {T("color.primary")}, stop:0.04 {T("color.primary")},
        stop:0.04 {T("color.primary.subtle")}, stop:1 {T("color.primary.subtle")});
    border: none;
    border-radius: 8px;
    color: {T("color.primary")};
    text-align: top;
    font-weight: 500;
    font-size: 10px;
    padding: 2px;
}
SkillButton#skillGroupButton[expanded="true"]:hover {
    background: qlineargradient(x1:1, y1:0, x2:0, y2:0,
        stop:0 {T("color.primary")}, stop:0.04 {T("color.primary")},
        stop:0.04 {T("color.primary.subtle")}, stop:1 {T("color.primary.subtle")});
    border: none;
    padding: 2px;
}
```

---

## 7. 使用示例

```python
from ui.skills_panel.skill_button import SkillButton
from PySide6.QtGui import QIcon

# 创建按钮
button = SkillButton(
    icon=QIcon(":/icons/my_plugin.png"),
    name="我的\n插件",
    description="我的插件功能描述"
)

# 连接点击信号
button.clicked.connect(self._on_button_clicked)

# 设置激活状态
button.set_active(True)
```

---

## 8. 相关文档

- [技能面板](skills-panel.md)
- [主窗口](main-window.md)
