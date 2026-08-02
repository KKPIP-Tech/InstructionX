"""
主窗口模块

定义应用程序主窗口类，包含菜单栏、主布局和插件系统集成。
"""

from pathlib import Path
from typing import List, Optional, Tuple

# ===================================================================
# PySide 相关
from PySide6.QtWidgets import (
    QMainWindow, QWidget,
    QVBoxLayout,
    QDialog, QLabel,
    QApplication, QGraphicsDropShadowEffect
)
from PySide6.QtGui import (
    QAction, QCursor, QMouseEvent, QColor, QCloseEvent, QIcon
)
from PySide6.QtCore import Qt

# ===================================================================
# 自定义工具
from ui.skills_panel.panel import SkillsPanel
from ui.dialog.plugin_management_dialog import PluginManagementDialog
from ui.dialog.about_dialog import AboutDialog
from ui.dialog.license_dialog import LicenseDialog
from ui.dialog.github_plugin_install_dialog import GitHubPluginInstallDialog
from ui.dialog.llm_settings import LLMSettingsDialog
from ui.work_area.work_area import WorkArea
from ui.title_bar import CustomTitleBar
from ui.usage_panel import UsagePanel
from ui.tray import TrayIconManager
from ui.dialog.close_confirm_dialog import CloseChoice, CloseConfirmDialog
from core.plugin.manager import PluginManager
from core.data.data_provider import DataProvider, DataNamespace
from core.interfaces import IPlugin, TaskStatus
from core.task.background_task import BackgroundTaskManager, LONG_TASK_STATUS_RUNNING
from core.llm.llm_provider import get_llm_provider
from utils.logging_tools import LoggerManager, get_name
from ui.uikit_theme import apply_uikit_theme, current_theme_mode
from InstructionX_UIKit import T


# ===================================================================
# 模块级常量
# 窗口最小尺寸与默认尺寸
WINDOW_MIN_WIDTH = 800
WINDOW_MIN_HEIGHT = 600
WINDOW_DEFAULT_WIDTH = 1024
WINDOW_DEFAULT_HEIGHT = 768

# 主容器边距（左、上、右、下）
CONTAINER_MARGIN_LEFT = 8
CONTAINER_MARGIN_TOP = 0
CONTAINER_MARGIN_RIGHT = 8
CONTAINER_MARGIN_BOTTOM = 8

# 窗口阴影效果参数
SHADOW_BLUR_RADIUS = 20
SHADOW_OFFSET_X = 0
SHADOW_OFFSET_Y = 4

# 技能面板高度限制
SKILLS_PANEL_MAX_HEIGHT = 135
SKILLS_PANEL_MIN_HEIGHT = 125

# 应用配置在 DataProvider 中的插件标识与主题设置键
APP_CONFIG_PLUGIN_ID = "__app_config__"
THEME_SETTING_KEY = "theme"

# 托盘图标路径（基于本文件位置推导，与 main.py 中窗口图标同一推导方式，
# 避免相对 CWD 失效）
TRAY_ICON_FILE = Path(__file__).resolve().parent / "logo.ico"

