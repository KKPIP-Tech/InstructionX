# Skills Area 宽松/紧凑双模式 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留现有宽松模式的前提下，为 Skills Area 增加单行、仅显示插件 Logo、支持溢出箭头导航和完整名称悬停提示的紧凑模式，并从「编辑」菜单中「切换主题」下方的入口切换和记住选择。

**Architecture:** `SkillsPanel` 持有显示模式并复用现有页面、插件按钮与分组控件，切换模式时不重载插件或重建工作区。`SkillButton` 只负责两种外观；新增 `SkillsScrollNavigator` 独立负责当前滚动页、溢出检测、箭头状态和 UIKit 图标；主窗口只负责菜单动作与偏好保存。

**Tech Stack:** Python 3.14、PySide6 6.11.1、Qt Widgets、InstructionX_UIKit Iconoir、SQLite DataProvider、pytest-qt（仅 `test` 分支）、独立 GUI 冒烟脚本（`dev` 分支）。

## Global Constraints

- 默认模式为 `compact`；宽松模式的布局、尺寸、计数器、滚动条和点击行为保持不变，用户保存的模式优先于默认值。
- 紧凑模式为单行：`[官方|第三方] | [横向插件 Logo] [左箭头][右箭头]`；不显示计数器、横向滚动指示条、SkillsPanel 或分组展开区外轮廓（紧凑时外层容器、Stack、ScrollArea 和内容容器均为 `border: none`，ScrollArea 使用 `QFrame.Shape.NoFrame`，底色保留 `color.bg.subtle` 不透明，宽松保留原背景与分隔线）；开启插件使用 `color.primary` 主色背景。
- 紧凑按钮宽度建议 32；**插件按钮、分组文件夹按钮和左右导航按钮的高度必须与【官方｜第三方】切换按钮的实际渲染高度一致**，不得另设 32×32 固定尺寸。图标尺寸根据统一行高计算，面板总高度由统一行高与命名边距计算，不硬编码 48。
- 紧凑按钮只显示插件原有 `IPlugin.skill_icon`，悬停 Tooltip 必须显示未截断的 `plugin_name`；插件 Logo 不替换为 UIKit 图标。
- 左右箭头只使用 UIKit 自带 Iconoir `arrow-left` / `arrow-right`，通过 `InstructionX_UIKit.get_pixmap()` 渲染；不得新增 SVG/PNG、文本箭头或修改 `ui/InstructionX_UIKit/`。
- 箭头在普通和禁用状态分别使用 `color.text.secondary` / `color.text.disabled`，并响应 `ThemeManager.theme_changed`。
- 保留现有插件排序、分组和行内展开语义；紧凑模式中分组文件夹按钮同样图标化，不把分组扁平化。
- 只有当前页内容溢出时显示两个箭头；箭头每次滚动一个 `pageStep()`，到左/右边界时对应按钮禁用。保留 Qt 默认滚轮和触控板滚动能力。
- 模式切换不得重载插件、重建插件 Widget、丢失当前 Tab、激活按钮、分组展开状态或各页滚动位置。
- 宽松/紧凑选择必须通过 PRIVATE `skills_panel_mode` 持久化，并在应用重启后恢复；这不是可省略的增强项。
- 不改变 `IPlugin`、`PluginServices`、`PluginManager` 等公共契约，不修改 `core/version.py`，不新增第三方依赖。
- `plugin/`、`custom_plugin/` 和 `ui/InstructionX_UIKit/` 完全只读。
- 新方法/函数不超过 40 行、嵌套不超过 3 层；注释和 docstring 使用中文，字面量使用命名常量。
- pytest 代码只允许进入 `test` 分支；本计划只新增测试文件，不修改既有测试。`dev` 使用 `scripts/smoke_skills_panel_modes.py` 做即时验证。
- 每个功能任务先在 `dev` 完成失败冒烟、最小实现和通过复验，再按项目流程在 `test` 分支补充 pytest。
- 所有 `git commit`、分支切换或合并操作执行前必须获得用户确认；提交信息使用 `<type>(<scope>): <中文描述>`，是否添加自定义前缀另行询问。
- 截图、临时配置和调试输出只写入 `temp/`；验证后清理不再需要的临时文件。

## 默认交互决策

1. 在「编辑」菜单中新增 `QAction`，**紧跟「切换主题」下方、位于「语言」上方**；不得添加为 MenuBar 顶层独立按钮，也不得放入「AI」菜单。
2. 动作显示当前状态，例如 `技能区：宽松` / `技能区：紧凑`，并提供切换提示；动作本身可勾选，勾选表示紧凑。
3. **模式选择必须记住**：使用现有 `APP_CONFIG_PLUGIN_ID` 的 PRIVATE 数据保存 `skills_panel_mode`，值为 `relaxed` 或 `compact`，重启后恢复上次选择；非法值或读取失败回退 `compact`，保存失败不阻断切换并记录 WARNING。
4. 分组按钮在紧凑模式保留点击展开/收起功能，展开后组内插件仍以紧凑 Logo 按钮行内显示；分组展开状态变化必须刷新溢出箭头。
5. 窗口变窄、插件安装/卸载、Tab 切换、分组展开/收起后均重新计算溢出；无插件或无溢出时不显示箭头。
6. `SkillsPanel._compact_row_height()` 以两个切换按钮的实际渲染高度为唯一行高来源，并将该值传给全部紧凑插件按钮、分组按钮和导航按钮。首次显示、语言切换和主题切换后延迟重新同步，避免字体或 QSS 变化造成高度不一致。

