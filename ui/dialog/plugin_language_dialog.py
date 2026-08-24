"""插件语言选择对话框

为单个插件设置语言覆盖（每插件语言自定义）：
- 第一项固定为「跟随框架（默认）」（清除覆盖），其后仅列出该插件
  ``text/`` 目录实际提供的语言（``LanguageManager.plugin_available_languages()``）；
- 当前生效项默认选中（按 ``plugin_language_override()`` 判断）；
- 确定后经 ``LanguageManager.set_plugin_language()`` 持久化覆盖并触发
  ``plugin_language_changed`` 信号；取消不改动现有覆盖。

用法::

    dialog = PluginLanguageDialog(plugin_id, plugin_name, parent)
    dialog.exec()
"""

from typing import Optional

# ===================================================================
# PySide 相关
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

# ===================================================================
# 本地
from core.i18n import get_language_manager, tr
from InstructionX_UIKit import set_property

# 本对话框的 i18n 分组名（键定义见 ui/text/zh.xml 的同名分组）
_I18N_GROUP = "dialog_plugin_management"

# ===================================================================
# 布局常量
DIALOG_MIN_WIDTH = 360
CONTENT_MARGIN = 24
CONTENT_SPACING = 16
BUTTON_SPACING = 12


class PluginLanguageDialog(QDialog):
    """插件语言选择对话框：设置/清除单个插件的语言覆盖。

    模态（WindowModal）；选项为「跟随框架（默认）」+ 插件实际提供的
    语言，显示「语言自称 (语言代码)」。样式令牌取自 UIKit 全局主题。
    """

    def __init__(self, plugin_id: str, plugin_name: str,
                 parent: Optional[QWidget] = None):
        """初始化对话框。

        Args:
            plugin_id: 插件 UUID（语言覆盖以此持久化）
            plugin_name: 插件显示名（用于对话框标题）
            parent: 父窗口（通常为插件管理对话框）
        """
        super().__init__(parent)
        self._plugin_id = plugin_id
        self._language_manager = get_language_manager()
        self.setWindowTitle(tr(_I18N_GROUP, "language.dialog_title", name=plugin_name))
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumWidth(DIALOG_MIN_WIDTH)
        self._init_ui()

    def _init_ui(self) -> None:
        """构建语言选项列表与确定/取消按钮布局。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            CONTENT_MARGIN, CONTENT_MARGIN, CONTENT_MARGIN, CONTENT_MARGIN
        )
        layout.setSpacing(CONTENT_SPACING)

        # 语言选项列表（当前生效项默认选中）
        self._language_list = QListWidget(self)
        self._populate_options()
        layout.addWidget(self._language_list)

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

    def _populate_options(self) -> None:
        """填充选项列表：「跟随框架（默认）」+ 插件提供的各语言。"""
        current_override = self._language_manager.plugin_language_override(self._plugin_id)

        # 第一项：跟随框架（UserRole 存 None，与具体语言代码区分）
        follow_item = QListWidgetItem(tr(_I18N_GROUP, "language.follow_option"))
        follow_item.setData(Qt.ItemDataRole.UserRole, None)
        self._language_list.addItem(follow_item)
        if current_override is None:
            self._language_list.setCurrentItem(follow_item)

        for code in self._language_manager.plugin_available_languages(self._plugin_id):
            display_name = self._language_manager.language_display_name(code)
            item = QListWidgetItem(f"{display_name} ({code})")
            # 语言代码存入 UserRole，确定时据此设置覆盖（不解析显示文本）
            item.setData(Qt.ItemDataRole.UserRole, code)
            self._language_list.addItem(item)
            if code == current_override:
                self._language_list.setCurrentItem(item)

    def _on_ok_clicked(self) -> None:
        """「确定」按钮：写入/清除语言覆盖（set_plugin_language 内部去重），随后关闭。"""
        item = self._language_list.currentItem()
        if item is not None:
            code = item.data(Qt.ItemDataRole.UserRole)
            self._language_manager.set_plugin_language(self._plugin_id, code or None)
        self.accept()
