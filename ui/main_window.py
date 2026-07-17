"""
主窗口模块

定义应用程序主窗口类，包含菜单栏、主布局和插件系统集成。
"""

from typing import Optional

# ===================================================================
# PySide 相关
from PySide6.QtWidgets import (
    QMainWindow, QWidget,
    QVBoxLayout,
    QDialog, QLabel,
    QApplication, QGraphicsDropShadowEffect
)
from PySide6.QtGui import (
    QAction, QCursor, QMouseEvent, QColor
)
from PySide6.QtCore import Qt

# ===================================================================
# 自定义工具
from ui.skills_panel.panel import SkillsPanel
from ui.dialog.plugin_order_dialog import PluginOrderDialog
from ui.work_area.work_area import WorkArea
from ui.title_bar import CustomTitleBar
from core.plugin.manager import PluginManager
from core.data.data_provider import DataProvider, DataNamespace
from utils.style_qss import get_style_qss
from utils.logging_tools import LoggerManager, get_name


class InstructionXMainWindow(QMainWindow):
    """
    应用程序主窗口

    采用单窗口多面板布局：
    - 顶部：菜单栏
    - 左侧：技能面板（插件选择器）
    - 右侧：工作区（显示激活的插件界面）

    负责初始化插件系统、响应技能点击、管理工作区内容。
    """

    def __init__(self):
        """
        初始化主窗口

        设置窗口尺寸，创建菜单栏，初始化插件系统。
        """

        super().__init__()

        self._logger = LoggerManager()

        # 设置无边框窗口
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 设置初始窗口大小
        self.setMinimumSize(800, 600)
        self.resize(1024, 768)

        # 获取当前主题
        self._style_qss = get_style_qss()
        self._current_theme = self._style_qss.theme()

        # 主题映射：浅色 → 深色 → 跟随系统
        self._theme_map = {'light': 'dark', 'dark': 'auto', 'auto': 'light'}

        # 加载保存的主题设置
        self._load_saved_theme()

        # 创建主容器（用于圆角效果）
        self._container = QWidget()
        self._container.setObjectName("mainContainer")
        self.setCentralWidget(self._container)

        # 主布局
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(8, 0, 8, 8)
        self._container_layout.setSpacing(0)

        # 创建自定义标题栏
        self._title_bar = CustomTitleBar(self)
        self._container_layout.addWidget(self._title_bar)

        # 创建菜单栏并移到标题栏
        self._create_menus()

        # 创建主布局内容
        self._create_main_layout()

        # 应用容器样式
        self._update_container_style()

        # 创建 Qt 阴影效果（替代 DWM 原生阴影，避免 WM_NCCALCSIZE 坐标错位）
        # 性能取舍：QGraphicsDropShadowEffect 需对整个容器做离屏渲染，
        # 低端机器上略有开销；但可彻底规避 DWM 方案的坐标错位问题，
        # 且 blurRadius 控制在 20 以限制渲染成本。
        self._shadow_effect = QGraphicsDropShadowEffect(self)
        self._shadow_effect.setBlurRadius(20)
        self._shadow_effect.setColor(QColor(0, 0, 0, 80))
        self._shadow_effect.setOffset(0, 4)
        self._container.setGraphicsEffect(self._shadow_effect)

        # 边缘 resize 相关变量
        self._resize_margin = 8  # 边缘检测区域宽度
        self._resize_dir = None  # 当前 resize 方向
        self._resize_start = None  # resize 起始位置和窗口大小

        # 开启鼠标追踪，确保 hover 状态下鼠标移动也能触发 mouseMoveEvent，
        # 从而及时更新边缘 resize 光标
        self.setMouseTracking(True)

    # ===============================================================
    # GUI 界面
    def _create_menus(self) -> None:
        """
        创建菜单栏

        包含编辑、用户中心、帮助等菜单项。
        菜单栏将移动到自定义标题栏中。
        """

        # 获取原生菜单栏并移到自定义标题栏
        menu_bar = self.menuBar()
        menu_bar.setNativeMenuBar(False)
        self._title_bar.set_menu_bar(menu_bar)

        # -------------------------------------------------
        # 编辑
        menu_edit = menu_bar.addMenu("编辑")

        # 插件排序
        menu_edit_plugin_order_action = QAction("插件排序", self)
        menu_edit_plugin_order_action.setShortcut("Ctrl+P")
        menu_edit_plugin_order_action.triggered.connect(self._open_plugin_order_dialog)
        menu_edit.addAction(menu_edit_plugin_order_action)

        # 主题切换
        self._menu_theme_action = QAction("切换主题", self)
        self._menu_theme_action.setToolTip("浅色 → 深色 → 跟随系统")
        self._menu_theme_action.triggered.connect(self._cycle_theme)
        menu_edit.addAction(self._menu_theme_action)
        self._update_theme_action_text()

        # 分隔线
        menu_edit.addSeparator()

        # 从 GitHub 安装插件
        menu_edit_github_install_action = QAction("从 GitHub 安装插件...", self)
        menu_edit_github_install_action.setStatusTip("从 GitHub 仓库安装插件")
        menu_edit_github_install_action.triggered.connect(self._open_github_plugin_install_dialog)
        menu_edit.addAction(menu_edit_github_install_action)

        # -------------------------------------------------
        # 用户中心
        menu_user = menu_bar.addMenu("用户中心")

        # -------------------------------------------------
        # AI 菜单
        self._create_ai_menu(menu_bar)

        # -------------------------------------------------
        # 帮助
        menu_help = menu_bar.addMenu("帮助")

        # 关于软件
        menu_help_about_action = QAction("关于", self)
        menu_help_about_action.triggered.connect(self._open_about_dialog)
        menu_help.addAction(menu_help_about_action)

        # 许可信息
        menu_help_license_action = QAction("许可信息", self)
        menu_help_license_action.triggered.connect(self._open_license_dialog)
        menu_help.addAction(menu_help_license_action)


    def _create_main_layout(self) -> None:
        """
        创建主布局

        初始化插件管理器，加载插件，创建技能面板和工作区。
        """

        # 创建内容布局（用于技能面板和工作区）
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(5)
        self._container_layout.addLayout(content_layout)

        # 初始化插件管理器
        self.plugin_manager = PluginManager()
        self.plugin_manager.load_plugins()

        # 应用自定义插件顺序
        self.plugin_manager.apply_custom_order()

        # 创建并添加 SkillsPanel（固定高度）
        self.skills_panel = SkillsPanel(self._container)
        self.skills_panel.set_plugin_manager(self.plugin_manager)
        self.skills_panel.load_skills_from_manager()
        self.skills_panel.setMaximumHeight(135)  # 设置最大高度
        self.skills_panel.setMinimumHeight(125)  # 设置最小高度
        content_layout.addWidget(self.skills_panel)

        # 创建工作区（可伸缩）
        self.work_area = WorkArea(self._container)
        content_layout.addWidget(self.work_area.get_widget(), stretch=1)

        # 设置清除高亮的回调
        self.work_area.set_clear_highlight_callback(self.skills_panel.clear_active_state)

        # 连接技能点击信号
        self.skills_panel.skill_clicked.connect(self._on_skill_clicked)

    def _on_skill_clicked(self, plugin):
        """
        处理技能按钮点击事件

        清除工作区并显示被点击插件的用户界面。
        注意：不清除按钮的高亮状态，以指示当前激活的插件。

        Args:
            plugin: 被点击的插件实例
        """
        # 清空工作区（不清除按钮高亮）
        self.work_area.clear_keep_highlight()

        # 获取插件的 widget 并显示在工作区
        plugin_widget = plugin.get_widget(parent=self.work_area.get_widget())
        if plugin_widget:
            self.work_area.add_widget(plugin_widget)
        else:
            # 如果插件 widget 创建失败，显示错误信息，并附带“重试”链接
            # （保持向工作区添加 QLabel 的接口约定，重试通过链接触发）
            error_label = QLabel(
                f"无法加载插件：{plugin.plugin_name}　<a href='retry'>点击重试</a>"
            )
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            error_label.setProperty("error", "true")
            error_label.style().unpolish(error_label)
            error_label.style().polish(error_label)
            error_label.setToolTip("加载失败，点击“点击重试”重新加载插件")
            error_label.linkActivated.connect(
                lambda _link, p=plugin: self._on_skill_clicked(p)
            )
            self.work_area.add_widget(error_label)

    def _open_plugin_order_dialog(self):
        """
        打开插件排序对话框

        用户保存排序后，重新加载技能面板以显示新的顺序。
        """
        dialog = PluginOrderDialog(self.plugin_manager, self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 用户点击了保存，重新加载 skills panel
            self.skills_panel.load_skills_from_manager()

    def _open_about_dialog(self):
        """打开关于对话框"""
        from ui.dialog.about_dialog import AboutDialog
        dialog = AboutDialog(self)
        dialog.exec()

    def _open_license_dialog(self):
        """打开开源许可对话框"""
        from ui.dialog.license_dialog import LicenseDialog
        dialog = LicenseDialog(self)
        dialog.exec()

    def _open_github_plugin_install_dialog(self):
        """打开从 GitHub 安装插件对话框"""
        from ui.dialog.github_plugin_install_dialog import GitHubPluginInstallDialog
        dialog = GitHubPluginInstallDialog(self)
        dialog.plugin_installed.connect(self._on_github_plugin_installed)
        dialog.exec()

    def _on_github_plugin_installed(self, results):
        """GitHub 插件安装完成后的回调"""
        # 重新加载技能面板
        self.skills_panel.load_skills_from_manager()
        # 注意：安装结果提示由 GitHubPluginInstallDialog 统一弹出，
        # 此处不再重复弹窗（避免安装成功时出现双弹窗）。

    def _load_saved_theme(self):
        """从 DataProvider 加载保存的主题设置"""
        try:
            provider = DataProvider()
            # 注册应用配置插件（如果不存在）
            try:
                provider.register_plugin("__app_config__", "AppConfig")
            except Exception:
                pass  # 已注册过属正常情况，忽略

            # 读取保存的主题
            saved_theme = provider.get_plugin_data(
                "__app_config__", "theme",
                DataNamespace.PRIVATE, "auto"
            )

            # 如果保存的主题不是 auto，则应用它
            if saved_theme != "auto":
                from utils.style_qss import set_style_qss_theme
                self._current_theme = saved_theme
                set_style_qss_theme(QApplication.instance(), saved_theme)  # type: ignore
        except Exception as e:
            # 加载失败时使用默认主题，但不静默吞掉错误
            self._logger.warning(get_name(), f"加载保存的主题设置失败，使用默认主题: {e}")

    def _save_theme(self, theme: str):
        """保存主题设置到 DataProvider"""
        try:
            provider = DataProvider()
            # 确保应用配置插件已注册
            try:
                provider.register_plugin("__app_config__", "AppConfig")
            except Exception:
                pass  # 已注册过属正常情况，忽略

            provider.set_plugin_data(
                "__app_config__", "theme",
                theme, DataNamespace.PRIVATE, notify=False
            )
        except Exception as e:
            # 保存失败不阻断主题切换，但记录日志便于排查
            self._logger.warning(get_name(), f"保存主题设置失败: {e}")

    def _update_theme_action_text(self):
        """更新主题菜单项文字，显示当前主题"""
        theme_labels = {'light': '浅色', 'dark': '深色', 'auto': '跟随系统'}
        label = theme_labels.get(self._current_theme, '跟随系统')
        self._menu_theme_action.setText(f"切换主题 ({label})")

    def _cycle_theme(self):
        """循环切换主题：浅色 → 深色 → 跟随系统"""
        from utils.style_qss import set_style_qss_theme
        next_theme = self._theme_map.get(self._current_theme, 'auto')
        self._current_theme = next_theme
        set_style_qss_theme(QApplication.instance(), next_theme)  # type: ignore
        self._update_container_style()
        self._update_theme_action_text()
        self._save_theme(next_theme)

    def _open_llm_settings_dialog(self):
        """
        打开 LLM 设置对话框

        用户保存设置后，重新加载 LLM 提供商配置。
        """
        from ui.dialog.llm_settings_dialog import LLMSettingsDialog

        dialog = LLMSettingsDialog(self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 用户点击了保存，重新加载 LLM Provider
            from core.llm.llm_provider import get_llm_provider
            get_llm_provider().reload_config()

    def _open_usage_panel(self):
        """打开用量查询面板对话框"""
        from ui.usage_panel import UsagePanel

        dialog = QDialog(self)
        dialog.setWindowTitle("用量查询")
        dialog.setMinimumSize(900, 600)
        dialog.resize(960, 680)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        usage_panel = UsagePanel(dialog)
        layout.addWidget(usage_panel)
        dialog.exec()

    # ===============================================================
    # AI 菜单
    # ===============================================================

    def _create_ai_menu(self, menu_bar):
        """创建 AI 菜单"""
        self._ai_menu = menu_bar.addMenu("AI")

        # LLM 设置
        settings_action = QAction("LLM 设置...", self)
        settings_action.setShortcut("Ctrl+L")
        settings_action.triggered.connect(self._open_llm_settings_dialog)
        self._ai_menu.addAction(settings_action)

        # 用量查询
        usage_action = QAction("用量查询", self)
        usage_action.triggered.connect(self._open_usage_panel)
        self._ai_menu.addAction(usage_action)

    def _update_container_style(self):
        """更新容器样式（圆角/最大化状态），适配当前主题"""
        colors = self._style_qss.colors()
        window_bg = colors.get('window', '#202020')
        border_color = colors.get('borderLight', '#3C3C3C')

        if self.isMaximized() or self.isFullScreen():
            # 最大化/全屏时移除圆角和阴影
            self._container.setStyleSheet(f"""
                QWidget#mainContainer {{
                    background-color: {window_bg};
                    border-radius: 0px;
                }}
            """)
            if hasattr(self, '_shadow_effect') and self._shadow_effect:
                self._shadow_effect.setEnabled(False)
        else:
            # 还原时显示圆角和阴影
            self._container.setStyleSheet(f"""
                QWidget#mainContainer {{
                    background-color: {window_bg};
                    border-radius: 8px;
                    border: 1px solid {border_color};
                }}
            """)
            if hasattr(self, '_shadow_effect') and self._shadow_effect:
                self._shadow_effect.setEnabled(True)

    def nativeEvent(self, eventType, message):
        """
        保留原生事件接口，当前不拦截任何消息。
        先前拦截 WM_NCCALCSIZE 会导致 Qt 与 Windows 坐标系错位，
        阴影改用 QGraphicsDropShadowEffect 实现。
        """
        return super().nativeEvent(eventType, message)

    def changeEvent(self, event):
        """监听窗口状态变化，更新标题栏按钮和阴影"""
        if event.type() == event.Type.WindowStateChange:
            self._title_bar.set_maximized(self.isMaximized() or self.isFullScreen())
            # 容器圆角/阴影样式统一由 _update_container_style 处理，避免重复代码
            self._update_container_style()
        super().changeEvent(event)

    # ===============================================================
    # 边缘 resize 功能
    def _get_resize_direction(self, pos: QMouseEvent) -> Optional[str]:
        """
        检测鼠标位置对应的 resize 方向

        Args:
            pos: 鼠标事件

        Returns:
            resize 方向字符串：'top', 'bottom', 'left', 'right',
            'top-left', 'top-right', 'bottom-left', 'bottom-right' 或 None
        """
        if self.isMaximized():
            return None

        margin = self._resize_margin
        x, y = pos.pos().x(), pos.pos().y()
        width = self.width()
        height = self.height()

        # 检测是否在边缘区域
        on_left = x < margin
        on_right = x > width - margin
        on_top = y < margin
        on_bottom = y > height - margin

        if on_top and on_left:
            return 'top-left'
        elif on_top and on_right:
            return 'top-right'
        elif on_bottom and on_left:
            return 'bottom-left'
        elif on_bottom and on_right:
            return 'bottom-right'
        elif on_top:
            return 'top'
        elif on_bottom:
            return 'bottom'
        elif on_left:
            return 'left'
        elif on_right:
            return 'right'
        return None

    def _get_resize_cursor(self, direction: Optional[str]) -> Qt.CursorShape:
        """根据 resize 方向获取对应的光标样式"""
        cursor_map = {
            'top': Qt.CursorShape.SizeVerCursor,
            'bottom': Qt.CursorShape.SizeVerCursor,
            'left': Qt.CursorShape.SizeHorCursor,
            'right': Qt.CursorShape.SizeHorCursor,
            'top-left': Qt.CursorShape.SizeFDiagCursor,
            'top-right': Qt.CursorShape.SizeBDiagCursor,
            'bottom-left': Qt.CursorShape.SizeBDiagCursor,
            'bottom-right': Qt.CursorShape.SizeFDiagCursor,
        }
        return cursor_map.get(direction, Qt.CursorShape.ArrowCursor)

    def mouseMoveEvent(self, event: QMouseEvent):
        """处理鼠标移动事件 - 边缘检测和 resize"""
        # 如果正在执行 resize 操作
        if self._resize_dir and event.buttons() == Qt.MouseButton.LeftButton:
            self._do_resize(event)
            return

        # 否则检测边缘位置
        direction = self._get_resize_direction(event)
        if direction:
            cursor = self._get_resize_cursor(direction)
            self.setCursor(QCursor(cursor))
            self._resize_dir = direction
        else:
            if self._resize_dir:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
                self._resize_dir = None

        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        """处理鼠标按下事件 - 开始 resize"""
        if event.button() == Qt.MouseButton.LeftButton:
            direction = self._get_resize_direction(event)
            if direction and not self.isMaximized():
                self._resize_dir = direction
                self._resize_start = {
                    'pos': event.globalPosition().toPoint(),
                    'geometry': self.geometry()
                }
                return

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """处理鼠标释放事件 - 结束 resize"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._resize_dir = None
            self._resize_start = None
            # 恢复默认光标
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

        super().mouseReleaseEvent(event)

    def _do_resize(self, event: QMouseEvent):
        """执行窗口 resize"""
        if not self._resize_start:
            return

        start_pos = self._resize_start['pos']
        start_geo = self._resize_start['geometry']
        current_pos = event.globalPosition().toPoint()

        delta = current_pos - start_pos
        direction = self._resize_dir

        new_x = start_geo.x()
        new_y = start_geo.y()
        new_width = start_geo.width()
        new_height = start_geo.height()

        # 根据方向调整窗口几何
        if 'left' in direction:
            new_x = start_geo.x() + delta.x()
            new_width = start_geo.width() - delta.x()
        if 'right' in direction:
            new_width = start_geo.width() + delta.x()
        if 'top' in direction:
            new_y = start_geo.y() + delta.y()
            new_height = start_geo.height() - delta.y()
        if 'bottom' in direction:
            new_height = start_geo.height() + delta.y()

        # 应用最小尺寸限制；从左/上边缘缩放被钳制时同步回推 x/y，
        # 否则窗口右/下边缘会随鼠标继续移动，造成窗口整体漂移
        min_w = self.minimumWidth()
        min_h = self.minimumHeight()
        if new_width < min_w:
            if 'left' in direction:
                new_x = start_geo.x() + start_geo.width() - min_w
            new_width = min_w
        if new_height < min_h:
            if 'top' in direction:
                new_y = start_geo.y() + start_geo.height() - min_h
            new_height = min_h

        # 调整窗口位置和大小
        self.setGeometry(new_x, new_y, new_width, new_height)
