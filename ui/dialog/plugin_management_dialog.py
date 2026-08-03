"""
插件管理对话框

集成插件的安装、升级/降级、卸载与自定义分组/排序管理：
- 「插件管理」页：插件列表、版本信息、检查更新、升级/降级、卸载、
  从 GitHub 安装、安装本地插件包
- 「分组与排序」页：在官方/第三方分类下维护自定义分组（命名、图标、
  组内成员），并在统一「面板顺序」列表中混排分组与未分组插件的位置
"""

from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QListWidget, QListWidgetItem, QTabWidget,
    QFileDialog, QFrame,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont

from core.plugin.manager import PluginManager
from core.plugin.github_plugin_installer import (
    GitHubPluginInstaller, InstallResult, ReleaseInfo,
)
from core.plugin.plugin_groups import (
    PluginGroup, GROUP_ICON_CHOICES,
    ITEM_TYPE_GROUP, ITEM_TYPE_PLUGIN,
)
from core.plugin.plugin_version import PluginVersion
from ui.dialog.github_plugin_install_dialog import GitHubPluginInstallDialog
from utils.logging_tools import LoggerManager, get_name
from InstructionX_UIKit import T
from InstructionX_UIKit.components import (
    Button, CheckBox, ComboBox, Dialog, LineEdit, Message,
)

# 模块级日志器（LoggerManager 为单例）
_logger = LoggerManager()


def _confirm(parent, title: str, text: str) -> bool:
    """阻塞式确认对话框（UIKit Dialog，替代 QMessageBox.question）"""
    dialog = Dialog(parent, title=title)
    dialog.set_text(text)
    return dialog.exec() == QDialog.DialogCode.Accepted


def _notice(parent, title: str, text: str) -> None:
    """阻塞式结果告知对话框（UIKit Dialog，替代 QMessageBox.information/warning）"""
    dialog = Dialog(parent, title=title, ok_text="知道了", show_cancel=False)
    dialog.set_text(text)
    dialog.exec()


def _prompt_text(parent, title: str, label: str, text: str = "") -> Tuple[str, bool]:
    """单行文本输入对话框（UIKit Dialog + LineEdit，替代 QInputDialog.getText）"""
    dialog = Dialog(parent, title=title)
    content = QWidget()
    lay = QVBoxLayout(content)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(QLabel(label))
    edit = LineEdit(text=text)
    lay.addWidget(edit)
    dialog.set_content(content)
    ok = dialog.exec() == QDialog.DialogCode.Accepted
    return edit.text(), ok


def _prompt_item(parent, title: str, label: str, items: List[str],
                 current: int = 0) -> Tuple[str, bool]:
    """下拉选择对话框（UIKit Dialog + ComboBox，替代 QInputDialog.getItem）"""
    dialog = Dialog(parent, title=title)
    content = QWidget()
    lay = QVBoxLayout(content)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(QLabel(label))
    combo = ComboBox(items=items)
    if 0 <= current < len(items):
        combo.setCurrentIndex(current)
    lay.addWidget(combo)
    dialog.set_content(content)
    ok = dialog.exec() == QDialog.DialogCode.Accepted
    return combo.currentText(), ok


def _bold_label(text: str) -> QLabel:
    """加粗小标签（替代旧 captionBold 动态属性）"""
    label = QLabel(text)
    font = QFont()
    font.setPixelSize(T("font.sm"))
    font.setBold(True)
    label.setFont(font)
    return label


def _version_relation(current: str, candidate: str) -> str:
    """计算候选版本相对当前版本的关系标签

    Args:
        current: 当前版本字符串
        candidate: 候选版本字符串

    Returns:
        "升级" / "降级" / "重装" / "未知"
    """
    try:
        cur = PluginVersion.from_string(current)
        cand = PluginVersion.from_string(candidate)
    except ValueError:
        return "未知"
    if cand > cur:
        return "升级"
    if cand < cur:
        return "降级"
    return "重装"


class _Worker(QThread):
    """通用后台任务线程（网络下载/安装等耗时操作不阻塞 UI）"""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        """执行任务并通过信号返回结果或错误"""
        try:
            self.succeeded.emit(self._fn())
        except Exception as e:
            self.failed.emit(str(e))


