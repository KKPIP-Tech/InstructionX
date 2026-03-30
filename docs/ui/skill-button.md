# SkillButton 技能按钮

> 图标在上、文本在下的技能切换按钮，支持激活状态高亮和自动文本换行

---

## 1. 概述

`SkillButton` 是 `QToolButton` 的子类，用于在技能面板中以图标+文字的方式展示插件入口。

**文件位置**: `ui/skills_panel/skill_button.py`

---

## 2. 核心特性

- **图标在上**: 按钮上方显示插件图标，下方显示插件名称
- **激活状态**: 当前选中的插件按钮有高亮边框
- **自动换行**: 长文本自动在合适位置换行，每行最多 5 个字符
- **固定尺寸**: 60 x 70 像素，适合工具栏布局

---

## 3. 构造函数

```python
def __init__(
    self,
    icon: QIcon,
    name: str,
    description: str,
    parent: QWidget = None
)
```

**参数**:
- `icon`: 插件的图标（`QIcon`）
- `name`: 插件显示名称
- `description`: 插件描述（用于工具提示）
- `parent`: 父控件

**示例**:
```python
button = SkillButton(
    icon=QIcon(":/icons/plugin.png"),
    name="LLM\nChat",
    description="LLM 智能对话",
    parent=self
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
- `active`: `True` 为激活状态（高亮边框），`False` 为普通状态

**示例**:
```python
button.set_active(True)   # 激活
button.set_active(False)  # 取消激活
```

### is_active()

```python
def is_active(self) -> bool
```

返回当前是否为激活状态。

---

## 5. 内部方法

### _process_display_text()

自动处理按钮文本的换行和截断：

- 如果文本包含 `\n`，按换行符分割
- 否则，如果长度 > 5，在第 5 个字符处换行
- 每行最大 5 个字符，超出部分用 `...` 截断
- 最多显示 2 行

**示例**:
```python
# "LLM\nChat" -> 显示为两行
# "文本格式化" -> 显示为 "文本..." 和 "格式化"
```

### _apply_style()

更新按钮样式属性并触发 Qt 样式重算。

- 根据 `_is_active` 设置 `active` 属性（`"true"` 或 `""`)
- 通过 `setProperty("active", value)` + `style().unpolish()` + `style().polish()` 触发样式更新

---

## 6. 样式定义

按钮的样式通过 QSS 样式表控制，关键状态：

| 状态 | 说明 |
|------|------|
| 普通状态 | 默认透明背景 |
| 悬停状态 | 半透明背景高亮 |
| 激活状态 | 边框高亮（accent 色） |

样式文件位于 `utils/style_qss/styles/custom.qss`：

```css
SkillButton[active="true"] {
    border: 2px solid accent_color;
    border-radius: 4px;
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

---

*本文档由 Claude Code 自动生成*
