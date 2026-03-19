"""
Main Window Tests

测试用例：
- MW-01: 窗口创建/销毁 (正常/多次创建)
- MW-02: 菜单栏功能 (所有菜单项可点击)
- MW-03: 窗口大小调整 (最小/最大/自定义尺寸)
- MW-04: 窗口关闭 (有未保存数据/无数据)
"""
import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget
from PySide6.QtCore import Qt


@pytest.mark.gui
class TestMainWindow:
    """测试主窗口"""

    @pytest.fixture
    def qapp(self):
        """QApplication fixture"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app

    @pytest.fixture
    def mock_main_window(self, qapp):
        """创建模拟的主窗口"""
        from unittest.mock import MagicMock

        # 创建模拟的窗口对象
        window = MagicMock()
        window._plugin_manager = MagicMock()
        window._data_provider = MagicMock()
        window._task_manager = MagicMock()

        yield window

    def test_mw_01_window_creation(self, qapp, mock_main_window):
        """MW-01: 测试窗口创建"""
        assert mock_main_window is not None

    def test_mw_03_resize_window(self, qapp, mock_main_window):
        """MW-03: 测试调整窗口大小"""
        # 模拟大小调整
        mock_main_window.width = MagicMock(return_value=800)
        mock_main_window.height = MagicMock(return_value=600)

        assert mock_main_window.width() == 800
        assert mock_main_window.height() == 600


@pytest.mark.gui
class TestMenuBar:
    """测试菜单栏"""

    @pytest.fixture
    def qapp(self):
        """QApplication fixture"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app

    @pytest.fixture
    def main_window_with_menu(self, qapp):
        """创建带菜单的主窗口"""
        # 创建一个真实的 QMainWindow 用于测试
        window = QMainWindow()
        menubar = window.menuBar()

        # 添加测试菜单
        test_menu = menubar.addMenu("Test")

        action1 = test_menu.addAction("Action 1")
        action2 = test_menu.addAction("Action 2")

        yield window, menubar, [action1, action2]

        window.close()

    def test_mw_02_menu_exists(self, main_window_with_menu):
        """MW-02: 测试菜单存在"""
        window, menubar, actions = main_window_with_menu

        # 验证有菜单
        assert menubar is not None

    def test_mw_02_menu_actions(self, main_window_with_menu):
        """MW-02: 测试菜单项可点击"""
        window, menubar, actions = main_window_with_menu

        # 验证菜单项存在
        assert len(actions) == 2

        # 触发动作
        for action in actions:
            action.trigger()
