"""
开源组件许可对话框

读取 licenses/manifest.json 中登记的第三方开源组件许可证信息，
左侧列表展示条目、支持搜索过滤，右侧展示许可证全文，并提供
「复制全文」「打开文件夹」操作。

样式约定（UIKit 迁移后）：颜色一律实时取 UIKit 令牌 T()，输入框/按钮使用
UIKit 组件（LineEdit/Button），全局 QSS 承担常规控件外观；仅列表卡片、
徽章、分区边框等定制结构保留局部 QSS（颜色同样取自令牌）。
对话框为模态短生命周期，主题色在打开时取一次（与旧行为一致）。
"""
import json
import os
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem,
    QScrollArea, QVBoxLayout, QWidget,
)

from InstructionX_UIKit import T, MONO_FAMILY, set_property
from InstructionX_UIKit.components import Button, LineEdit, Message

from core.i18n import tr
from utils.logging_tools import LoggerManager, get_name

# 模块级日志器（LoggerManager 为单例）
_logger = LoggerManager()

# i18n 文案分组名
_TR_GROUP = "dialog_license"


# 许可证类型徽章配色（浅色底 + 深字，亮/暗主题下均可读，属刻意的品牌色设计）
LICENSE_COLORS = {
    "OFL-1.1": ("#E8F5E9", "#2E7D32"),
    "MIT": ("#E8F5E9", "#2E7D32"),
    "Apache-2.0": ("#E3F2FD", "#1565C0"),
    "LGPL-3.0": ("#FFF3E0", "#E65100"),
    "GPL-3.0": ("#FFEBEE", "#C62828"),
    "BSD-3-Clause": ("#F3E5F5", "#6A1B9A"),
    "PSF-2.0": ("#E0F2F1", "#00695C"),
    "BSD-2-Clause": ("#FCE4EC", "#AD1457"),
    "MPL-2.0": ("#E8EAF6", "#283593"),
    "Unknown": ("#F5F5F5", "#616161"),
}


def _get_license_colors(license_type: str) -> tuple:
    if license_type in LICENSE_COLORS:
        return LICENSE_COLORS[license_type]
    for key in LICENSE_COLORS:
        if license_type.startswith(key):
            return LICENSE_COLORS[key]
    return LICENSE_COLORS["Unknown"]


def _get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _get_manifest_dir() -> Path:
    return _get_project_root() / "licenses"


def _badge_qss(bg: str, fg: str) -> str:
    """许可证徽章局部 QSS（圆角胶囊）"""
    return (
        f"QLabel {{ background-color: {bg}; color: {fg}; "
        f"border-radius: {T('radius.sm')}px; padding: 1px 6px; "
        f"font-size: {T('font.xs')}px; font-weight: 500; }}"
    )


class _LicenseItemWidget(QWidget):
    """许可证列表项控件

    职责：在许可对话框左侧列表中展示单个许可证条目（名称、英文名、
    许可证类型徽章、版本号），并支持选中态样式切换。

    典型用法：由 LicenseDialog._populate_list 创建，作为 QListWidgetItem
    的 itemWidget 使用；通过 set_selected 同步列表选中状态。
    """

    def __init__(self, name: str, display_name: str, license_type: str,
                 category: str, version: str = "", parent=None):
        super().__init__(parent)
        self._name = name
        self._display_name = display_name
        self._license_type = license_type
        self._category = category
        self._version = version
        self._is_selected = False
        self._setup_ui()

    def _meta_label(self, text: str) -> QLabel:
        """次级信息标签（英文名/版本号）：字阶 xs + role=secondary"""
        label = QLabel(text)
        font = QFont()
        font.setPixelSize(T("font.xs"))
        label.setFont(font)
        set_property(label, "role", "secondary")
        return label

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)

        # 名称（加粗）
        title = self._display_name if self._display_name else self._name
        self._name_label = QLabel(title)
        name_font = QFont()
        name_font.setPixelSize(T("font.md"))
        name_font.setBold(True)
        self._name_label.setFont(name_font)
        layout.addWidget(self._name_label)

        # 英文名（如果有）
        self._en_label = None
        if self._display_name and self._display_name != self._name:
            self._en_label = self._meta_label(self._name)
            layout.addWidget(self._en_label)

        # 底部行：许可证标签 + 版本
        row = QHBoxLayout()
        row.setSpacing(4)
        row.setContentsMargins(0, 0, 0, 0)

        bg, fg = _get_license_colors(self._license_type)
        self._badge = QLabel(self._license_type)
        self._badge.setStyleSheet(_badge_qss(bg, fg))
        row.addWidget(self._badge)

        self._ver_label = None
        if self._version:
            self._ver_label = self._meta_label(f"v{self._version}")
            row.addWidget(self._ver_label)

        row.addStretch()
        layout.addLayout(row)

    def set_selected(self, selected: bool):
        """更新选中态文字颜色（选中底为 primary.subtle，文字强调主色）"""
        self._is_selected = selected
        if selected:
            self._name_label.setStyleSheet(
                f"color: {T('color.primary')}; background: transparent;")
        else:
            self._name_label.setStyleSheet("background: transparent;")


