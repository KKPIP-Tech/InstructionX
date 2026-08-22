"""界面语言选择对话框

列出框架全部可用语言（``LanguageManager.available_languages()``），
每行显示「语言自称 (语言代码)」；确定后经
``LanguageManager.set_language()`` 实时切换（触发 ``language_changed``
信号，各界面重取词），无需重启；取消不改动当前语言。

用法::

    dialog = LanguageDialog(main_window)
    dialog.exec()
"""

from typing import Optional

# ===================================================================
# PySide 相关
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

# ===================================================================
# 本地
from core.i18n import get_language_manager, tr
from InstructionX_UIKit import set_property

# 对话框文案均经 i18n 子系统取词（分组 dialog_language / common），
# 在使用处调用 tr()，不做模块级固化，保证语言切换后新建实例即为新语言

# ===================================================================
# 布局常量
DIALOG_MIN_WIDTH = 360
CONTENT_MARGIN = 24
CONTENT_SPACING = 16
BUTTON_SPACING = 12


class LanguageDialog(QDialog):
    """界面语言选择对话框：列表展示可用语言，确定后实时切换。

    模态（WindowModal，父窗口为主窗口）；当前语言默认选中。
    样式令牌取自 UIKit 全局主题（按钮 variant 由全局 QSS 驱动，
    随应用主题自动切换，无需手动跟随）。
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化对话框。

        Args:
            parent: 父窗口（通常为主窗口）
        """
        super().__init__(parent)
        self._language_manager = get_language_manager()
        self.setWindowTitle(tr("dialog_language", "title"))
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumWidth(DIALOG_MIN_WIDTH)
        self._init_ui()

    def _init_ui(self) -> None:
        """构建语言列表、说明文字与确定/取消按钮布局。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            CONTENT_MARGIN, CONTENT_MARGIN, CONTENT_MARGIN, CONTENT_MARGIN
        )
        layout.setSpacing(CONTENT_SPACING)

        # 语言列表（当前语言默认选中）
        self._language_list = QListWidget(self)
        self._populate_languages()
        layout.addWidget(self._language_list)

        # 说明文字
        note_label = QLabel(tr("dialog_language", "note"))
        note_label.setWordWrap(True)
        set_property(note_label, "role", "secondary")
        layout.addWidget(note_label)

        # 底部按钮：确定 / 取消
        button_layout = QHBoxLayout()
        button_layout.setSpacing(BUTTON_SPACING)
        button_layout.addStretch()

        ok_button = QPushButton(tr("common", "ok"))
        set_property(ok_button, "variant", "primary")
        ok_button.setDefault(True)
        ok_button.clicked.connect(self._on_ok_clicked)
        button_layout.addWidget(ok_button)

        cancel_button = QPushButton(tr("common", "cancel"))
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        layout.addLayout(button_layout)

    def _populate_languages(self) -> None:
        """填充语言列表：「显示名 (代码)」，当前语言默认选中。"""
        current_code = self._language_manager.current_language()
        for code in self._language_manager.available_languages():
            display_name = self._language_manager.language_display_name(code)
            item = QListWidgetItem(f"{display_name} ({code})")
            # 语言代码存入 UserRole，确定时据此切换（不解析显示文本）
            item.setData(Qt.ItemDataRole.UserRole, code)
            self._language_list.addItem(item)
            if code == current_code:
                self._language_list.setCurrentItem(item)

    def _on_ok_clicked(self) -> None:
        """「确定」按钮：选中语言与当前不同时实时切换，随后关闭对话框。"""
        item = self._language_list.currentItem()
        if item is not None:
            code = item.data(Qt.ItemDataRole.UserRole)
            if code and code != self._language_manager.current_language():
                self._language_manager.set_language(code)
        self.accept()
