"""
许可对话框
展示项目中各类许可证信息，支持字体、第三方依赖等多种分类
"""
import json
import os
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QScrollArea, QVBoxLayout, QWidget, QMessageBox,
)

from utils.logging_tools import LoggerManager, get_name
from utils.style_qss import get_style_qss

# 模块级日志器（LoggerManager 为单例）
_logger = LoggerManager()


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
    "阿里妈妈专有协议": ("#FFF8E1", "#F57F17"),
    "阿里巴巴专有协议": ("#FFF3E0", "#E65100"),
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


class _LicenseItemWidget(QWidget):
    """许可证列表项控件

    职责：在许可对话框左侧列表中展示单个许可证条目（名称、英文名、
    许可证类型徽章、版本号），并支持选中态样式切换。

    典型用法：由 LicenseDialog._populate_list 创建，作为 QListWidgetItem
    的 itemWidget 使用；通过 set_selected 同步列表选中状态。
    """

    def __init__(self, name: str, display_name: str, license_type: str,
                 category: str, version: str = "", colors: dict = None, parent=None):
        super().__init__(parent)
        self._name = name
        self._display_name = display_name
        self._license_type = license_type
        self._category = category
        self._version = version
        self._colors = colors or {}
        self._is_selected = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)

        # 主题色
        tp = self._colors.get('textPrimary', '#212121')
        ts = self._colors.get('textSecondary', '#757575')

        # 名称（加粗）
        name_font = QFont()
        name_font.setPointSize(10)
        name_font.setBold(True)

        title = self._display_name if self._display_name else self._name
        self._name_label = QLabel(title)
        self._name_label.setFont(name_font)
        self._name_label.setStyleSheet(f"color: {tp}; background: transparent;")
        layout.addWidget(self._name_label)

        # 英文名（如果有）
        self._en_label = None
        if self._display_name and self._display_name != self._name:
            self._en_label = QLabel(self._name)
            self._en_label.setStyleSheet(f"color: {ts}; font-size: 8pt; background: transparent;")
            layout.addWidget(self._en_label)

        # 底部行：许可证标签 + 版本
        row = QHBoxLayout()
        row.setSpacing(4)
        row.setContentsMargins(0, 0, 0, 0)

        bg, fg = _get_license_colors(self._license_type)
        self._badge = QLabel(self._license_type)
        self._badge.setStyleSheet(
            f"QLabel {{ background-color: {bg}; color: {fg}; "
            f"border-radius: 4px; padding: 1px 6px; font-size: 7pt; "
            f"font-weight: 500; }}"
        )
        row.addWidget(self._badge)

        self._ver_label = None
        if self._version:
            self._ver_label = QLabel(f"v{self._version}")
            self._ver_label.setStyleSheet(f"color: {ts}; font-size: 8pt; background: transparent;")
            row.addWidget(self._ver_label)

        row.addStretch()
        layout.addLayout(row)

    def set_selected(self, selected: bool):
        """更新选中态文字颜色"""
        self._is_selected = selected
        if selected:
            self._name_label.setStyleSheet("color: #FFFFFF; background: transparent;")
            if self._en_label:
                self._en_label.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 8pt; background: transparent;")
            if self._ver_label:
                self._ver_label.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 8pt; background: transparent;")
            # Badge: 半透明背景 + 白色文字，更协调
            self._badge.setStyleSheet(
                "QLabel { background-color: rgba(255,255,255,0.25); color: #FFFFFF; "
                "border-radius: 4px; padding: 1px 6px; font-size: 7pt; "
                "font-weight: 500; }"
            )
        else:
            tp = self._colors.get('textPrimary', '#212121')
            ts = self._colors.get('textSecondary', '#757575')
            self._name_label.setStyleSheet(f"color: {tp}; background: transparent;")
            if self._en_label:
                self._en_label.setStyleSheet(f"color: {ts}; font-size: 8pt; background: transparent;")
            if self._ver_label:
                self._ver_label.setStyleSheet(f"color: {ts}; font-size: 8pt; background: transparent;")
            # Badge: 恢复原色
            bg, fg = _get_license_colors(self._license_type)
            self._badge.setStyleSheet(
                f"QLabel {{ background-color: {bg}; color: {fg}; "
                f"border-radius: 4px; padding: 1px 6px; font-size: 7pt; "
                f"font-weight: 500; }}"
            )

    def name(self) -> str:
        return self._name