class VersionSelectDialog(QDialog):
    """版本选择对话框：列出 Release 版本供升级/降级选择"""

    def __init__(self, plugin_name: str, current_version: str,
                 releases: List[ReleaseInfo], parent=None):
        """初始化版本选择对话框

        Args:
            plugin_name: 插件名称
            current_version: 当前安装版本
            releases: 可选版本列表
            parent: 父窗口
        """
        super().__init__(parent)
        self.selected: Optional[ReleaseInfo] = None
        self._releases = releases
        self.setWindowTitle(f"选择版本 - {plugin_name}")
        self.setMinimumSize(460, 360)
        self._init_ui(plugin_name, current_version)

    def _init_ui(self, plugin_name: str, current_version: str) -> None:
        """构建界面"""
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"当前版本: {current_version or '未知'}"))

        self.list_widget = QListWidget()
        for rel in self._releases:
            relation = _version_relation(current_version, rel.version)
            version_text = rel.version or "未知版本"
            item = QListWidgetItem(f"{rel.tag}  —  {version_text}（{relation}）")
            if relation == "降级":
                item.setForeground(QColor(T("color.warning")))
            self.list_widget.addItem(item)
        if self.list_widget.count():
            self.list_widget.setCurrentRow(0)
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = Button("取消", variant="default")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = Button("安装所选版本", variant="primary")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_accept)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

    def _on_accept(self) -> None:
        """确认选择"""
        row = self.list_widget.currentRow()
        if row < 0:
            Message.warning(self, "请选择要安装的版本")
            return
        self.selected = self._releases[row]
        self.accept()