class LicenseDialog(QDialog):
    """开源组件许可对话框

    职责：读取 licenses/manifest.json 中登记的第三方开源组件许可证信息，
    左侧列表展示条目、支持搜索过滤，右侧展示许可证全文，并提供
    「复制全文」「打开文件夹」操作。

    典型用法：由主窗口「帮助 → 开源组件许可」菜单创建并 exec() 显示。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr(_TR_GROUP, "title"))
        self.setMinimumSize(900, 600)
        self.resize(950, 650)
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Dialog)

        self._all_items: list = []
        self._all_list_items: list = []
        self._current_search: str = ""
        self._selected_license_text: str = ""

        # 容器引用，防止 GC
        self._header: QFrame = None
        self._content: QWidget = None
        self._right_panel: QWidget = None
        self._bottom_bar: QFrame = None
        self._scroll: QScrollArea = None

        self._init_ui()
        QTimer.singleShot(0, self._load_licenses)

    # ------------------------------------------------------------------ UI
    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self._build_header())

        self._content = QWidget()
        cl = QHBoxLayout(self._content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self._build_left_panel())
        cl.addWidget(self._build_right_panel(), 1)
        main_layout.addWidget(self._content)

    def _build_header(self) -> QFrame:
        """页头：标题 + 底部分隔线"""
        self._header = QFrame()
        self._header.setFixedHeight(52)
        self._header.setObjectName("headerBar")
        self._header.setStyleSheet(
            f"#headerBar {{ border-bottom: 1px solid {T('color.border')}; }}")
        hl = QHBoxLayout(self._header)
        hl.setContentsMargins(20, 0, 16, 0)

        title = QLabel(tr(_TR_GROUP, "title"))
        font = QFont()
        font.setPixelSize(T("font.title.sm"))
        font.setBold(True)
        title.setFont(font)
        hl.addWidget(title)
        hl.addStretch()
        return self._header

    def _build_left_panel(self) -> QFrame:
        """左栏：搜索框 + 许可证卡片列表 + 空状态"""
        left_panel = QFrame()
        left_panel.setFixedWidth(320)
        left_panel.setObjectName("leftPanel")
        left_panel.setStyleSheet(
            f"#leftPanel {{ border-right: 1px solid {T('color.border')}; }}")
        ll = QVBoxLayout(left_panel)
        ll.setContentsMargins(12, 12, 12, 12)
        ll.setSpacing(10)

        self._search_input = LineEdit(
            placeholder=tr(_TR_GROUP, "search.placeholder"), clearable=True)
        self._search_input.textChanged.connect(self._on_search)
        ll.addWidget(self._search_input)

        list_w = QListWidget()
        list_w.setObjectName("licenseList")
        list_w.itemClicked.connect(self._on_item_clicked)
        list_w.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        list_w.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 卡片式列表项：定制结构无对应 UIKit 组件，局部 QSS 颜色取令牌
        list_w.setStyleSheet(f"""
            QListWidget {{
                border: none;
                background: transparent;
                outline: none;
            }}
            QListWidget::item {{
                padding: 4px;
                margin: 4px 0px;
                border-radius: {T('radius.lg')}px;
                background: {T('color.bg.elevated')};
                border: 1px solid {T('color.border')};
            }}
            QListWidget::item:hover {{
                background: {T('color.bg.muted')};
                border-color: {T('color.border.strong')};
            }}
            QListWidget::item:selected {{
                background: {T('color.primary.subtle')};
                border: 1px solid {T('color.primary')};
            }}
        """)
        self._list_widget = list_w
        ll.addWidget(list_w, 1)

        self._empty_state = QLabel(tr(_TR_GROUP, "list.empty"))
        self._empty_state.setAlignment(Qt.AlignCenter)
        set_property(self._empty_state, "role", "secondary")
        self._empty_state.hide()
        ll.addWidget(self._empty_state)
        return left_panel

    def _build_right_panel(self) -> QWidget:
        """右栏：详情头部 + 许可全文滚动区 + 底部按钮栏"""
        self._right_panel = QWidget()
        rl = QVBoxLayout(self._right_panel)
        rl.setContentsMargins(20, 16, 20, 12)
        rl.setSpacing(12)

        self._detail_header = QLabel()
        self._detail_header.setStyleSheet("border: none;")
        rl.addWidget(self._detail_header)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        rl.addWidget(sep)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        # 许可全文：等宽字体 + 次级底卡片（定制结构，颜色取令牌）
        self._license_text_label = QLabel()
        self._license_text_label.setWordWrap(True)
        self._license_text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._license_text_label.setStyleSheet(f"""
            QLabel {{
                color: {T('color.text.primary')};
                background-color: {T('color.bg.subtle')};
                padding: 16px;
                border-radius: {T('radius.lg')}px;
                border: 1px solid {T('color.border')};
                font-family: {MONO_FAMILY};
                font-size: {T('font.sm')}px;
            }}
        """)
        self._license_text_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._scroll.setWidget(self._license_text_label)
        rl.addWidget(self._scroll, 1)

        rl.addWidget(self._build_bottom_bar())
        return self._right_panel

    def _build_bottom_bar(self) -> QFrame:
        """底部按钮栏：复制全文 / 打开文件夹 / 关闭（主按钮）"""
        self._bottom_bar = QFrame()
        self._bottom_bar.setFixedHeight(52)
        self._bottom_bar.setObjectName("bottomBar")
        self._bottom_bar.setStyleSheet(
            f"#bottomBar {{ border-top: 1px solid {T('color.border')}; }}")
        bl = QHBoxLayout(self._bottom_bar)
        bl.setContentsMargins(20, 0, 20, 0)
        bl.setSpacing(8)
        bl.addStretch()

        self._copy_btn = Button(tr(_TR_GROUP, "button.copy_all"), variant="default")
        self._copy_btn.setCursor(Qt.PointingHandCursor)
        self._copy_btn.clicked.connect(self._on_copy)
        bl.addWidget(self._copy_btn, 0, Qt.AlignRight)

        folder_btn = Button(tr(_TR_GROUP, "button.open_folder"), variant="default")
        folder_btn.setCursor(Qt.PointingHandCursor)
        folder_btn.clicked.connect(self._on_open_folder)
        bl.addWidget(folder_btn, 0, Qt.AlignRight)

        close_btn = Button(tr("common", "close"), variant="primary")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        bl.addWidget(close_btn, 0, Qt.AlignRight)
        return self._bottom_bar

    # ------------------------------------------------------------------ 数据
    def _load_licenses(self):
        manifest_path = _get_manifest_dir() / "manifest.json"
        if not manifest_path.exists():
            return

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            # manifest 损坏或读取失败时保持空列表，不阻断对话框打开
            _logger.warning(get_name(), f"许可证 manifest 读取失败，许可列表为空: {e}")
            return

        deps = data.get("dependencies", [])

        for d in deps:
            d["_category"] = tr(_TR_GROUP, "category.dependency")

        self._all_items = deps
        self._all_items.sort(key=lambda x: x.get("name", ""))

        self._populate_list()

    def _populate_list(self):
        self._list_widget.clear()
        self._all_list_items = []
        for item in self._all_items:
            cat = item.get("_category", "")
            name = item.get("name", "")
            display = item.get("display_name", "")
            lic = item.get("license_type", "Unknown")
            version = item.get("version", "")

            widget = _LicenseItemWidget(name, display, lic, cat, version)
            # 强制 layout 以获取准确 sizeHint，再加 10px 余量应对 item padding
            widget.adjustSize()
            hint = widget.sizeHint()
            lw_item = QListWidgetItem()
            lw_item.setSizeHint(QSize(hint.width(), hint.height() + 10))
            lw_item.setData(Qt.UserRole, item)
            self._list_widget.addItem(lw_item)
            self._list_widget.setItemWidget(lw_item, widget)
            self._all_list_items.append((lw_item, widget, item))

        if self._all_items:
            self._list_widget.setCurrentRow(0)
            self._show_detail(self._all_items[0])
            self._update_selection_state()

    # ------------------------------------------------------------------ 交互
    def _on_search(self, text: str):
        self._current_search = text.strip().lower()
        visible_count = 0
        for lw_item, widget, item in self._all_list_items:
            name = item.get("name", "")
            display = item.get("display_name", "")
            match = (
                self._current_search == "" or
                self._current_search in name.lower() or
                (display and self._current_search in display.lower())
            )
            lw_item.setHidden(not match)
            if match:
                visible_count += 1

        # 控制空状态显示
        if visible_count == 0 and self._current_search != "":
            self._list_widget.hide()
            self._empty_state.show()
        else:
            self._list_widget.show()
            self._empty_state.hide()

    def _on_item_clicked(self, lw_item: QListWidgetItem):
        item = lw_item.data(Qt.UserRole)
        if item:
            self._show_detail(item)
        self._update_selection_state()

    def _update_selection_state(self):
        """同步所有列表项的选中态样式"""
        for lw_item, widget, _ in getattr(self, '_all_list_items', []):
            if isinstance(widget, _LicenseItemWidget):
                widget.set_selected(lw_item.isSelected())

    def _show_detail(self, item: dict):
        name = item.get("name", "")
        display = item.get("display_name", "")
        version = item.get("version", "")
        lic = item.get("license_type", "Unknown")
        url = item.get("url", "")
        copyright_text = item.get("copyright", "")
        category = item.get("_category", "")

        title = display if display else name
        bg, fg = _get_license_colors(lic)
        tp = T("color.text.primary")
        ts = T("color.text.secondary")
        accent = T("color.primary")

        # 优化后的详情页头部布局
        header_html = f'<div style="line-height: 1.5;">'

        # 第一行：主标题 + 徽章
        header_html += f'<div style="margin-bottom: 6px;">'
        header_html += f'<span style="font-size: 16pt; font-weight: bold; color: {tp};">{title}</span>'
        header_html += f'<span style="background-color: {bg}; color: {fg}; border-radius: 12px; padding: 3px 10px; font-size: 9pt; font-weight: 500; margin-left: 24px; vertical-align: middle;">{lic}</span>'
        header_html += '</div>'

        # 第二行：英文名称（如果有）
        if display and display != name:
            header_html += f'<div style="font-size: 10pt; color: {ts}; margin-bottom: 4px;">{name}</div>'

        # 第三行：版本 + 分类
        meta_info = []
        if version:
            meta_info.append(tr(_TR_GROUP, "detail.version", version=version))
        if category:
            meta_info.append(f'{category}')
        if meta_info:
            header_html += f'<div style="font-size: 9pt; color: {ts}; margin-bottom: 8px;">{" &nbsp;|&nbsp; ".join(meta_info)}</div>'

        # 版权信息
        if copyright_text:
            header_html += f'<div style="font-size: 9pt; color: {ts}; margin-bottom: 4px; font-style: italic;">© {copyright_text}</div>'

        # 链接（带悬停效果）
        if url:
            header_html += f'<div style="margin-top: 4px;">'
            header_html += f'<a href="{url}" style="font-size: 9pt; color: {accent}; text-decoration: none; padding: 2px 0;">{url}</a>'
            header_html += '</div>'

        header_html += '</div>'

        self._detail_header.setText(header_html)
        self._detail_header.setOpenExternalLinks(True)

        # 加载许可文件
        lic_rel = item.get("license_file", "")
        lic_path = _get_manifest_dir().parent / lic_rel
        self._selected_license_text = ""

        if lic_path.exists():
            try:
                with open(lic_path, "r", encoding="utf-8") as f:
                    self._selected_license_text = f.read()
            except IOError:
                self._selected_license_text = tr(_TR_GROUP, "detail.read_failed")
        else:
            self._selected_license_text = tr(
                _TR_GROUP, "detail.file_not_found", path=lic_rel)

        self._license_text_label.setText(self._selected_license_text)

    def _on_copy(self):
        if self._selected_license_text:
            QApplication.clipboard().setText(self._selected_license_text)
            orig = self._copy_btn.text()
            self._copy_btn.setText(tr(_TR_GROUP, "button.copied"))
            QTimer.singleShot(1500, lambda: self._copy_btn.setText(orig))

    def _on_open_folder(self):
        folder = _get_manifest_dir().parent
        if folder.exists():
            os.startfile(folder)
        else:
            Message.warning(self, tr(_TR_GROUP, "message.dir_not_exist", path=folder))