## 文件结构

| 文件 | 动作与职责 |
|---|---|
| `ui/skills_panel/skill_button.py` | 修改：宽松/紧凑外观、尺寸、图标和 Tooltip 切换 |
| `ui/skills_panel/plugin_group_widget.py` | 修改：向文件夹及组内按钮传播紧凑外观，保留展开信号 |
| `ui/skills_panel/scroll_navigation.py` | 新增：当前 ScrollArea 绑定、溢出检测、分页滚动、边界禁用、Iconoir 图标与主题刷新 |
| `ui/skills_panel/panel.py` | 修改：模式状态、单行/双行布局迁移、面板高度、滚动策略和导航接线 |
| `ui/main_window.py` | 修改：「编辑 → 切换主题」下方的模式动作、模式加载/保存和面板初始化；删除主窗口中的面板高度重复定义 |
| `ui/uikit_theme.py` | 修改：紧凑按钮与导航按钮的 QSS，颜色继续取 UIKit 令牌 |
| `ui/text/zh.xml`、`en.xml`、`fr.xml`、`ru.xml` | 修改：菜单、模式和左右导航的四语言文案 |
| `scripts/smoke_skills_panel_modes.py` | 新增：真实 Qt 组件双模式、溢出、状态保持和截图冒烟 |
| `test/ui_tests/test_skills_panel_compact.py`（仅 `test` 分支） | 新增：按钮、分组、导航和面板双模式测试 |
| `test/ui_tests/test_skills_panel_mode_action.py`（仅 `test` 分支） | 新增：菜单动作、偏好恢复、非法值和保存失败测试 |
| `docs/ui/skills-panel.md`、`skill-button.md`、`main-window.md` | 修改：双模式结构、交互、尺寸和菜单入口 |
| `docs/architecture/overview.md`、`AGENTS.md` | 修改：同步 SkillsPanel 双模式和紧凑高度，消除固定 125–135 的单一模式描述 |

## 分支与验证工作流

每个 Task 1–4 严格按以下顺序执行：

1. 在 `dev` 向 `scripts/smoke_skills_panel_modes.py` 添加本任务失败场景，确认失败原因正是缺少目标行为。
2. 完成最小实现，运行同一冒烟及相邻既有检查直至通过。
3. 请求用户确认后提交 `dev` 功能改动。
4. 请求用户确认分支操作后，在 `test` 分支合入当前 `dev`，添加本任务列出的新 pytest 文件；不修改既有测试。
5. 运行定向 pytest 和全量 pytest；请求确认后提交测试，返回 `dev` 开始下一任务。

macOS 命令使用 `.venv/bin/python`；Windows 对应使用 `.venv\Scripts\python.exe`。

---

### Task 1: SkillButton 与分组控件的紧凑外观

**Files:**
- Modify: `ui/skills_panel/skill_button.py:12-89`
- Modify: `ui/skills_panel/plugin_group_widget.py:55-163`
- Modify: `ui/uikit_theme.py:175-313`
- Create: `scripts/smoke_skills_panel_modes.py`
- Test（仅 `test` 分支）: `test/ui_tests/test_skills_panel_compact.py`

**Interfaces:**
- Consumes: 现有 `SkillButton(icon, name, description, parent=None)`，构造签名保持不变。
- Produces: `SkillButton.set_compact(compact: bool, row_height: int) -> None`、`SkillButton.is_compact() -> bool`、`PluginGroupWidget.set_compact(compact: bool, row_height: int) -> None`。`row_height` 在紧凑模式下必须使用 SkillsPanel 提供的统一切换按钮行高。

- [ ] **Step 1: 在 dev 冒烟中写入按钮失败场景**

```python
row_height = 24
button = SkillButton(QIcon(), "完整插件全称", "插件描述")
button.set_compact(True, row_height)
assert button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
assert button.width() == COMPACT_BUTTON_WIDTH
assert button.height() == row_height
assert button.iconSize().height() <= row_height
assert button.toolTip() == "完整插件全称"
button.set_compact(False, row_height)
assert button.size() == QSize(78, 64)
assert button.toolTip() == "完整插件全称\n插件描述"
```

- [ ] **Step 2: 运行冒烟并确认按预期失败**

Run: `.venv/bin/python scripts/smoke_skills_panel_modes.py --case button`

Expected: FAIL，原因是 `SkillButton` 尚无 `set_compact()`；不得用删除断言绕过失败。

- [ ] **Step 3: 实现按钮和分组的最小模式接口**

`SkillButton` 使用以下完整核心方法；尺寸常量为 `RELAXED_BUTTON_WIDTH=78`、`RELAXED_BUTTON_HEIGHT=64`、`RELAXED_ICON_SIZE=28`、`COMPACT_BUTTON_WIDTH=32`、`COMPACT_ICON_MAX_SIZE=20`、`COMPACT_ICON_VERTICAL_PADDING=2`。紧凑高度不在按钮类中定义。