class GroupEditorWidget(QWidget):
    """单个 scope 的分组与排序编辑器（工作副本，保存时统一提交）

    左侧「面板顺序」为分组与未分组插件的统一混排列表（决定技能面板中
    分组文件夹与插件按钮的相对位置）；右侧「组内插件」编辑当前选中
    分组的成员与组内顺序。
    """

    def __init__(self, plugin_manager: PluginManager, scope: str, parent=None):
        """初始化分组编辑器

        Args:
            plugin_manager: 插件管理器
            scope: "official" 或 "thirdparty"
            parent: 父控件
        """
        super().__init__(parent)
        self.pm = plugin_manager
        self.scope = scope
        self.groups: List[PluginGroup] = []
        self._panel_items: List[Tuple[str, str]] = []
        self._current_group_id: Optional[str] = None
        self._init_ui()
        self.reload()

    # ==================== 界面构建 ====================

    def _init_ui(self) -> None:
        """构建两栏界面：面板顺序 / 分组穿梭框"""
        layout = QHBoxLayout(self)
        layout.setSpacing(12)

        self.panel_list = QListWidget()
        self.panel_list.currentRowChanged.connect(self._on_panel_selection)
        layout.addLayout(self._build_column(
            "面板顺序（分组 / 插件）", self.panel_list, self._panel_buttons()
        ))

        layout.addWidget(self._build_shuttle_box(), stretch=1)

    def _build_shuttle_box(self) -> QWidget:
        """构建分组穿梭框（标题 + 未分组插件 ⇄ 组内插件）

        未选中分组时整体隐藏；选中分组后显示该分组的成员配置。
        """
        self.shuttle_box = QWidget()
        box_layout = QVBoxLayout(self.shuttle_box)
        box_layout.setContentsMargins(0, 0, 0, 0)

        # 标题：显示当前选中的分组
        self.group_title = _bold_label("")
        box_layout.addWidget(self.group_title)

        # 穿梭区：未分组插件 | 按钮列 | 组内插件（含排序）
        shuttle_layout = QHBoxLayout()

        self.available_list = QListWidget()
        available_column = QVBoxLayout()
        available_label = QLabel("未分组插件")
        available_column.addWidget(available_label)
        available_column.addWidget(self.available_list, stretch=1)
        shuttle_layout.addLayout(available_column, stretch=1)

        btn_column = QVBoxLayout()
        btn_column.addStretch()
        for text, handler in (("→", self._on_assign_member),
                              ("←", self._on_remove_member),
                              ("上移", lambda: self._move_member(-1)),
                              ("下移", lambda: self._move_member(1))):
            btn = Button(text, variant="default", size="sm")
            btn.setFixedWidth(56)
            btn.clicked.connect(handler)
            btn_column.addWidget(btn)
        btn_column.addStretch()
        shuttle_layout.addLayout(btn_column)

        self.member_list = QListWidget()
        member_column = QVBoxLayout()
        member_label = QLabel("组内插件")
        member_column.addWidget(member_label)
        member_column.addWidget(self.member_list, stretch=1)
        shuttle_layout.addLayout(member_column, stretch=1)

        box_layout.addLayout(shuttle_layout, stretch=1)
        self.shuttle_box.setVisible(False)
        return self.shuttle_box

    def _build_column(self, title: str, list_widget: QListWidget,
                      buttons: List[Button]) -> QVBoxLayout:
        """构建一栏：标题 + 列表 + 按钮组"""
        column = QVBoxLayout()
        column.addWidget(_bold_label(title))
        column.addWidget(list_widget, stretch=1)
        btn_layout = QGridLayout()
        for index, btn in enumerate(buttons):
            btn_layout.addWidget(btn, index // 2, index % 2)
        column.addLayout(btn_layout)
        return column

    def _panel_buttons(self) -> List[Button]:
        """面板顺序列表的操作按钮"""
        specs = [
            ("新建分组", self._on_new_group), ("重命名", self._on_rename_group),
            ("设置图标", self._on_group_icon), ("删除分组", self._on_delete_group),
            ("上移", lambda: self._move_panel_item(-1)),
            ("下移", lambda: self._move_panel_item(1)),
        ]
        return [self._make_button(text, handler) for text, handler in specs]

    def _make_button(self, text: str, handler: Callable) -> Button:
        """创建按钮并连接处理函数"""
        btn = Button(text, variant="default", size="sm")
        btn.clicked.connect(handler)
        return btn

    # ==================== 数据加载与刷新 ====================

    def reload(self) -> None:
        """从存储重新加载工作副本（外部变更后调用）"""
        self.groups = list(self.pm.get_groups(self.scope))
        self._current_group_id = None
        self._rebuild_panel_items()
        self._refresh_panel_list()
        self._update_shuttle_state()

    def _rebuild_panel_items(self) -> None:
        """按「存储顺序 + 新分组 + 未分组插件」重建统一面板顺序"""
        if self.scope == "official":
            plugins = self.pm.get_official_plugins()
        else:
            plugins = self.pm.get_thirdparty_plugins()
        by_id = {p.plugin_id: p for p in plugins if p.plugin_id}
        group_ids = {g.id for g in self.groups}
        assigned = {pid for g in self.groups for pid in g.plugins}

        items: List[Tuple[str, str]] = []
        seen = set()
        for item_type, item_id in self.pm.group_store.load_order(self.scope):
            if item_type == ITEM_TYPE_GROUP and item_id in group_ids:
                items.append((item_type, item_id))
                seen.add((ITEM_TYPE_GROUP, item_id))
            elif (item_type == ITEM_TYPE_PLUGIN and item_id in by_id
                  and item_id not in assigned and item_id not in seen):
                items.append((item_type, item_id))
                seen.add(item_id)

        for group in self.groups:
            if (ITEM_TYPE_GROUP, group.id) not in seen:
                items.append((ITEM_TYPE_GROUP, group.id))
        for uuid in self._ungrouped_order(by_id, assigned):
            if uuid not in seen:
                items.append((ITEM_TYPE_PLUGIN, uuid))
                seen.add(uuid)
        self._panel_items = items

    def _ungrouped_order(self, by_id: dict, assigned: set) -> List[str]:
        """未分组插件 UUID 列表（按 plugin_order 顺序，新插件追加在后）"""
        order_key = ("official_plugins" if self.scope == "official"
                     else "thirdparty_plugins")
        order = self.pm.config_manager.load_plugin_order().get(order_key, [])
        result = [uuid for uuid in order if uuid in by_id and uuid not in assigned]
        seen = set(result)
        for uuid in by_id:
            if uuid not in assigned and uuid not in seen:
                result.append(uuid)
        return result

    def _refresh_panel_list(self) -> None:
        """刷新面板顺序列表（保持选中项）"""
        row = self.panel_list.currentRow()
        self.panel_list.blockSignals(True)
        self.panel_list.clear()
        for item_type, item_id in self._panel_items:
            item = QListWidgetItem(self._panel_item_text(item_type, item_id))
            item.setData(Qt.ItemDataRole.UserRole, (item_type, item_id))
            self.panel_list.addItem(item)
        self.panel_list.blockSignals(False)
        if 0 <= row < self.panel_list.count():
            self.panel_list.setCurrentRow(row)

    def _panel_item_text(self, item_type: str, item_id: str) -> str:
        """面板顺序条目的显示文本"""
        if item_type == ITEM_TYPE_GROUP:
            group = self._find_group(item_id)
            if group:
                return f"{group.icon_key} {group.name}"
            return f"(已失效分组) {item_id[:8]}"
        plugin = self.pm.get_plugin_by_id(item_id)
        return plugin.plugin_name if plugin else f"(已移除) {item_id[:8]}"

    def _refresh_members(self) -> None:
        """刷新当前选中分组的组内插件列表"""
        self.member_list.clear()
        group = self._current_group()
        if group is None:
            return
        for uuid in group.plugins:
            plugin = self.pm.get_plugin_by_id(uuid)
            name = plugin.plugin_name if plugin else f"(已移除) {uuid[:8]}"
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, uuid)
            self.member_list.addItem(item)

    def _refresh_available(self) -> None:
        """刷新穿梭框的未分组插件列表（来自面板顺序中的插件条目）"""
        self.available_list.clear()
        for item_type, item_id in self._panel_items:
            if item_type != ITEM_TYPE_PLUGIN:
                continue
            plugin = self.pm.get_plugin_by_id(item_id)
            name = plugin.plugin_name if plugin else f"(已移除) {item_id[:8]}"
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, item_id)
            self.available_list.addItem(item)

    def _update_shuttle_state(self) -> None:
        """根据当前选中的面板条目更新穿梭框可见性与内容

        选中分组：显示标题（分组图标+名称）与穿梭框；
        未选中分组：整体隐藏。
        """
        group = self._current_group()
        self.shuttle_box.setVisible(group is not None)
        if group is None:
            return
        self.group_title.setText(f"组内配置：{group.icon_key} {group.name}")
        self._refresh_available()
        self._refresh_members()

    # ==================== 选择与查找 ====================

    def _find_group(self, group_id: str) -> Optional[PluginGroup]:
        """按 ID 查找工作副本中的分组"""
        for group in self.groups:
            if group.id == group_id:
                return group
        return None

    def _current_group(self) -> Optional[PluginGroup]:
        """当前目标分组（最近一次选中的分组条目）"""
        if self._current_group_id is None:
            return None
        return self._find_group(self._current_group_id)

    def _selected_panel_item(self) -> Optional[Tuple[int, str, str]]:
        """当前选中的面板条目，返回 (行号, 类型, id)"""
        row = self.panel_list.currentRow()
        if not (0 <= row < len(self._panel_items)):
            return None
        item_type, item_id = self._panel_items[row]
        return row, item_type, item_id

    def _on_panel_selection(self, row: int) -> None:
        """面板条目选中变化：选中分组时展示其穿梭框，否则隐藏"""
        if 0 <= row < len(self._panel_items):
            item_type, item_id = self._panel_items[row]
            self._current_group_id = item_id if item_type == ITEM_TYPE_GROUP else None
        else:
            self._current_group_id = None
        self._update_shuttle_state()

    # ==================== 分组操作 ====================

    def _on_new_group(self) -> None:
        """新建分组（追加到面板顺序末尾）"""
        name, ok = _prompt_text(self, "新建分组", "分组名称:")
        if ok and name.strip():
            group = PluginGroup.new(name.strip())
            self.groups.append(group)
            self._panel_items.append((ITEM_TYPE_GROUP, group.id))
            self._refresh_panel_list()
            self.panel_list.setCurrentRow(self.panel_list.count() - 1)

    def _on_rename_group(self) -> None:
        """重命名选中的分组"""
        group = self._selected_group_item()
        if group is None:
            return
        name, ok = _prompt_text(self, "重命名分组", "分组名称:", text=group.name)
        if ok and name.strip():
            group.name = name.strip()
            self._refresh_after_group_change(group)

    def _on_group_icon(self) -> None:
        """设置选中分组的图标"""
        group = self._selected_group_item()
        if group is None:
            return
        current = GROUP_ICON_CHOICES.index(group.icon_key) \
            if group.icon_key in GROUP_ICON_CHOICES else 0
        icon, ok = _prompt_item(
            self, "设置图标", "选择分组图标:", GROUP_ICON_CHOICES, current
        )
        if ok and icon:
            group.icon_key = icon
            self._refresh_after_group_change(group)

    def _selected_group_item(self) -> Optional[PluginGroup]:
        """获取面板列表中选中的分组（选中插件时提示并返回 None）"""
        selected = self._selected_panel_item()
        if selected is None or selected[1] != ITEM_TYPE_GROUP:
            Message.info(self, "请先在左侧列表中选中一个分组")
            return None
        return self._find_group(selected[2])

    def _on_delete_group(self) -> None:
        """删除选中分组（组内插件变为未分组，插入到分组原位置）"""
        selected = self._selected_panel_item()
        if selected is None or selected[1] != ITEM_TYPE_GROUP:
            Message.info(self, "请先在左侧列表中选中一个分组")
            return
        row, _type, group_id = selected
        group = self._find_group(group_id)
        if group is None:
            return
        self.groups.remove(group)
        del self._panel_items[row]
        for offset, uuid in enumerate(group.plugins):
            self._panel_items.insert(row + offset, (ITEM_TYPE_PLUGIN, uuid))
        if self._current_group_id == group_id:
            self._current_group_id = None
        self._refresh_panel_list()
        self._update_shuttle_state()

    def _move_panel_item(self, delta: int) -> None:
        """面板顺序条目上移/下移（分组与插件混排）"""
        row = self.panel_list.currentRow()
        target = row + delta
        if 0 <= row < len(self._panel_items) and 0 <= target < len(self._panel_items):
            self._panel_items[row], self._panel_items[target] = \
                self._panel_items[target], self._panel_items[row]
            self._refresh_panel_list()
            self.panel_list.setCurrentRow(target)

    # ==================== 成员操作 ====================

    def _on_assign_member(self) -> None:
        """将穿梭框中选中的未分组插件加入当前分组"""
        group = self._current_group()
        item = self.available_list.currentItem()
        if group is None:
            Message.info(self, "请先在左侧列表中选中目标分组")
            return
        if item is None:
            Message.info(self, "请在「未分组插件」中选中要加入的插件")
            return
        uuid = item.data(Qt.ItemDataRole.UserRole)
        if uuid not in group.plugins:
            group.plugins.append(uuid)
        self._remove_panel_plugin_entry(uuid)
        self._refresh_panel_list()
        self._update_shuttle_state()

    def _remove_panel_plugin_entry(self, uuid: str) -> None:
        """从面板顺序中移除指定插件条目"""
        self._panel_items = [
            entry for entry in self._panel_items
            if not (entry[0] == ITEM_TYPE_PLUGIN and entry[1] == uuid)
        ]

    def _on_remove_member(self) -> None:
        """将选中插件移出分组（回到面板顺序中分组之后的位置）"""
        group = self._current_group()
        row = self.member_list.currentRow()
        if group is None or not (0 <= row < len(group.plugins)):
            return
        uuid = group.plugins.pop(row)
        insert_at = self._panel_insert_position(group.id)
        self._panel_items.insert(insert_at, (ITEM_TYPE_PLUGIN, uuid))
        self._refresh_panel_list()
        self._update_shuttle_state()

    def _panel_insert_position(self, group_id: str) -> int:
        """计算移出分组的插件在面板顺序中的插入位置（分组条目之后）"""
        for index, (item_type, item_id) in enumerate(self._panel_items):
            if item_type == ITEM_TYPE_GROUP and item_id == group_id:
                return index + 1
        return len(self._panel_items)

    def _move_member(self, delta: int) -> None:
        """组内插件排序上移/下移"""
        group = self._current_group()
        row = self.member_list.currentRow()
        target = row + delta
        if group is None or not (0 <= row < len(group.plugins)):
            return
        if 0 <= target < len(group.plugins):
            group.plugins[row], group.plugins[target] = \
                group.plugins[target], group.plugins[row]
            self._refresh_members()
            self.member_list.setCurrentRow(target)

    def _refresh_after_group_change(self, group: PluginGroup) -> None:
        """分组名称/图标变更后刷新面板列表与穿梭框标题"""
        self._refresh_panel_list()
        if self._current_group() is group:
            self.group_title.setText(f"组内配置：{group.icon_key} {group.name}")

    # ==================== 提交 ====================

    def collect_panel_order(self) -> List[Tuple[str, str]]:
        """收集面板统一顺序（分组与未分组插件混排条目）"""
        return list(self._panel_items)


