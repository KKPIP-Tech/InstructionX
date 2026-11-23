"""pytest tests for utils.thread_utils."""
import threading
import time

import pytest

import utils.thread_utils as thread_utils


@pytest.fixture(autouse=True)
def reset_thread_utils_invoker(monkeypatch):
    """每个测试前重置 thread_utils 的延迟 invoker 单例。"""
    monkeypatch.setattr(thread_utils, "_invoker", None)
    yield


class TestIsUIThread:
    """Tests for is_ui_thread()."""

    def test_returns_false_without_qapplication(self, monkeypatch):
        """无 QApplication 实例时返回 False。"""
        monkeypatch.setattr(thread_utils, "_get_app", lambda: None)
        assert thread_utils.is_ui_thread() is False

    def test_returns_true_on_main_thread_with_qapp(self, qapp_instance):
        """主线程在 QApplication 存在时应被视为 UI 线程。"""
        assert thread_utils.is_ui_thread() is True

    def test_returns_false_on_worker_thread_with_qapp(self, qapp_instance):
        """工作线程在 QApplication 存在时不应被视为 UI 线程。"""
        result = {}

        def worker():
            result["ui"] = thread_utils.is_ui_thread()

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        assert result["ui"] is False


class TestRunInUIThread:
    """Tests for run_in_ui_thread()."""

    def test_runs_directly_without_qapplication(self, monkeypatch):
        """无 QApplication 时直接在当前线程执行。"""
        monkeypatch.setattr(thread_utils, "_get_app", lambda: None)
        called = []
        thread_utils.run_in_ui_thread(lambda: called.append(1))
        assert called == [1]

    def test_runs_on_main_thread_with_qapp(self, qapp_instance, qtbot):
        """已在 UI 线程时直接同步执行。"""
        called = []
        thread_utils.run_in_ui_thread(lambda: called.append(threading.current_thread().name))
        assert called == [threading.current_thread().name]

    def test_marshals_to_ui_thread(self, qapp_instance, qtbot):
        """工作线程投递到 UI 线程执行。"""
        result = []
        event = threading.Event()

        def worker():
            def ui_op():
                result.append(threading.current_thread().name)
                event.set()

            thread_utils.run_in_ui_thread(ui_op)

        t = threading.Thread(target=worker)
        t.start()
        qtbot.waitUntil(event.is_set, timeout=2000)
        t.join()
        assert result
        assert result[0] == threading.current_thread().name


class TestRunInUIThreadSync:
    """Tests for run_in_ui_thread_sync()."""

    def test_returns_directly_without_qapplication(self, monkeypatch):
        """无 QApplication 时直接返回结果。"""
        monkeypatch.setattr(thread_utils, "_get_app", lambda: None)
        assert thread_utils.run_in_ui_thread_sync(lambda: 42) == 42

    def test_returns_result_from_ui_thread(self, qapp_instance, qtbot):
        """同步等待 UI 线程执行并返回结果。"""
        assert thread_utils.run_in_ui_thread_sync(lambda: "hello") == "hello"

    def test_re_raises_exception_from_ui_thread(self, qapp_instance, qtbot):
        """UI 线程函数抛出的异常应在调用线程重新抛出。"""

        def fail():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            thread_utils.run_in_ui_thread_sync(fail)

    def test_times_out_when_ui_thread_blocked(self, qapp_instance, qtbot):
        """UI 线程长时间不处理时，工作线程调用 sync 超时抛 TimeoutError。"""
        block_event = threading.Event()
        release_event = threading.Event()
        timeout_raised = []

        def occupy():
            block_event.set()
            release_event.wait(timeout=5)

        def worker():
            thread_utils.run_in_ui_thread(occupy)
            # 从工作线程调用 sync，此时 UI 线程被 occupy 阻塞
            try:
                thread_utils.run_in_ui_thread_sync(lambda: None, timeout=0.2)
            except TimeoutError:
                timeout_raised.append(True)

        t = threading.Thread(target=worker)
        t.start()
        qtbot.waitUntil(block_event.is_set, timeout=2000)
        t.join(timeout=3)
        assert timeout_raised, "Expected TimeoutError from blocked UI thread"