```python
def set_compact(self, compact: bool, row_height: int) -> None:
    """切换外观；紧凑高度由 SkillsPanel 的切换按钮行高统一提供。"""
    if compact and row_height <= 2 * COMPACT_ICON_VERTICAL_PADDING:
        raise ValueError("紧凑按钮行高必须大于上下图标边距")
    self._compact = compact
    if compact:
        icon_size = min(
            COMPACT_ICON_MAX_SIZE,
            row_height - 2 * COMPACT_ICON_VERTICAL_PADDING,
        )
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setFixedSize(COMPACT_BUTTON_WIDTH, row_height)
        self.setIconSize(QSize(icon_size, icon_size))
    else:
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setFixedSize(RELAXED_BUTTON_WIDTH, RELAXED_BUTTON_HEIGHT)
        self.setIconSize(QSize(RELAXED_ICON_SIZE, RELAXED_ICON_SIZE))
    self.setToolTip(self.skill_name if compact else f"{self.skill_name}\n{self.skill_description}")
    self.setProperty("compact", "true" if compact else "false")
    self._apply_style()


def is_compact(self) -> bool:
    """返回当前是否为紧凑外观。"""
    return self._compact
```

构造函数默认令 `_compact=False`，原有文本截断只用于宽松模式；`ToolButtonIconOnly` 负责隐藏文本，不清空 `skill_name`。`PluginGroupWidget` 保存主布局和展开区布局引用，并实现：

```python
def set_compact(self, compact: bool, row_height: int) -> None:
    """向文件夹和全部组内按钮传播紧凑外观与统一行高。"""
    self.folder_btn.set_compact(compact, row_height)
    for index in range(self._inner_layout.count()):
        item = self._inner_layout.itemAt(index)
        button = item.widget() if item else None
        if isinstance(button, SkillButton):
            button.set_compact(compact, row_height)
    self._inner_layout.setContentsMargins(*(COMPACT_GROUP_MARGINS if compact else RELAXED_GROUP_MARGINS))
    self._inner_layout.setSpacing(COMPACT_GROUP_SPACING if compact else RELAXED_GROUP_SPACING)
```

在 `_compat_skills_panel_qss()` 增加 `SkillButton[compact="true"]` 的紧凑 padding/radius；激活渐变、hover、pressed 和分组 expanded 状态继续沿用现有令牌与选择器。

- [ ] **Step 4: 复验按钮与分组冒烟**

Run: `.venv/bin/python scripts/smoke_skills_panel_modes.py --case button`

Expected: PASS；额外断言文件夹和组内两个插件按钮宽度均为 32、高度均等于切换按钮行高，切回宽松后均恢复 78×64，激活状态不变。

- [ ] **Step 5: 请求确认并提交 dev，然后在 test 分支添加 pytest**

```python
def test_compact_button_preserves_full_name_and_restores_relaxed(qtbot):
    """紧凑按钮仅显示图标和全名提示，恢复宽松后名称与描述完整还原。"""
    row_height = 24
    button = SkillButton(QIcon(), "完整插件全称", "插件描述")
    qtbot.addWidget(button)
    button.set_compact(True, row_height)
    assert button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
    assert button.width() == COMPACT_BUTTON_WIDTH
    assert button.height() == row_height
    assert button.toolTip() == "完整插件全称"
    button.set_active(True)
    button.set_compact(False, row_height)
    assert button.size() == QSize(78, 64)
    assert button.toolTip() == "完整插件全称\n插件描述"
    assert button.is_active() is True
```

新增分组测试时分别断言 `folder_btn` 和 `expand_area.layout()` 中的按钮；不得只验证顶层文件夹。

- [ ] **Step 6: 运行定向测试并提交测试**

Run: `.venv/bin/python -m pytest test/ui_tests/test_skills_panel_compact.py -q --tb=short -p no:cacheprovider`

Expected: PASS。按 Global Constraints 请求确认后分别提交 dev 与 test。

---

### Task 2: UIKit 图标的横向滚动导航组件

**Files:**
- Create: `ui/skills_panel/scroll_navigation.py`
- Modify: `ui/uikit_theme.py:175-313`
- Modify: `ui/text/zh.xml`、`en.xml`、`fr.xml`、`ru.xml`
- Modify: `scripts/smoke_skills_panel_modes.py`
- Test（仅 `test` 分支）: `test/ui_tests/test_skills_panel_compact.py`

**Interfaces:**
- Consumes: `QScrollArea.horizontalScrollBar()`、UIKit `get_pixmap()`、`ThemeManager.theme_changed`、`tr()`。
- Produces: `SkillsScrollNavigator.watch(scroll_area)`、`set_current(scroll_area)`、`set_active(active: bool)`、`set_row_height(row_height: int)`、`refresh()`、`left_btn`、`right_btn`。导航按钮高度同样由 SkillsPanel 统一传入。

- [ ] **Step 1: 添加无溢出、溢出和边界失败场景**

冒烟创建可视宽度 240、内容宽度 1200 的 `QScrollArea`，断言未溢出时导航隐藏；溢出时两个按钮出现，初始左按钮禁用、右按钮可用；点击右按钮后滚动值增加一个 `pageStep()`；滚到最大值后右按钮禁用。

