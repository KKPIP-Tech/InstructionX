"""
插件排序对话框
允许用户调整 skills panel 中插件的显示顺序
"""
from typing import List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem,
    QPushButton, QFrame, QAbstractItemView, QAbstractItemDelegate, QStyle
)
from PySide6.QtCore import Qt, QSize, QMimeData, QByteArray, QRect
from PySide6.QtGui import QFont, QDrag, QPixmap, QPainter, QIcon, QColor, QFontMetrics

from core.plugin.manager import PluginManager


class OrderListWidget(QListWidget):
    """自定义列表控件，优化拖动时的显示效果"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # 设置拖拽属性
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

        # 回调函数，用于更新图标序号
        self.update_icon_callback = None

        # 拖拽完成后更新序号
        self.model().rowsMoved.connect(self._on_rows_moved)

    def set_update_icon_callback(self, callback):
        """设置更新图标的回调函数"""
        self.update_icon_callback = callback

    def _on_rows_moved(self):
        """当行移动时（拖拽完成后），更新序号"""
        if self.update_icon_callback:
            self.update_icon_callback()

    def mousePressEvent(self, event):
        """处理鼠标按下事件"""
        super().mousePressEvent(event)
        # 确保按下时选中当前项
        current_item = self.itemAt(event.pos())
        if current_item:
            self.setCurrentItem(current_item)

    def startDrag(self, supportedActions):
        """重写 startDrag 方法，自定义拖动时的显示"""
        # 调用父类方法，保持拖拽功能正常
        super().startDrag(supportedActions)


class PluginOrderDialog(QDialog):
    """插件排序对话框"""

    def __init__(self, plugin_manager: PluginManager, parent=None):
        """
        初始化插件排序对话框

        Args:
            plugin_manager: 插件管理器实例
            parent: 父窗口
        """
        super().__init__(parent)
        self.plugin_manager = plugin_manager
        self.setWindowTitle("插件排序")
        self.setMinimumSize(700, 500)

        self._init_ui()
        self._load_plugins()

    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        title_label = QLabel("拖动插件项来调整顺序")
        title_font = QFont()
        title_font.setPointSize(10)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # 分割线
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        # 主要内容区域（两个列表）
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)

        # 左侧：官方插件
        official_layout = QVBoxLayout()
        official_label = QLabel("官方插件")
        official_label.setProperty("captionBold", "true")
        official_label.style().unpolish(official_label)
        official_label.style().polish(official_label)
        official_layout.addWidget(official_label)

        self.official_list = OrderListWidget()
        self.official_list.setProperty("class", "dialog")
        self.official_list.style().unpolish(self.official_list)
        self.official_list.style().polish(self.official_list)
        official_layout.addWidget(self.official_list)
        content_layout.addLayout(official_layout, stretch=1)

        # 右侧：第三方插件
        thirdparty_layout = QVBoxLayout()
        thirdparty_label = QLabel("第三方插件")
        thirdparty_label.setProperty("captionBold", "true")
        thirdparty_label.style().unpolish(thirdparty_label)
        thirdparty_label.style().polish(thirdparty_label)
        thirdparty_layout.addWidget(thirdparty_label)

        self.thirdparty_list = OrderListWidget()
        self.thirdparty_list.setProperty("class", "dialog")
        self.thirdparty_list.style().unpolish(self.thirdparty_list)
        self.thirdparty_list.style().polish(self.thirdparty_list)
        thirdparty_layout.addWidget(self.thirdparty_list)
        content_layout.addLayout(thirdparty_layout, stretch=1)

        layout.addLayout(content_layout, stretch=1)

        # 分割线
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.HLine)
        separator2.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator2)

        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        # 重置按钮
        self.reset_button = QPushButton("重置")
        self.reset_button.setMinimumWidth(80)
        self.reset_button.clicked.connect(self._reset_order)
        button_layout.addWidget(self.reset_button)

        button_layout.addSpacing(10)

        # 取消按钮
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setMinimumWidth(80)
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        button_layout.addSpacing(10)

        # 保存按钮
        self.save_button = QPushButton("保存")
        self.save_button.setMinimumWidth(80)
        self.save_button.setProperty("class", "accentSave")
        self.save_button.style().unpolish(self.save_button)
        self.save_button.style().polish(self.save_button)
        self.save_button.clicked.connect(self._save_order)
        button_layout.addWidget(self.save_button)

        layout.addLayout(button_layout)

    def _create_icon_with_number(self, original_icon: QIcon, number: int) -> QIcon:
        """
        创建一个包含序号的图标（序号以文本形式在图标前面）

        Args:
            original_icon: 原始插件图标
            number: 序号

        Returns:
            包含序号的新图标
        """
        # 创建一个画布来容纳序号和图标
        combined_size = QSize(48, 32)
        pixmap = QPixmap(combined_size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制序号文字（纯文本，无背景）
        painter.setPen(QColor("#333333"))
        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        painter.setFont(font)

        number_text = str(number)
        text_rect = QRect(0, 0, 16, 32)
        flags = Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextSingleLine
        painter.drawText(text_rect, flags, number_text)

        # 绘制原始图标（在序号右侧）
        if original_icon:
            icon_pixmap = original_icon.pixmap(QSize(32, 32))
            painter.drawPixmap(16, 0, icon_pixmap)

        painter.end()

        return QIcon(pixmap)

    def _update_all_icons(self):
        """更新所有列表项的图标序号"""
        # 更新官方插件列表的图标
        for i in range(self.official_list.count()):
            item = self.official_list.item(i)
            plugin_id = item.data(Qt.ItemDataRole.UserRole)
            # 通过 UUID 查找对应的插件
            plugin = self.plugin_manager.get_plugin_by_id(plugin_id)
            if plugin:
                icon = getattr(plugin, 'skill_icon', None)
                if icon is None or icon.isNull():
                    style = self.style()
                    icon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)
                combined_icon = self._create_icon_with_number(icon, i + 1)
                item.setIcon(combined_icon)

        # 更新第三方插件列表的图标
        for i in range(self.thirdparty_list.count()):
            item = self.thirdparty_list.item(i)
            plugin_id = item.data(Qt.ItemDataRole.UserRole)
            # 通过 UUID 查找对应的插件
            plugin = self.plugin_manager.get_plugin_by_id(plugin_id)
            if plugin:
                icon = getattr(plugin, 'skill_icon', None)
                if icon is None or icon.isNull():
                    style = self.style()
                    icon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)
                combined_icon = self._create_icon_with_number(icon, i + 1)
                item.setIcon(combined_icon)

    def _load_plugins(self):
        """加载插件到列表"""
        # 清空列表
        self.official_list.clear()
        self.thirdparty_list.clear()

        # 设置图标大小（带有序号的组合图标）
        icon_size = QSize(48, 32)
        self.official_list.setIconSize(icon_size)
        self.thirdparty_list.setIconSize(icon_size)

        # 设置更新图标的回调函数
        self.official_list.set_update_icon_callback(self._update_all_icons)
        self.thirdparty_list.set_update_icon_callback(self._update_all_icons)

        # 加载官方插件
        official_plugins = self.plugin_manager.get_official_plugins()
        for index, plugin in enumerate(official_plugins, start=1):
            # 获取插件图标
            icon = getattr(plugin, 'skill_icon', None)
            if icon is None or icon.isNull():
                # 使用默认图标
                style = self.style()
                icon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)

            # 创建带有序号的组合图标（序号以纯文本形式在图标前面）
            combined_icon = self._create_icon_with_number(icon, index)

            # 只显示插件名称，序号在图标中
            item = QListWidgetItem(combined_icon, plugin.plugin_name)
            item.setData(Qt.ItemDataRole.UserRole, plugin.plugin_id)  # 使用 UUID
            self.official_list.addItem(item)

        # 加载第三方插件
        thirdparty_plugins = self.plugin_manager.get_thirdparty_plugins()
        for index, plugin in enumerate(thirdparty_plugins, start=1):
            # 获取插件图标
            icon = getattr(plugin, 'skill_icon', None)
            if icon is None or icon.isNull():
                # 使用默认图标
                style = self.style()
                icon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)

            # 创建带有序号的组合图标（序号以纯文本形式在图标前面）
            combined_icon = self._create_icon_with_number(icon, index)

            # 只显示插件名称，序号在图标中
            item = QListWidgetItem(combined_icon, plugin.plugin_name)
            item.setData(Qt.ItemDataRole.UserRole, plugin.plugin_id)  # 使用 UUID
            self.thirdparty_list.addItem(item)

    def _get_ordered_plugin_names(self, list_widget: QListWidget) -> List[str]:
        """获取列表中插件名称的顺序"""
        plugin_names = []
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            plugin_name = item.data(Qt.ItemDataRole.UserRole)
            plugin_names.append(plugin_name)
        return plugin_names

    def _save_order(self):
        """保存插件顺序"""
        # 获取排序后的插件名称
        official_order = self._get_ordered_plugin_names(self.official_list)
        thirdparty_order = self._get_ordered_plugin_names(self.thirdparty_list)

        # 保存到配置文件
        success = self.plugin_manager.save_plugin_order(official_order, thirdparty_order)

        if success:
            # 应用新顺序
            self.plugin_manager.apply_custom_order()
            self.accept()
        else:
            # 显示错误信息（使用简单的消息框）
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "保存失败",
                "无法保存插件顺序配置，请检查权限和磁盘空间。"
            )

    def _reset_order(self):
        """重置为默认顺序"""
        # 清空当前顺序
        self.plugin_manager.config_manager.save_plugin_order([], [])

        # 重新加载插件（使用默认顺序）
        self.plugin_manager.apply_custom_order()
        self._load_plugins()