class LicenseDialog(QDialog):
    """许可信息对话框

    职责：读取 licenses/manifest.json 中登记的字体与第三方依赖许可证信息，
    左侧列表展示条目、支持搜索过滤，右侧展示许可证全文，并提供
    「复制全文」「打开文件夹」操作。

    典型用法：由主窗口「帮助 → 许可信息」菜单创建并 exec() 显示。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("许可信息")
        self.setMinimumSize(900, 600)
        self.resize(950, 650)
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Dialog)

        self._colors = get_style_qss().colors()
        self._all_items: list = []
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

    def _init_ui(self):
        bg = self._colors.get("window", "#FFFFFF")
        border = self._colors.get("borderLight", "#E0E0E0")
        text_primary = self._colors.get("textPrimary", "#212121")
        text_secondary = self._colors.get("textSecondary", "#757575")
        accent = self._colors.get("accent", "#1976D2")
        self.setStyleSheet(f"QDialog {{ background-color: {bg}; }}")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Header ──────────────────────────────────────────
        self._header = QFrame()
        header = self._header
        header.setFixedHeight(52)
        header.setObjectName("headerBar")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 0, 16, 0)

        title = QLabel("许可信息  Licenses")
        f = QFont()
        f.setPointSize(12)
        f.setBold(True)
        title.setFont(f)
        title.setStyleSheet(f"color: {text_primary}; background: transparent; border: none;")
        hl.addWidget(title)
        hl.addStretch()

        header.setStyleSheet(f"#headerBar {{ border-bottom: 1px solid {border}; background: {bg}; }}")
        main_layout.addWidget(header)

        # ── Content ─────────────────────────────────────────
        self._content = QWidget()
        content = self._content
        cl = QHBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        # 左栏
        left_panel = QFrame()
        left_panel.setFixedWidth(320)
        left_panel.setObjectName("leftPanel")
        ll = QVBoxLayout(left_panel)
        ll.setContentsMargins(12, 12, 12, 12)
        ll.setSpacing(10)

        search = QLineEdit()
        search.setPlaceholderText("搜索名称...")
        search.setFixedHeight(34)
        search.textChanged.connect(self._on_search)
        search.setStyleSheet(
            f"QLineEdit {{ background: {self._colors.get('controlFill','#F5F5F5')}; "
            f"border: 1px solid {border}; border-radius: 6px; padding: 0 10px; "
            f"color: {text_primary}; font-size: 10pt; }}"
            f"QLineEdit:focus {{ border-color: {accent}; }}"
        )
        self._search_input = search
        ll.addWidget(search)

        list_w = QListWidget()
        list_w.setObjectName("licenseList")
        list_w.itemClicked.connect(self._on_item_clicked)
        list_w.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        list_w.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 列表样式：卡片效果、悬停、选中状态
        list_w.setStyleSheet(f"""
            QListWidget {{
                border: none;
                background: transparent;
                outline: none;
            }}
            QListWidget::item {{
                padding: 4px;
                margin: 4px 0px;
                border-radius: 8px;
                background: {self._colors.get('cardBackground', '#FFFFFF')};
                border: 1px solid {self._colors.get('borderLight', '#E0E0E0')};
            }}
            QListWidget::item:hover {{
                background: {self._colors.get('controlFillHover', '#F5F5F5')};
                border-color: {self._colors.get('border', '#BDBDBD')};
            }}
            QListWidget::item:selected {{
                background: {self._colors.get('accentLight', '#E3F2FD')};
                border-left: 4px solid {accent};
                border-top: 1px solid {accent};
                border-right: 1px solid {accent};
                border-bottom: 1px solid {accent};
            }}
        """)
        self._list_widget = list_w
        ll.addWidget(list_w, 1)

        # 空状态提示
        self._empty_state = QLabel("未找到匹配的许可证")
        self._empty_state.setAlignment(Qt.AlignCenter)
        self._empty_state.setStyleSheet(f"""
            QLabel {{
                color: {text_secondary};
                font-size: 11pt;
                padding: 40px 20px;
            }}
        """)
        self._empty_state.hide()
        ll.addWidget(self._empty_state)

        left_panel.setStyleSheet(f"#leftPanel {{ border-right: 1px solid {border}; }}")
        cl.addWidget(left_panel)

        # 右栏
        self._right_panel = QWidget()
        right_panel = self._right_panel
        cl.addWidget(right_panel, 1)
        
        # 右栏内容布局
        rl = QVBoxLayout(right_panel)
        rl.setContentsMargins(20, 16, 20, 12)
        rl.setSpacing(12)

        self._detail_header = QLabel()
        self._detail_header.setStyleSheet("border: none;")
        rl.addWidget(self._detail_header)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"QFrame {{ border: 1px solid {border}; }}")
        sep.setFixedHeight(1)
        rl.addWidget(sep)

        self._scroll = QScrollArea()
        s = self._scroll
        s.setObjectName("licenseScroll")
        s.setWidgetResizable(True)
        s.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        s.setFrameShape(QFrame.Shape.NoFrame)
        s.setStyleSheet(f"QScrollArea {{ border: none; background: transparent; }}")

        self._license_text_label = QLabel()
        self._license_text_label.setWordWrap(True)
        self._license_text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # 代码块样式：浅灰背景、圆角、内边距，使用样式表设置字体
        self._license_text_label.setStyleSheet(f"""
            QLabel {{
                color: {text_primary};
                background-color: {self._colors.get('codeBackground', '#F5F5F5')};
                padding: 16px;
                border-radius: 8px;
                border: 1px solid {self._colors.get('borderLight', '#E0E0E0')};
                font-family: "Courier New", monospace;
                font-size: 9pt;
            }}
        """)
        self._license_text_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        s.setWidget(self._license_text_label)
        rl.addWidget(s, 1)

        # 底部栏
        self._bottom_bar = QFrame()
        bb = self._bottom_bar
        bb.setFixedHeight(52)
        bb.setObjectName("bottomBar")
        bl = QHBoxLayout(bb)
        bl.setContentsMargins(20, 0, 20, 0)
        bl.addStretch()

        copy_btn = QPushButton("复制全文")
        copy_btn.setFixedHeight(34)
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.clicked.connect(self._on_copy)
        copy_btn.setStyleSheet(
            f"QPushButton {{ background: {self._colors.get('controlFill','#F0F0F0')}; "
            f"border: 1px solid {border}; border-radius: 6px; padding: 0 16px; "
            f"color: {text_primary}; font-size: 10pt; }}"
            f"QPushButton:hover {{ background: {self._colors.get('controlFillHover','#E0E0E0')}; }}"
        )
        self._copy_btn = copy_btn
        bl.addWidget(copy_btn, 0, Qt.AlignRight)

        folder_btn = QPushButton("打开文件夹")
        folder_btn.setFixedHeight(34)
        folder_btn.setCursor(Qt.PointingHandCursor)
        folder_btn.clicked.connect(self._on_open_folder)
        folder_btn.setStyleSheet(
            f"QPushButton {{ background: {self._colors.get('controlFill','#F0F0F0')}; "
            f"border: 1px solid {border}; border-radius: 6px; padding: 0 16px; "
            f"color: {text_primary}; font-size: 10pt; }}"
            f"QPushButton:hover {{ background: {self._colors.get('controlFillHover','#E0E0E0')}; }}"
        )
        bl.addWidget(folder_btn, 0, Qt.AlignRight)

        close_btn2 = QPushButton("关闭")
        close_btn2.setFixedHeight(34)
        close_btn2.setCursor(Qt.PointingHandCursor)
        close_btn2.clicked.connect(self.accept)
        close_btn2.setStyleSheet(
            f"QPushButton {{ background: {accent}; color: white; border: none; "
            f"border-radius: 6px; padding: 0 20px; font-size: 10pt; }}"
            f"QPushButton:hover {{ background: {self._colors.get('accentDark','#1565C0')}; }}"
        )
        bl.addWidget(close_btn2, 0, Qt.AlignRight)
        bb.setStyleSheet(f"#bottomBar {{ border-top: 1px solid {border}; }}")
        rl.addWidget(bb)

        main_layout.addWidget(content)

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

        fonts = data.get("fonts", [])
        deps = data.get("dependencies", [])

        for d in fonts:
            d["_category"] = "字体"
        for d in deps:
            d["_category"] = "依赖"

        self._all_items = fonts + deps
        self._all_items.sort(key=lambda x: x.get("name", ""))

        self._populate_list()

    def _populate_list(self):
        self._list_widget.clear()
        self._all_list_items: list[tuple] = []
        for item in self._all_items:
            cat = item.get("_category", "")
            name = item.get("name", "")
            display = item.get("display_name", "")
            lic = item.get("license_type", "Unknown")
            version = item.get("version", "")

            widget = _LicenseItemWidget(name, display, lic, cat, version, self._colors)
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
        tp = self._colors.get("textPrimary", "#212121")
        ts = self._colors.get("textSecondary", "#757575")
        accent = self._colors.get("accent", "#1976D2")

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
            meta_info.append(f'版本 v{version}')
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
                self._selected_license_text = "(无法读取许可文件)"
        else:
            self._selected_license_text = f"(许可文件未找到: {lic_rel})"

        self._license_text_label.setText(self._selected_license_text)

    def _on_copy(self):
        if self._selected_license_text:
            QApplication.clipboard().setText(self._selected_license_text)
            orig = self._copy_btn.text()
            self._copy_btn.setText("已复制！")
            QTimer.singleShot(1500, lambda: self._copy_btn.setText(orig))

    def _on_open_folder(self):
        folder = _get_manifest_dir().parent
        if folder.exists():
            os.startfile(folder)
        else:
            QMessageBox.information(self, "提示", f"目录不存在: {folder}")