- [ ] **Step 2: 运行导航场景并确认失败**

Run: `.venv/bin/python scripts/smoke_skills_panel_modes.py --case navigation`

Expected: FAIL，原因是 `ui.skills_panel.scroll_navigation` 尚不存在。

- [ ] **Step 3: 实现独立的 SkillsScrollNavigator**

组件使用 `NAV_BUTTON_WIDTH=28`、`NAV_ICON_MAX_SIZE=16`、`NAV_ICON_VERTICAL_PADDING=2`、`SCROLL_DIRECTION_PREVIOUS=-1`、`SCROLL_DIRECTION_NEXT=1`，自身水平布局边距为 0。`set_row_height()` 校验行高足以容纳图标后，将两个导航按钮设为 `NAV_BUTTON_WIDTH × row_height`，图标边长取 `min(NAV_ICON_MAX_SIZE, row_height - 2 * NAV_ICON_VERTICAL_PADDING)`；核心滚动行为按以下实现：

```python
def _scroll_page(self, direction: int) -> None:
    """按当前可视页滚动，QScrollBar 自动钳制到合法范围。"""
    if self._current_scroll_area is None:
        return
    bar = self._current_scroll_area.horizontalScrollBar()
    bar.setValue(bar.value() + direction * bar.pageStep())


def refresh(self) -> None:
    """根据当前页溢出和滚动位置同步导航可见性与边界状态。"""
    if self._current_scroll_area is None:
        self.hide()
        return
    bar = self._current_scroll_area.horizontalScrollBar()
    overflow = self._active and bar.maximum() > bar.minimum()
    self.setVisible(overflow)
    self.left_btn.setEnabled(overflow and bar.value() > bar.minimum())
    self.right_btn.setEnabled(overflow and bar.value() < bar.maximum())
```

`watch()` 对每个页面只连接一次 `rangeChanged`、`valueChanged`，并对其 viewport 安装 Resize 事件过滤器；`set_current()` 只切换当前页并刷新，不重复连接。Resize、Tab 切换和分组展开后的刷新通过 `QTimer.singleShot(0, self.refresh)` 延迟到布局完成。

图标必须使用 UIKit，并为 QIcon 显式提供禁用态：

```python
def _arrow_icon(name: str, icon_size: int) -> QIcon:
    """从 UIKit Iconoir 按统一行高构建普通/禁用两态箭头。"""
    icon = QIcon()
    icon.addPixmap(
        get_pixmap(name, icon_size, T("color.text.secondary")),
        QIcon.Mode.Normal,
    )
    icon.addPixmap(
        get_pixmap(name, icon_size, T("color.text.disabled")),
        QIcon.Mode.Disabled,
    )
    return icon
```

`_reload_icons()` 使用当前行高计算出的 `self._icon_size`，分别加载 `arrow-left` 和 `arrow-right`；`set_row_height()` 更新行高后也要调用它。`ThemeManager.instance().theme_changed.connect(self._on_theme_changed)`，主题回调重载图标并刷新。按钮文案为空，Tooltip 与 accessibleName 分别取 `skills_panel.navigation.previous` / `skills_panel.navigation.next`，不得设置为 `<-`、`->`。

- [ ] **Step 4: 复验导航、图标和主题场景**

Run: `.venv/bin/python scripts/smoke_skills_panel_modes.py --case navigation`

Expected: PASS；同时断言 `left_btn.text() == ""`、`right_btn.text() == ""`、两个 `QIcon` 均非空，主题回调后图标对象已刷新，禁用时按钮不可用。

- [ ] **Step 5: 在 test 分支添加真实滚动测试**

```python
def test_navigator_pages_and_disables_at_boundaries(qtbot):
    """溢出时显示 UIKit 箭头，按页滚动并在两端禁用对应按钮。"""
    scroll = QScrollArea()
    content = QWidget()
    content.setFixedSize(1200, 32)
    scroll.setWidget(content)
    scroll.resize(240, 48)
    navigator = SkillsScrollNavigator()
    navigator.set_row_height(24)
    navigator.watch(scroll)
    navigator.set_current(scroll)
    navigator.set_active(True)
    qtbot.addWidget(scroll)
    qtbot.addWidget(navigator)
    scroll.show()
    qtbot.waitUntil(lambda: scroll.horizontalScrollBar().maximum() > 0)
    navigator.refresh()
    bar = scroll.horizontalScrollBar()
    assert navigator.isVisible() is True
    assert navigator.left_btn.isEnabled() is False
    assert navigator.right_btn.isEnabled() is True
    previous = bar.value()
    navigator.right_btn.click()
    assert bar.value() == previous + bar.pageStep()
    bar.setValue(bar.maximum())
    assert navigator.right_btn.isEnabled() is False
```

另增无溢出隐藏、空当前页隐藏、viewport Resize 后刷新、普通/禁用图标非空四个测试，分别使用独立 widget，避免共享 Qt 状态。

- [ ] **Step 6: 运行测试并按规定提交**

Run: `.venv/bin/python -m pytest test/ui_tests/test_skills_panel_compact.py -q --tb=short -p no:cacheprovider`

Expected: PASS；提交前运行 `.venv/bin/python scripts/check_i18n_completeness.py`，四种语言均不得缺少新键。

