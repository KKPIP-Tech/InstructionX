"""字体管理对话框

框架字体的管理入口：左栏展示已安装字体（框架管理）与系统字体两个分组，
右栏提供实时预览（示例文本可编辑、字号可调），底部提供安装/卸载操作。
卸载仅对已安装分组可用；预览经 FontManager.get_font 构造，所选家族不可用时
自动回退系统字体并显示实际解析结果。

样式约定：颜色一律实时取 UIKit 令牌 T()，按钮/输入框使用 UIKit 组件
（Button/LineEdit/Message），仅列表与预览卡片等定制结构保留局部 QSS。
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QSpinBox, QVBoxLayout, QWidget,
)

from InstructionX_UIKit import T, set_property
from InstructionX_UIKit.components import Button, LineEdit, Message

from core.font import FontInstallError, FontManager, get_font_manager
from utils.logging_tools import LoggerManager, get_name

from ui.dialog.llm_settings import feedback

# 模块级日志器（LoggerManager 为单例）
_logger = LoggerManager()

# 预览区默认示例文本与字号范围
_DEFAULT_SAMPLE_TEXT = "InstructionX 字体预览 Font Preview 0123 ABCabc"
_PREVIEW_MIN_SIZE = 8
_PREVIEW_MAX_SIZE = 72
_PREVIEW_DEFAULT_SIZE = 24

# 列表分组标题（不可选择的分组行）
_GROUP_INSTALLED = "已安装字体"
_GROUP_SYSTEM = "系统字体"

# 安装文件对话框的格式过滤
_FONT_FILE_FILTER = "字体文件 (*.ttf *.otf *.ttc)"


class FontManagerDialog(QDialog):
    """字体管理对话框

    职责：字体安装/卸载、已安装与系统字体浏览、实时效果预览与回退提示。

    典型用法：由主窗口「编辑 → 字体管理...」菜单创建并 exec() 显示。
    """

    def __init__(self, parent=None, font_manager: FontManager = None):
        super().__init__(parent)
        self.setWindowTitle("字体管理")
        self.setMinimumSize(860, 560)
        self.resize(920, 620)
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Dialog)

        self._font_manager = font_manager or get_font_manager()
        # 当前选中项：(家族名, 是否已安装分组)；无选中时为 None
        self._selected: tuple = None

        self._init_ui()
        self._reload_fonts()

    # ------------------------------------------------------------------ UI
    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self._build_header())

        content = QWidget()
        cl = QHBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self._build_left_panel())
        cl.addWidget(self._build_right_panel(), 1)
        main_layout.addWidget(content)

        main_layout.addWidget(self._build_bottom_bar())

    def _build_header(self) -> QFrame:
        """页头：标题 + 底部分隔线"""
        header = QFrame()
        header.setFixedHeight(52)
        header.setObjectName("fontDialogHeader")
        header.setStyleSheet(
            f"#fontDialogHeader {{ border-bottom: 1px solid {T('color.border')}; }}")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 0, 16, 0)

        title = QLabel("字体管理")
        title_font = title.font()
        title_font.setPixelSize(T("font.title.sm"))
        title_font.setBold(True)
        title.setFont(title_font)
        hl.addWidget(title)
        hl.addStretch()
        return header

    def _build_left_panel(self) -> QFrame:
        """左栏：搜索框 + 字体列表（已安装 / 系统 两个分组）"""
        left_panel = QFrame()
        left_panel.setFixedWidth(280)
        left_panel.setObjectName("fontListPanel")
        left_panel.setStyleSheet(
            f"#fontListPanel {{ border-right: 1px solid {T('color.border')}; }}")
        ll = QVBoxLayout(left_panel)
        ll.setContentsMargins(12, 12, 12, 12)
        ll.setSpacing(10)

        self._search_input = LineEdit(placeholder="搜索字体...", clearable=True)
        self._search_input.textChanged.connect(self._on_search)
        ll.addWidget(self._search_input)

        self._list_widget = QListWidget()
        self._list_widget.setObjectName("fontList")
        self._list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list_widget.currentItemChanged.connect(self._on_selection_changed)
        ll.addWidget(self._list_widget, 1)
        return left_panel

    def _build_right_panel(self) -> QWidget:
        """右栏：示例文本编辑 + 字号调节 + 预览区 + 解析结果提示"""
        right_panel = QWidget()
        rl = QVBoxLayout(right_panel)
        rl.setContentsMargins(20, 16, 20, 16)
        rl.setSpacing(12)

        self._sample_input = LineEdit(placeholder="输入预览文本...")
        self._sample_input.setText(_DEFAULT_SAMPLE_TEXT)
        self._sample_input.textChanged.connect(self._update_preview)
        rl.addWidget(self._sample_input)

        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("字号"))
        self._size_spin = QSpinBox()
        self._size_spin.setRange(_PREVIEW_MIN_SIZE, _PREVIEW_MAX_SIZE)
        self._size_spin.setValue(_PREVIEW_DEFAULT_SIZE)
        self._size_spin.valueChanged.connect(self._update_preview)
        size_row.addWidget(self._size_spin)
        size_row.addStretch()
        rl.addLayout(size_row)

        # 预览卡片：定制结构，颜色取令牌
        self._preview_label = QLabel("请选择左侧字体进行预览")
        self._preview_label.setAlignment(Qt.AlignCenter)
        self._preview_label.setWordWrap(True)
        self._preview_label.setStyleSheet(f"""
            QLabel {{
                color: {T('color.text.primary')};
                background-color: {T('color.bg.subtle')};
                border: 1px solid {T('color.border')};
                border-radius: {T('radius.lg')}px;
                padding: 24px;
            }}
        """)
        rl.addWidget(self._preview_label, 1)

        self._resolve_label = QLabel("")
        set_property(self._resolve_label, "role", "secondary")
        rl.addWidget(self._resolve_label)
        return right_panel

    def _build_bottom_bar(self) -> QFrame:
        """底部按钮栏：安装字体... / 卸载 / 关闭（主按钮）"""
        bottom_bar = QFrame()
        bottom_bar.setFixedHeight(52)
        bottom_bar.setObjectName("fontDialogBottomBar")
        bottom_bar.setStyleSheet(
            f"#fontDialogBottomBar {{ border-top: 1px solid {T('color.border')}; }}")
        bl = QHBoxLayout(bottom_bar)
        bl.setContentsMargins(20, 0, 20, 0)
        bl.setSpacing(8)

        install_btn = Button("安装字体...", variant="default")
        install_btn.setCursor(Qt.PointingHandCursor)
        install_btn.clicked.connect(self._on_install)
        bl.addWidget(install_btn)

        self._uninstall_btn = Button("卸载", variant="default")
        self._uninstall_btn.setCursor(Qt.PointingHandCursor)
        self._uninstall_btn.setEnabled(False)
        self._uninstall_btn.clicked.connect(self._on_uninstall)
        bl.addWidget(self._uninstall_btn)

        bl.addStretch()
        close_btn = Button("关闭", variant="primary")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        bl.addWidget(close_btn, 0, Qt.AlignRight)
        return bottom_bar

    # ------------------------------------------------------------------ 数据
    def _reload_fonts(self):
        """重建字体列表（已安装分组在前，系统分组在后）"""
        self._list_widget.clear()
        self._add_group_header(_GROUP_INSTALLED)

        installed = self._font_manager.list_fonts()
        for record in installed:
            self._add_font_item(record.family, record.font_id, installed=True)
        if not installed:
            self._add_hint_item("（尚未安装字体）")

        self._add_group_header(_GROUP_SYSTEM)
        for family in sorted(QFontDatabase.families()):
            self._add_font_item(family, "", installed=False)

    def _add_group_header(self, text: str):
        """添加不可选择的分组标题行"""
        item = QListWidgetItem(text)
        item.setFlags(Qt.NoItemFlags)
        header_font = item.font()
        header_font.setBold(True)
        item.setFont(header_font)
        self._list_widget.addItem(item)

    def _add_font_item(self, family: str, font_id: str, installed: bool):
        """添加一个可选中的字体行（UserRole 存家族名与分组标记）"""
        item = QListWidgetItem(family)
        item.setData(Qt.UserRole, (family, installed, font_id))
        self._list_widget.addItem(item)

    def _add_hint_item(self, text: str):
        """添加不可选择的灰色提示行（如空分组占位）"""
        item = QListWidgetItem(text)
        item.setFlags(Qt.NoItemFlags)
        item.setForeground(QColor(T("color.text.tertiary")))
        self._list_widget.addItem(item)

    # ------------------------------------------------------------------ 交互
    def _on_search(self, text: str):
        """按家族名过滤列表（分组标题恒显示）"""
        keyword = text.strip().lower()
        for row in range(self._list_widget.count()):
            item = self._list_widget.item(row)
            payload = item.data(Qt.UserRole)
            if payload is None:
                continue  # 分组标题与提示行不过滤
            item.setHidden(bool(keyword) and keyword not in payload[0].lower())

    def _on_selection_changed(self, current: QListWidgetItem, _previous):
        """选中变化：更新预览与卸载按钮状态"""
        payload = current.data(Qt.UserRole) if current else None
        self._selected = payload
        self._uninstall_btn.setEnabled(bool(payload and payload[1]))
        self._update_preview()

    def _update_preview(self):
        """按当前选中字体刷新预览；不可用时显示回退结果"""
        if not self._selected:
            self._preview_label.setText("请选择左侧字体进行预览")
            self._resolve_label.setText("")
            return

        family = self._selected[0]
        sample = self._sample_input.text() or _DEFAULT_SAMPLE_TEXT
        font = self._font_manager.get_font(
            family, point_size=self._size_spin.value())
        self._preview_label.setFont(font)
        self._preview_label.setText(sample)

        resolved = font.family()
        if resolved == family:
            self._resolve_label.setText(f"当前字体：{resolved}")
        else:
            self._resolve_label.setText(f"字体 {family} 不可用，已回退到系统字体：{resolved}")

    def _on_install(self):
        """选择字体文件并安装；失败弹窗并记日志"""
        paths, _selected_filter = QFileDialog.getOpenFileNames(
            self, "选择字体文件", "", _FONT_FILE_FILTER)
        if not paths:
            return

        installed_count = 0
        for path in paths:
            try:
                self._font_manager.install_font(path, source="user")
                installed_count += 1
            except FontInstallError as e:
                _logger.error(get_name(), f"字体安装失败: {path}: {e}")
                Message.warning(self, f"安装失败：{Path(path).name}\n{e}")

        if installed_count:
            feedback.success(self, f"成功安装 {installed_count} 个字体")
            self._reload_fonts()

    def _on_uninstall(self):
        """卸载当前选中的已安装字体（确认后执行）"""
        if not self._selected or not self._selected[1]:
            return
        family, _installed, font_id = self._selected
        confirmed = feedback.confirm(
            self, "卸载字体",
            f"确定卸载字体「{family}」吗？\n卸载后使用该字体的界面将回退到系统字体。")
        if not confirmed:
            return

        if self._font_manager.uninstall_font(font_id):
            feedback.success(self, f"字体「{family}」已卸载")
        else:
            Message.warning(self, f"卸载失败：未找到字体 {family}")
        self._reload_fonts()
