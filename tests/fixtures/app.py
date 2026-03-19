"""
QApplication fixture

提供 QApplication 实例用于 GUI 测试。
"""
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """
    Session 级别的 QApplication fixture

    注意：GUI 测试使用此 fixture，session 级别确保只有一个 QApplication 实例。
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    # Session 结束后不退出 app，让 pytest-qt 处理


@pytest.fixture
def qapp_widget(qapp):
    """
    提供一个临时的 QWidget 用于测试

    每次调用创建新 widget，测试结束后自动销毁
    """
    from PySide6.QtWidgets import QWidget

    widget = QWidget()
    yield widget
    widget.deleteLater()