---

### Task 3: SkillsPanel 单行紧凑布局与状态保持

**Files:**
- Modify: `ui/skills_panel/panel.py:16-369`
- Modify: `ui/skills_panel/plugin_group_widget.py:141-159`
- Modify: `ui/main_window.py:154-156`、`ui/main_window.py:519-529`
- Modify: `scripts/smoke_skills_panel_modes.py`
- Test（仅 `test` 分支）: `test/ui_tests/test_skills_panel_compact.py`

**Interfaces:**
- Consumes: Task 1 的 `set_compact()`、Task 2 的 `SkillsScrollNavigator`。
- Produces: `SKILLS_PANEL_RELAXED="relaxed"`、`SKILLS_PANEL_COMPACT="compact"`、`SKILLS_PANEL_MODES`、`SKILLS_HEADER_VERTICAL_MARGIN=6`、`SKILLS_PILL_VERTICAL_MARGIN=2`、`SkillsPanel.set_display_mode(mode: str)`、`SkillsPanel.display_mode`。

- [ ] **Step 1: 添加布局与状态保持失败场景**

冒烟加载两个未分组插件、一个含两个插件的分组和两个第三方插件，点击一个插件并展开分组，然后切换紧凑模式，断言：

```python
assert panel.display_mode == SKILLS_PANEL_COMPACT
assert panel.count_label.isHidden() is True
row_height = panel._compact_row_height()
assert panel.height() == (
    row_height
    + 2 * SKILLS_HEADER_VERTICAL_MARGIN
    + 2 * SKILLS_PILL_VERTICAL_MARGIN
)
assert panel._header_layout.indexOf(panel.stacked_widget) >= 0
assert panel._active_plugin is active_plugin
assert group_widget.is_expanded() is True
for index in range(2):
    button = panel.official_layout.itemAt(index).widget()
    assert button.height() == panel.official_btn.height()
    assert button.height() == panel.thirdparty_btn.height()
assert group_widget.folder_btn.height() == row_height
assert group_widget.expand_area.layout().itemAt(0).widget().height() == row_height
assert panel.scroll_navigator.left_btn.height() == row_height
assert panel.scroll_navigator.right_btn.height() == row_height
for scroll_area in panel._scroll_areas.values():
    assert scroll_area.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
```

随后切回宽松，断言计数器恢复、滚动条恢复 `ScrollBarAsNeeded`、面板恢复 125–135、激活插件和分组状态不变。

- [ ] **Step 2: 运行面板场景并确认失败**

Run: `.venv/bin/python scripts/smoke_skills_panel_modes.py --case panel`

Expected: FAIL，原因是 `set_display_mode()` 尚不存在。

- [ ] **Step 3: 实现模式状态和布局迁移**

`SkillsPanel.__init__()` 先按原结构创建宽松布局，再调用 `set_display_mode(SKILLS_PANEL_DEFAULT_MODE)`，默认进入紧凑布局。保存 `_main_layout`、`_header_layout`、两个 ScrollArea 和两个容器布局；`_create_skills_page()` 返回这些引用。紧凑切换使用：

```python
def set_display_mode(self, mode: str) -> None:
    """切换面板布局，不重建插件按钮或插件实例。"""
    if mode not in SKILLS_PANEL_MODES:
        raise ValueError(f"未知技能面板模式: {mode}")
    if mode == self._display_mode:
        return
    self._display_mode = mode
    compact = mode == SKILLS_PANEL_COMPACT
    row_height = self._compact_row_height() if compact else 0
    self._apply_button_mode(compact, row_height)
    self._apply_scroll_mode(compact, row_height)
    self._place_stacked_widget(compact)
    self._apply_panel_height(compact, row_height)
    self.count_label.setVisible(not compact)
    if compact:
        self.scroll_navigator.set_row_height(row_height)
    self.scroll_navigator.set_active(compact)
    self._schedule_navigation_refresh()


def _compact_row_height(self) -> int:
    """读取切换按钮行高；未显示时使用 sizeHint，显示后使用实际高度。"""
    if self.isVisible():
        return max(self.official_btn.height(), self.thirdparty_btn.height())
    return max(
        self.official_btn.sizeHint().height(),
        self.thirdparty_btn.sizeHint().height(),
    )


def _place_stacked_widget(self, compact: bool) -> None:
    """紧凑时把同一 Stack 移入 Header，宽松时移回第二行。"""
    if compact:
        self._main_layout.removeWidget(self.stacked_widget)
        index = self._header_layout.indexOf(self.scroll_navigator)
        self._header_layout.insertWidget(index, self.stacked_widget, 1)
        self._header_layout.setStretchFactor(self.count_label, 0)
    else:
        self._header_layout.removeWidget(self.stacked_widget)
        self._header_layout.setStretchFactor(self.count_label, 1)
        self._main_layout.addWidget(self.stacked_widget)
    self.stacked_widget.show()
```

其他辅助方法职责固定如下并完整实现：