class PluginManagementDialog(QDialog):
    """
    插件管理对话框

    集成插件的安装、升级/降级、卸载与自定义分组/排序管理。

    Signals:
        plugins_changed: 插件集合或分组/排序发生变化（主窗口应刷新技能面板）
    """

    plugins_changed = Signal()

    # (scope, 显示名)
    SCOPES = (("official", "官方插件"), ("thirdparty", "第三方插件"))

    def __init__(self, plugin_manager: PluginManager, parent=None):
        """初始化插件管理对话框

        Args:
            plugin_manager: 插件管理器实例
            parent: 父窗口
        """
        super().__init__(parent)
        self.pm = plugin_manager
        self.installer = GitHubPluginInstaller(plugin_manager)
        self._worker: Optional[_Worker] = None
        self._plugin_lists: Dict[str, QListWidget] = {}
        self._group_editors: Dict[str, GroupEditorWidget] = {}
        self.setWindowTitle("插件管理")
        self.setMinimumSize(860, 560)
        self._init_ui()
        self.reload_plugin_lists()

    # ==================== 界面构建 ====================

    def _init_ui(self) -> None:
        """构建界面：管理页 + 分组排序页 + 底部按钮"""
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_manage_tab(), "插件管理")
        self.tabs.addTab(self._build_groups_tab(), "分组与排序")
        layout.addWidget(self.tabs, stretch=1)

        close_btn = Button("关闭", variant="default")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.accept)
        bottom = QHBoxLayout()
        bottom.addStretch()
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

    def _build_manage_tab(self) -> QWidget:
        """构建「插件管理」页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        toolbar = QHBoxLayout()
        for text, handler in (("从 GitHub 安装插件…", self._on_install_github),
                              ("安装本地插件包…", self._on_install_zip),
                              ("刷新", self._on_refresh)):
            btn = Button(text, variant="default")
            btn.clicked.connect(handler)
            toolbar.addWidget(btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        body = QHBoxLayout()
        self.scope_tabs = QTabWidget()
        for scope, title in self.SCOPES:
            list_widget = QListWidget()
            list_widget.currentItemChanged.connect(
                lambda item, _prev, s=scope: self._on_plugin_selected(s, item)
            )
            self._plugin_lists[scope] = list_widget
            self.scope_tabs.addTab(list_widget, title)
        body.addWidget(self.scope_tabs, stretch=2)
        body.addWidget(self._build_detail_panel(), stretch=1)
        layout.addLayout(body, stretch=1)
        return tab

    def _build_detail_panel(self) -> QFrame:
        """构建右侧插件详情与操作面板"""
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(panel)

        self.detail_name = QLabel("未选择插件")
        self.detail_name.setWordWrap(True)
        self.detail_version = QLabel("")
        self.detail_source = QLabel("")
        self.detail_source.setWordWrap(True)
        for label in (self.detail_name, self.detail_version, self.detail_source):
            layout.addWidget(label)
        layout.addSpacing(10)

        self.update_btn = Button("检查更新 / 升级 / 降级…", variant="default")
        self.update_btn.clicked.connect(self._on_check_updates)
        self.uninstall_btn = Button("卸载…", variant="danger")
        self.uninstall_btn.clicked.connect(self._on_uninstall)
        layout.addWidget(self.update_btn)
        layout.addWidget(self.uninstall_btn)
        layout.addStretch()
        return panel

    def _build_groups_tab(self) -> QWidget:
        """构建「分组与排序」页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.group_scope_tabs = QTabWidget()
        for scope, title in self.SCOPES:
            editor = GroupEditorWidget(self.pm, scope)
            self._group_editors[scope] = editor
            self.group_scope_tabs.addTab(editor, title)
        layout.addWidget(self.group_scope_tabs, stretch=1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        reset_btn = Button("重置", variant="default")
        reset_btn.clicked.connect(self._on_groups_reset)
        save_btn = Button("保存分组与排序", variant="primary")
        save_btn.clicked.connect(self._on_groups_save)
        btn_layout.addWidget(reset_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)
        return tab

    # ==================== 插件列表 ====================

    def reload_plugin_lists(self) -> None:
        """刷新两个 scope 的插件列表（显示名称与版本）"""
        for scope, _title in self.SCOPES:
            list_widget = self._plugin_lists[scope]
            list_widget.clear()
            plugins = (self.pm.get_official_plugins() if scope == "official"
                       else self.pm.get_thirdparty_plugins())
            for plugin in plugins:
                record = self.pm.registry.get(plugin.plugin_id) or {}
                version = record.get("version", "")
                text = plugin.plugin_name
                if version:
                    text += f"  (v{version})"
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, plugin.plugin_id)
                list_widget.addItem(item)
        self._on_plugin_selected(self._current_scope(), None)

    def _current_scope(self) -> str:
        """当前「插件管理」页选中的 scope"""
        return self.SCOPES[self.scope_tabs.currentIndex()][0]

    def _selected_plugin_id(self) -> Optional[str]:
        """当前选中的插件 UUID"""
        list_widget = self._plugin_lists[self._current_scope()]
        item = list_widget.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _on_plugin_selected(self, scope: str, item: Optional[QListWidgetItem]) -> None:
        """插件选中变化时刷新详情面板"""
        if item is None:
            self.detail_name.setText("未选择插件")
            self.detail_version.setText("")
            self.detail_source.setText("")
            return
        uuid = item.data(Qt.ItemDataRole.UserRole)
        record = self.pm.registry.get(uuid) or {}
        self.detail_name.setText(f"名称: {record.get('name', item.text())}")
        self.detail_version.setText(f"版本: {record.get('version', '未知')}")
        source = record.get("source_url") or record.get("source_type", "未知")
        self.detail_source.setText(f"来源: {source}")

    # ==================== 安装 / 升级 / 降级 ====================

    def _on_install_github(self) -> None:
        """打开 GitHub 安装对话框，完成后刷新"""
        dialog = GitHubPluginInstallDialog(self)
        dialog.plugin_installed.connect(lambda _results: self._refresh_after_change())
        dialog.exec()

    def _on_install_zip(self) -> None:
        """选择本地插件包并安装"""
        zip_path, _selected = QFileDialog.getOpenFileName(
            self, "选择插件包", "", "Zip 文件 (*.zip)"
        )
        if not zip_path:
            return
        self._run_background(
            lambda: self.installer.install_from_zip(zip_path),
            self._on_install_results,
        )

    def _on_check_updates(self) -> None:
        """检查选中插件的可用版本（GitHub Release）"""
        uuid = self._selected_plugin_id()
        if uuid is None:
            Message.info(self, "请先选择插件")
            return
        record = self.pm.registry.get(uuid)
        if not record or record.get("source_type") != "github" or not record.get("source_url"):
            Message.info(
                self,
                "该插件没有记录 GitHub 来源，无法检查更新。\n可使用「安装本地插件包」手动升级/降级。"
            )
            return

        source_path = record.get("source_path", "")
        descriptor_path = f"{source_path}/IXPlugin.json" if source_path else ""
        source_url = record["source_url"]
        self._run_background(
            lambda: self.installer.get_available_versions(source_url, descriptor_path),
            lambda releases: self._on_versions_fetched(uuid, releases),
        )

    def _on_versions_fetched(self, uuid: str, releases: List[ReleaseInfo]) -> None:
        """版本列表获取完成，弹出选择对话框"""
        if not releases:
            Message.info(self, "未获取到该仓库的 Release 版本")
            return
        record = self.pm.registry.get(uuid) or {}
        current = record.get("version", "")
        dialog = VersionSelectDialog(record.get("name", ""), current, releases, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.selected is None:
            return
        self._confirm_and_install_release(uuid, record, dialog.selected)

    def _confirm_and_install_release(self, uuid: str, record: dict,
                                     release: ReleaseInfo) -> None:
        """确认后安装选定的 Release 版本"""
        current = record.get("version", "")
        relation = _version_relation(current, release.version)
        text = (f"将{relation}插件「{record.get('name', '')}」\n"
                f"当前版本: {current or '未知'}\n目标版本: {release.version or release.tag}")
        if relation == "降级":
            text += "\n\n警告：降级可能导致数据不兼容或配置丢失！"
        if not _confirm(self, "确认安装", text):
            return

        parsed = self.installer.parse_github_url(record["source_url"])
        if not parsed:
            Message.warning(self, "来源仓库 URL 无效")
            return
        owner, repo = parsed
        target_dir = (self.pm.official_plugin_dir if record.get("scope") == "official"
                      else self.pm.thirdparty_plugin_dir)
        source_path = record.get("source_path", "")
        selected = [source_path] if source_path else None
        self._run_background(
            lambda: self.installer.install_release(owner, repo, release.tag, target_dir, selected),
            self._on_install_results,
        )

    def _on_install_results(self, results: List[InstallResult]) -> None:
        """安装/升级/降级完成，展示结果并刷新"""
        success = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        details = "\n".join(f"  - {r.plugin_name or r.plugin_id}: {r.message}" for r in results)
        if failed:
            _notice(self, "安装结果", f"部分失败：\n{details}")
        else:
            _notice(self, "安装结果", f"全部成功：\n{details}")
        if success:
            self._refresh_after_change()

    # ==================== 卸载 ====================

    def _on_uninstall(self) -> None:
        """卸载选中插件"""
        uuid = self._selected_plugin_id()
        if uuid is None:
            Message.info(self, "请先选择插件")
            return
        record = self.pm.registry.get(uuid) or {}
        name = record.get("name", uuid)
        scope = record.get("scope", "")

        text = f"确定卸载插件「{name}」？"
        if scope == "official":
            text += "\n\n该插件属于官方插件，卸载后需重新安装才能恢复。"
        # UIKit Dialog + 自定义内容（替代 QMessageBox + setCheckBox）
        dialog = Dialog(self, title="确认卸载")
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel(text))
        checkbox = CheckBox("同时删除插件数据（不可恢复）")
        lay.addWidget(checkbox)
        dialog.set_content(content)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        result = self.pm.uninstall_plugin(uuid, remove_data=checkbox.isChecked())
        if not result["success"]:
            _notice(self, "卸载失败", result["message"])
            return
        message = result["message"]
        if result["warnings"]:
            message += "\n\n警告：\n" + "\n".join(result["warnings"])
        _notice(self, "卸载完成", message)
        self._refresh_after_change()

    # ==================== 分组与排序保存 ====================

    def _on_groups_save(self) -> None:
        """保存两个 scope 的分组与面板统一顺序"""
        for scope, _title in self.SCOPES:
            editor = self._group_editors[scope]
            if not self.pm.save_groups(scope, editor.groups, editor.collect_panel_order()):
                _notice(self, "保存失败", "无法保存分组配置，请检查权限和磁盘空间。")
                return
        _logger.info(get_name(), "插件分组与排序已保存")
        self.plugins_changed.emit()
        Message.success(self, "分组与排序已保存")

    def _on_groups_reset(self) -> None:
        """放弃工作副本，重新加载分组配置"""
        for editor in self._group_editors.values():
            editor.reload()

    # ==================== 通用 ====================

    def _on_refresh(self) -> None:
        """手动刷新：重新加载插件并刷新列表"""
        self._refresh_after_change()

    def _refresh_after_change(self) -> None:
        """插件集合变更后的统一刷新"""
        self.pm.reload_plugins()
        self.reload_plugin_lists()
        for editor in self._group_editors.values():
            editor.reload()
        self.plugins_changed.emit()

    def _run_background(self, fn: Callable, on_success: Callable) -> None:
        """在后台线程执行耗时操作

        Args:
            fn: 无参数任务函数，返回值传给 on_success
            on_success: 成功回调（UI 线程执行）
        """
        if self._worker is not None and self._worker.isRunning():
            Message.info(self, "正在执行其他操作，请稍候")
            return
        self.setEnabled(False)
        self._worker = _Worker(fn, self)
        self._worker.succeeded.connect(on_success)
        self._worker.failed.connect(self._on_background_error)
        self._worker.finished.connect(lambda: self.setEnabled(True))
        self._worker.start()

    def _on_background_error(self, error: str) -> None:
        """后台任务异常"""
        _logger.error(get_name(), f"插件管理后台操作失败: {error}")
        _notice(self, "操作失败", error)