# 任务所属插件无法解析时的兜底显示名
UNKNOWN_PLUGIN_NAME = "未知插件"


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
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.resize(WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT)

        # 获取当前主题
        self._current_theme = current_theme_mode()

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
        self._container_layout.setContentsMargins(
            CONTAINER_MARGIN_LEFT, CONTAINER_MARGIN_TOP,
            CONTAINER_MARGIN_RIGHT, CONTAINER_MARGIN_BOTTOM,
        )
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
        self._shadow_effect.setBlurRadius(SHADOW_BLUR_RADIUS)
        self._shadow_effect.setColor(QColor(0, 0, 0, 80))
        self._shadow_effect.setOffset(SHADOW_OFFSET_X, SHADOW_OFFSET_Y)
        self._container.setGraphicsEffect(self._shadow_effect)

        # 边缘 resize 相关变量
        self._resize_margin = 8  # 边缘检测区域宽度
        self._resize_dir = None  # 当前 resize 方向
        self._resize_start = None  # resize 起始位置和窗口大小

        # 开启鼠标追踪，确保 hover 状态下鼠标移动也能触发 mouseMoveEvent，
        # 从而及时更新边缘 resize 光标
        self.setMouseTracking(True)

        # 托盘运行状态（closeEvent 编排用）
        self._force_quit = False            # 显式退出路径置位，closeEvent 直接放行
        self._close_dialog_showing = False  # 关闭确认框防重入守卫
        self._active_plugin: Optional[IPlugin] = None  # 当前激活插件，托盘子菜单标记用

        # 创建系统托盘管理器并接线
        self._setup_tray()

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

        # 插件管理（安装/升级/卸载/分组/排序）
        menu_edit_plugin_manage_action = QAction("插件管理...", self)
        menu_edit_plugin_manage_action.setShortcut("Ctrl+P")
        menu_edit_plugin_manage_action.triggered.connect(self._open_plugin_management_dialog)
        menu_edit.addAction(menu_edit_plugin_manage_action)

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
        self.skills_panel.setMaximumHeight(SKILLS_PANEL_MAX_HEIGHT)  # 设置最大高度
        self.skills_panel.setMinimumHeight(SKILLS_PANEL_MIN_HEIGHT)  # 设置最小高度
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
        # 记录当前激活插件（托盘「正在运行的插件」子菜单标记用）
        self._active_plugin = plugin

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

    def _open_plugin_management_dialog(self):
        """打开插件管理对话框（安装/升级/降级/卸载/分组/排序）"""
        dialog = PluginManagementDialog(self.plugin_manager, self)
        dialog.plugins_changed.connect(self._on_plugins_changed)
        dialog.exec()

    def _on_plugins_changed(self):
        """插件集合或分组排序变化后的统一刷新"""
        self.skills_panel.load_skills_from_manager()
        # 清空工作区，避免残留已卸载插件的 Widget
        self.work_area.clear()

    def _open_about_dialog(self):
        """打开关于对话框"""
        dialog = AboutDialog(self)
        dialog.exec()

    def _open_license_dialog(self):
        """打开开源许可对话框"""
        dialog = LicenseDialog(self)
        dialog.exec()

    def _open_github_plugin_install_dialog(self):
        """打开从 GitHub 安装插件对话框"""
        dialog = GitHubPluginInstallDialog(self)
        dialog.plugin_installed.connect(self._on_github_plugin_installed)
        dialog.exec()

    def _on_github_plugin_installed(self, results):
        """GitHub 插件安装完成后的回调：重新加载插件并刷新技能面板"""
        # 重新扫描插件目录加载新插件（此前只刷新面板导致新插件不可见）
        self.plugin_manager.reload_plugins()
        self.skills_panel.load_skills_from_manager()
        self.work_area.clear()
        # 注意：安装结果提示由 GitHubPluginInstallDialog 统一弹出，
        # 此处不再重复弹窗（避免安装成功时出现双弹窗）。

    def _load_saved_theme(self):
        """从 DataProvider 加载保存的主题设置"""
        try:
            provider = DataProvider()
            # 注册应用配置插件（如果不存在）
            try:
                provider.register_plugin(APP_CONFIG_PLUGIN_ID, "AppConfig")
            except Exception as e:
                # 已注册过属正常情况，忽略
                self._logger.debug(get_name(), f"注册应用配置插件跳过（可能已注册）: {e}")

            # 读取保存的主题
            saved_theme = provider.get_plugin_data(
                APP_CONFIG_PLUGIN_ID, THEME_SETTING_KEY,
                DataNamespace.PRIVATE, "auto"
            )

            # 如果保存的主题不是 auto，则应用它
            if saved_theme != "auto":
                self._current_theme = saved_theme
                apply_uikit_theme(QApplication.instance(), saved_theme)  # type: ignore
        except Exception as e:
            # 加载失败时使用默认主题，但不静默吞掉错误
            self._logger.warning(get_name(), f"加载保存的主题设置失败，使用默认主题: {e}")

    def _save_theme(self, theme: str):
        """保存主题设置到 DataProvider"""
        try:
            provider = DataProvider()
            # 确保应用配置插件已注册
            try:
                provider.register_plugin(APP_CONFIG_PLUGIN_ID, "AppConfig")
            except Exception as e:
                # 已注册过属正常情况，忽略
                self._logger.debug(get_name(), f"注册应用配置插件跳过（可能已注册）: {e}")

            provider.set_plugin_data(
                APP_CONFIG_PLUGIN_ID, THEME_SETTING_KEY,
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
        next_theme = self._theme_map.get(self._current_theme, 'auto')
        self._current_theme = next_theme
        apply_uikit_theme(QApplication.instance(), next_theme)  # type: ignore
        self._update_container_style()
        self._update_theme_action_text()
        self._save_theme(next_theme)

    def _open_llm_settings_dialog(self):
        """
        打开 LLM 设置对话框

        新版对话框为自动保存语义（编辑即时落盘）；LLMProvider 具备惰性
        刷新，此处 Accepted 后的 reload_config() 为幂等保底调用。
        """
        dialog = LLMSettingsDialog(self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 幂等保底：确保 LLM Provider 配置为最新
            get_llm_provider().reload_config()
        # 对话框以主窗口为父对象，exec 返回后不会自动销毁；
        # 显式 deleteLater 释放其 C++ 对象树（含配置订阅面板），
        # 避免多次打开累积隐藏对话框与悬挂回调
        dialog.deleteLater()

    def _open_usage_panel(self):
        """打开用量查询面板对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("用量查询")
        dialog.setMinimumSize(900, 600)
        # 尺寸对齐用量面板 Demo 的设计密度（1100×760）
        dialog.resize(1100, 760)
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
        window_bg = T("color.bg.base")
        border_color = T("color.border")

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

    # ===============================================================
    # 系统托盘与关闭编排
    # ===============================================================

    def closeEvent(self, event: QCloseEvent) -> None:
        """拦截关闭事件（叉子 / Alt+F4 / 任务栏右键关闭的统一拦截点）。

        每次弹窗询问「退出程序 / 最小化到托盘 / 取消」（不提供记忆选项，
        每次必问）；显式退出路径（托盘菜单「退出」）直接放行。
        """
        if self._force_quit:
            # 托盘菜单「退出」等显式退出路径：放行关闭并显式结束事件循环
            # （setQuitOnLastWindowClosed(False) 后关窗不再自动退出）
            event.accept()
            app = QApplication.instance()
            if app is not None:
                app.quit()
            return
        if self._close_dialog_showing:
            # 防重入：确认框弹出期间的重复关闭触发（Alt+F4 连按等）直接忽略
            event.ignore()
            return
        choice = self._ask_close_choice()
        self._dispatch_close_choice(choice, event)

    def _ask_close_choice(self) -> CloseChoice:
        """弹出关闭确认对话框（模态，每次必问），期间置防重入守卫。

        Returns:
            用户选择的三值枚举；Esc / 对话框叉号等价于 CANCEL
        """
        self._close_dialog_showing = True
        try:
            return CloseConfirmDialog.ask(self)
        finally:
            self._close_dialog_showing = False

    def _dispatch_close_choice(self, choice: CloseChoice, event: QCloseEvent) -> None:
        """按用户在确认框中的选择分发关闭行为。

        Args:
            choice: 用户在确认框中的选择
            event: 原始关闭事件（按分支 accept / ignore）
        """
        if choice is CloseChoice.EXIT:
            # setQuitOnLastWindowClosed(False) 后关窗不再自动退出，需显式 quit
            self._force_quit = True
            event.accept()
            app = QApplication.instance()
            if app is not None:
                app.quit()
            return
        if choice is CloseChoice.MINIMIZE_TO_TRAY:
            event.ignore()
            self._minimize_to_tray()
            return
        # 取消：忽略关闭事件，窗口保持原状
        event.ignore()

    def _setup_tray(self) -> None:
        """创建托盘管理器并接线（信号连接、状态子菜单数据回调注入）。"""
        self._tray_manager = TrayIconManager(QIcon(str(TRAY_ICON_FILE)), parent=self)
        self._tray_manager.set_status_providers(
            self._collect_running_plugins, self._collect_running_tasks
        )
        self._tray_manager.show_main_window_requested.connect(self._restore_from_tray)
        self._tray_manager.quit_requested.connect(self._quit_application)
        self._tray_manager.plugin_activate_requested.connect(
            self._activate_plugin_from_tray
        )
        # 退出事件循环前隐藏托盘图标，避免通知区域残留幽灵图标；
        # 在主窗口内接线（而非 main.py），main.py 无需感知托盘存在
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._tray_manager.hide)

    def _minimize_to_tray(self) -> None:
        """最小化到系统托盘：隐藏主窗口、托盘图标驻留并弹通知提示。

        托盘不可用（如裸 GNOME 桌面）时降级为普通最小化并记 WARNING。
        """
        if not self._tray_manager.is_tray_available():
            self._logger.warning(
                get_name(), "系统托盘不可用，「最小化到托盘」降级为普通最小化"
            )
            self.showMinimized()
            return
        # hide 才会从任务栏消失只留托盘（showMinimized 仍保留任务栏图标）
        self.hide()
        self._tray_manager.show()
        # 每次最小化到托盘都弹通知提示（发送失败由门面降级为仅记日志）
        self._tray_manager.show_minimize_hint()

    def _restore_from_tray(self) -> None:
        """从托盘恢复主窗口；托盘图标随恢复移除（下次最小化时再驻留）。"""
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self._tray_manager.hide()

    def _quit_application(self) -> None:
        """真正退出程序（托盘菜单「退出」调用）：用户意图已明确，不再询问。"""
        self._force_quit = True
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _activate_plugin_from_tray(self, plugin: IPlugin) -> None:
        """托盘插件子菜单点击：恢复主窗口并切换到指定插件。

        Args:
            plugin: 目标插件实例
        """
        self._restore_from_tray()
        self._on_skill_clicked(plugin)

    def _collect_running_plugins(self) -> List[Tuple[IPlugin, bool]]:
        """托盘「正在运行的插件」子菜单数据：已加载插件 + 当前激活标记。

        Returns:
            [(插件实例, 是否当前激活), ...]；查询异常记 WARNING 返回空列表
        """
        try:
            plugins = self.plugin_manager.get_all_plugins()
            return [(plugin, plugin is self._active_plugin) for plugin in plugins]
        except Exception as e:
            self._logger.warning(get_name(), f"收集已加载插件列表失败: {e}")
            return []

    def _collect_running_tasks(self) -> List[Tuple[str, str]]:
        """托盘「后台正在运行的任务」子菜单数据。

        合并一次性任务（RUNNING/PENDING）与运行中的长期任务。

        Returns:
            [(任务名, 所属插件名), ...]；查询异常记 WARNING 返回空列表
        """
        try:
            manager = BackgroundTaskManager._instance
            if manager is None:
                return []
            entries: List[Tuple[str, str]] = []
            for task in manager.get_all_tasks():
                if task.status in (TaskStatus.RUNNING, TaskStatus.PENDING):
                    entries.append((task.name, self._resolve_plugin_name(task.plugin_id)))
            for long_task in manager.get_long_running_tasks():
                if long_task.current_status == LONG_TASK_STATUS_RUNNING:
                    entries.append(
                        (long_task.name, self._resolve_plugin_name(long_task.plugin_id))
                    )
            return entries
        except Exception as e:
            self._logger.warning(get_name(), f"收集后台运行任务列表失败: {e}")
            return []

    def _resolve_plugin_name(self, plugin_id: str) -> str:
        """将任务记录的插件 UUID 解析为插件显示名。

        Args:
            plugin_id: 插件 UUID

        Returns:
            插件显示名；无法解析时回退为 UUID 本身，空 UUID 时为占位文案
        """
        plugin = self.plugin_manager.get_plugin_by_id(plugin_id)
        if plugin is not None:
            return plugin.plugin_name
        return plugin_id if plugin_id else UNKNOWN_PLUGIN_NAME