- `_apply_button_mode(compact, row_height)`：遍历两个顶层布局；未分组按钮和分组控件都收到同一个 `row_height`，确保普通、文件夹和组内按钮等高。
- `_apply_scroll_mode(compact, row_height)`：紧凑设置水平 `ScrollBarAlwaysOff` 并将 ScrollArea 高度限制为 `row_height`，宽松恢复 `ScrollBarAsNeeded` 和原有尺寸约束；垂直始终关闭；紧凑容器边距为 4/0/4/0、间距 2，宽松恢复 4/2/4/2、间距 4。
- `_apply_panel_height(compact, row_height)`：紧凑设置为 `row_height + 2 * SKILLS_HEADER_VERTICAL_MARGIN + 2 * SKILLS_PILL_VERTICAL_MARGIN`，包含 Pill 容器与 Header 的既有垂直边距；宽松恢复 `setMinimumHeight(125)` 和 `setMaximumHeight(135)`。因此删除 MainWindow 中重复高度常量与两条设置语句。
- `_sync_compact_metrics()`：紧凑模式下重新读取 `_compact_row_height()`，同步全部按钮、ScrollArea、导航和面板高度；首次 `showEvent()`、语言切换及 `ThemeManager.theme_changed` 后通过零延迟 QTimer 调用，宽松模式直接返回。
- `_schedule_navigation_refresh()`：用零延迟单次 QTimer 调用 `scroll_navigator.refresh()`。

`_create_skill_button()` 按当前模式和 `_compact_row_height()` 初始化新按钮；`_add_group_widget()` 使用同一行高初始化分组，并将 `group_widget.toggled` 连接到 `_schedule_navigation_refresh()`。`_switch_tab()` 保留计数逻辑，同时调用 `scroll_navigator.set_current(self._scroll_areas[index])` 和刷新。`load_skills_from_manager()` 末尾调度刷新，覆盖插件安装/卸载后的溢出变化。

- [ ] **Step 4: 复验布局、Tab、分组和滚动位置**

Run: `.venv/bin/python scripts/smoke_skills_panel_modes.py --case panel`

Expected: PASS；额外验证官方/第三方各自滚动值在两次模式切换后保持，当前 Tab 不变，点击任一紧凑按钮仍只发出一次原插件对象的 `skill_clicked`。

- [ ] **Step 5: 在 test 分支添加面板测试**

新增测试覆盖：

1. 默认紧凑；切回宽松后布局和计数器保持不变。
2. 紧凑后 Stack 位于 Header、计数隐藏、水平条隐藏、所有顶层和组内按钮均紧凑。
3. 普通、组内、文件夹及导航按钮分别与两个切换按钮实际高度一致，面板高度等于统一行高加上下边距。
4. 首次显示、语言切换和主题切换后重新同步行高，不能只在首次进入紧凑模式时设置一次。
5. 切回宽松后尺寸、计数、滚动策略完整恢复。
6. 当前 Tab、激活插件、分组展开状态和两个页面的滚动值保持。
7. 无插件时紧凑区域为空且箭头隐藏；大量插件时出现箭头。
8. 非法模式抛出 `ValueError`，重复设置同一模式不重复迁移布局。

核心断言使用：

```python
def test_compact_mode_keeps_active_plugin_and_group_state(qtbot, loaded_panel):
    """模式切换只改变外观和布局，不破坏用户当前交互状态。"""
    panel = loaded_panel
    active_plugin = panel._active_plugin
    expanded = panel._expanded_group_ids()
    panel.set_display_mode(SKILLS_PANEL_COMPACT)
    assert panel._active_plugin is active_plugin
    assert panel._expanded_group_ids() == expanded
    assert panel.count_label.isHidden() is True
    assert panel._header_layout.indexOf(panel.stacked_widget) >= 0
    row_height = panel._compact_row_height()
    assert panel.scroll_navigator.left_btn.height() == row_height
    assert panel.scroll_navigator.right_btn.height() == row_height
    assert panel.official_layout.itemAt(0).widget().height() == row_height
    panel.set_display_mode(SKILLS_PANEL_RELAXED)
    assert panel._active_plugin is active_plugin
    assert panel._expanded_group_ids() == expanded
    assert panel.count_label.isHidden() is False
```

`loaded_panel` fixture 必须创建真实 `SkillButton`/`PluginGroupWidget`，只 mock 插件数据，不 mock 被测布局组件。

- [ ] **Step 6: 运行定向和回归测试并按规定提交**

Run: `.venv/bin/python -m pytest test/ui_tests/test_skills_panel_compact.py test/ui_tests/test_skills_panel.py -q --tb=short -p no:cacheprovider`

Expected: 新增与既有 SkillsPanel 测试全部 PASS；若既有测试因新结构必须修改，先停止并向用户说明目的与必要性，不在本计划中默认改写。

---

### Task 4: 编辑菜单切换动作与模式偏好持久化

**Files:**
- Modify: `ui/main_window.py:191-245`、`ui/main_window.py:397-496`、`ui/main_window.py:499-529`
- Modify: `ui/text/zh.xml`、`en.xml`、`fr.xml`、`ru.xml`
- Modify: `scripts/smoke_skills_panel_modes.py`
- Test（仅 `test` 分支）: `test/ui_tests/test_skills_panel_mode_action.py`

**Interfaces:**
- Consumes: Task 3 的模式常量、`SkillsPanel.set_display_mode()`、现有 `APP_CONFIG_PLUGIN_ID` 和 PRIVATE DataProvider。
- Produces: `SKILLS_PANEL_MODE_SETTING_KEY="skills_panel_mode"`、`_toggle_skills_panel_mode(checked: bool)`、`_set_skills_panel_mode(mode: str)`、`_load_saved_skills_panel_mode()`、`_save_skills_panel_mode()`。

- [ ] **Step 1: 添加菜单和偏好失败场景**

冒烟断言 `_menu_edit.actions()` 包含 `_action_skills_mode`，且其前一项恰好是 `_menu_theme_action`、后一项是语言动作；该动作不得出现在 MenuBar 顶层。动作可勾选，触发后 SkillsPanel 收到紧凑模式，动作文字显示当前模式；再次触发恢复宽松。DataProvider mock 分别返回 `compact`、非法字符串和抛出异常，验证重启恢复、非法值回退与保存失败不阻断。

- [ ] **Step 2: 运行菜单场景并确认失败**

Run: `.venv/bin/python scripts/smoke_skills_panel_modes.py --case menu`

Expected: FAIL，原因是 `_action_skills_mode` 和模式偏好方法尚不存在。

- [ ] **Step 3: 接入编辑菜单动作和启动顺序**

主窗口在读取偏好前设置 `_skills_panel_mode=SKILLS_PANEL_RELAXED`；在 `_load_saved_theme()` 之后调用 `_load_saved_skills_panel_mode()`，再创建菜单；在 `_create_main_layout()` 中、加载插件按钮前调用 `self.skills_panel.set_display_mode(self._skills_panel_mode)`。在现有 `_menu_theme_action` 加入编辑菜单之后、语言动作创建之前插入：

```python
self._action_skills_mode = QAction(self)
self._action_skills_mode.setCheckable(True)
self._action_skills_mode.triggered.connect(self._toggle_skills_panel_mode)
self._menu_edit.addAction(self._action_skills_mode)
```

因此最终编辑菜单顺序为「插件管理」「字体管理」「切换主题」「技能区模式」「语言」「GitHub Key 管理」。

模式分发和偏好保存使用：

```python
def _toggle_skills_panel_mode(self, checked: bool) -> None:
    """根据菜单勾选状态切换技能区模式。"""
    mode = SKILLS_PANEL_COMPACT if checked else SKILLS_PANEL_RELAXED
    self._set_skills_panel_mode(mode)


def _set_skills_panel_mode(self, mode: str) -> None:
    """应用模式并尝试保存；保存失败不撤销用户本次选择。"""
    self._skills_panel_mode = mode
    panel = getattr(self, "skills_panel", None)
    if panel is not None:
        panel.set_display_mode(mode)
    self._update_skills_mode_action()
    self._save_skills_panel_mode()
```

`_load_saved_skills_panel_mode()` 从 PRIVATE 键读取并校验 `SKILLS_PANEL_MODES`；`_save_skills_panel_mode()` 使用 `notify=False`。两者异常均记录包含操作上下文的 WARNING，默认/回退值为 `compact`。

`_update_skills_mode_action()` 同步 checked、当前模式文字和 Tooltip；`_retranslate_ui()` 末尾调用它。新增四语言键：`main_window.menu.edit.skills_mode.current`、`main_window.menu.edit.skills_mode.tooltip`、`skills_panel.mode.relaxed`、`skills_panel.mode.compact`。

- [ ] **Step 4: 复验菜单、四语言和保存失败降级**

Run: `.venv/bin/python scripts/smoke_skills_panel_modes.py --case menu`

Expected: PASS；随后运行 `.venv/bin/python scripts/check_i18n_completeness.py`，默认语言覆盖全部新 `tr()`，其他语言无新增缺键。

- [ ] **Step 5: 在 test 分支添加动作与异常路径测试**

```python
def test_mode_action_below_theme_and_toggles_panel(mocker, qtbot, window_with_menus):
    """编辑菜单中的模式动作紧跟主题切换，并能切换和保存紧凑模式。"""
    window = window_with_menus
    window.skills_panel = MagicMock()
    save = mocker.patch.object(window, "_save_skills_panel_mode")
    actions = window._menu_edit.actions()
    mode_index = actions.index(window._action_skills_mode)
    assert actions[mode_index - 1] is window._menu_theme_action
    assert actions[mode_index + 1] is window._action_language
    assert window._action_skills_mode not in window.menuBar().actions()
    window._action_skills_mode.trigger()
    window.skills_panel.set_display_mode.assert_called_once_with(SKILLS_PANEL_COMPACT)
    save.assert_called_once_with()
    assert window._action_skills_mode.isChecked() is True


def test_invalid_saved_mode_falls_back_to_compact(mocker):
    """非法持久化值不得进入面板，启动回退默认紧凑模式。"""
    provider = MagicMock()
    provider.get_plugin_data.return_value = "unexpected-mode"
    mocker.patch("ui.main_window.DataProvider", return_value=provider)
    owner = SimpleNamespace(_logger=MagicMock(), _skills_panel_mode=SKILLS_PANEL_COMPACT)
    InstructionXMainWindow._load_saved_skills_panel_mode(owner)
    assert owner._skills_panel_mode == SKILLS_PANEL_COMPACT
```

另增保存异常测试：mock `set_plugin_data()` 抛出 `RuntimeError("disk full")`，确认 `_save_skills_panel_mode()` 不向外抛出，且 `_logger.warning` 被调用一次；再验证 `_set_skills_panel_mode()` 已先更新面板和动作。

- [ ] **Step 6: 运行定向、主窗口回归和全量测试**

Run: `.venv/bin/python -m pytest test/ui_tests/test_skills_panel_mode_action.py test/ui_tests/test_main_window.py test/ui_tests/test_close_event_dispatch.py -q --tb=short -p no:cacheprovider`

Expected: PASS。既有测试若需修改，先向用户说明并取得认可。

---

### Task 5: 文档同步与端到端验收

**Files:**
- Modify: `docs/ui/skills-panel.md`
- Modify: `docs/ui/skill-button.md`
- Modify: `docs/ui/main-window.md`
- Modify: `docs/architecture/overview.md`
- Modify: `AGENTS.md`
- Modify: `scripts/smoke_skills_panel_modes.py`

**Interfaces:**
- Consumes: Task 1–4 最终代码与测试。
- Produces: 与实现一致的双模式文档、真实窗口验收结果和可复现冒烟入口。

- [ ] **Step 1: 更新文档与实际接口**

文档明确两种布局、默认紧凑、紧凑尺寸、完整名称 Tooltip、分组行为、溢出箭头、隐藏滚动条、菜单位置和持久化键。同步 `SkillsPanel` 公共方法、模式常量、`SkillsScrollNavigator` 职责以及 MainWindow 不再持有面板高度常量的事实。

- [ ] **Step 2: 运行完整自动化验证**

```bash
.venv/bin/python scripts/smoke_skills_panel_modes.py
.venv/bin/python scripts/check_i18n_completeness.py
.venv/bin/python -m pytest test/ -q --tb=short -p no:cacheprovider
```

Expected: 三条命令均退出 0；pytest 在 `test` 分支执行。任何既有失败先核对基线，不混入无关修复。

- [ ] **Step 3: 在真实窗口完成端到端验收**

使用 `.venv/bin/python main.py` 启动应用，并逐项确认：

1. 首次启动或非法配置时为宽松模式，外观与改动前一致。
2. 通过「编辑 → 切换主题」正下方的模式菜单项进入紧凑模式后，Skills Area 变为单行，WorkArea 自动获得释放的垂直空间；普通插件、组内插件、文件夹和左右箭头均与【官方｜第三方】切换按钮实际等高。
3. 插件按钮只有 Logo，长名称、含换行名称悬停均显示完整 `plugin_name`，点击仍打开原插件并保持高亮；语言和主题切换后所有紧凑按钮仍与切换按钮等高。
4. 分组文件夹可展开/收起，组内按钮同样紧凑；展开导致溢出后箭头出现，收起后按实际溢出隐藏。
5. 无溢出时无箭头；大量插件和 800px 最小窗口下出现左右箭头，点击按页滚动，两端禁用，全程无可见水平滚动条。
6. 官方/第三方切换后计数逻辑、插件顺序和各页滚动位置正确；模式往返不丢失 Tab、激活插件或分组展开状态。
7. 浅色、深色和跟随系统主题下箭头均可读，禁用态明确，Iconoir 图标清晰；高 DPI 下不模糊。
8. 中、英、法、俄界面实时切换后菜单和导航 Tooltip 文案正确。
9. 重启后恢复上次模式；模拟保存失败时模式仍切换且日志包含 WARNING，不弹出阻断性异常。
10. macOS Cocoa 与 Windows 各完成一次真实窗口验收；Windows 额外验证 Canvas/RHI 插件打开时紧凑区域无点击穿透。

- [ ] **Step 4: 保存必要截图并清理临时产物**

截图仅保存到 `temp/skills-panel-modes/`，至少包含宽松、紧凑无溢出、紧凑溢出、分组展开、深色禁用箭头五种状态。验收完成后删除不再需要的临时配置和日志，不提交 `temp/`。

- [ ] **Step 5: 最终交叉核对并请求文档提交确认**

```bash
git status --short --branch
git diff --check
```

Expected: 无空白错误、无测试代码进入 `dev`、无 `temp/` 文件、无插件目录或 UIKit 库改动。确认文档与代码一致后，按用户确认的提交信息提交文档。

## 完成标准

- 宽松模式默认且行为不回归；紧凑模式严格为单行 Logo 列表并释放 WorkArea 高度。
- 所有紧凑插件/分组/导航按钮与切换按钮实际等高；首次显示、语言和主题变化后仍保持一致。
- 计数器只在宽松模式显示；水平滚动指示条在紧凑模式始终不可见。
- 溢出箭头只在需要时出现，使用 UIKit Iconoir，分页滚动和边界禁用正确。
- 插件全名 Tooltip、插件点击、Tab、激活、分组、滚动位置和主题均正确。
- 模式可从「编辑」菜单中「切换主题」正下方的入口切换，并通过 PRIVATE `skills_panel_mode` 持久化、在重启后恢复；配置异常有安全回退和日志。
- 新增正常、边界、异常测试通过，全量 pytest、i18n 校验和真实窗口端到端验收通过。
