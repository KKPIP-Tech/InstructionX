"""MCP 单连接 actor 生命周期与超时清理测试。"""

import asyncio
from types import SimpleNamespace

import pytest

from core.mcp.async_cleanup import cancel_pending_tasks
from core.mcp.client import ConnectionActor, MCPClientManager, MCPServerConnection
from core.mcp.config import MCPRemoteServerConfig

RECONNECT_ITERATIONS = 100


class FakeExitStack:
    """记录进入和退出所在 coroutine Task 名。"""

    def __init__(self):
        self.enter_task = None
        self.close_task = None
        self.closed = False

    async def __aenter__(self):
        self.enter_task = asyncio.current_task().get_name()
        return self

    async def aclose(self):
        self.close_task = asyncio.current_task().get_name()
        self.closed = True


class FakeSession:
    """提供可控工具返回和阻塞调用。"""

    def __init__(self):
        self.delay = 0
        self.call_tasks = []

    async def call_tool(self, name, arguments):
        self.call_tasks.append(asyncio.current_task().get_name())
        if self.delay:
            await asyncio.sleep(self.delay)
        return SimpleNamespace(
            content=[SimpleNamespace(text=f"echo:{arguments.get('text', '')}")]
        )


def _config():
    return MCPRemoteServerConfig(
        server_id="test", name="Test", transport="stdio", command="python", args=[]
    )


async def _open_fake_transport(session, stack):
    await stack.__aenter__()
    return session, stack, SimpleNamespace(tools=[])


def test_actor_enters_calls_and_closes_stack_in_same_task():
    """连接进入、调用与退出栈必须属于同一 coroutine owner。"""
    async def scenario():
        stack = FakeExitStack()
        session = FakeSession()
        actor = ConnectionActor(_config())
        actor._open_transport = lambda: _open_fake_transport(session, stack)
        await actor.start()
        result = await actor.call_tool("echo", {"text": "ok"})
        await actor.stop()
        assert "echo:ok" in result.content[0].text
        assert stack.closed
        assert stack.enter_task == session.call_tasks[0] == stack.close_task

    asyncio.run(scenario())


def test_actor_timeout_cancels_remote_call_and_closes_stack():
    """调用超时必须取消远端等待并清理退出栈，且停止保持幂等。"""
    async def scenario():
        stack = FakeExitStack()
        session = FakeSession()
        session.delay = 0.05
        actor = ConnectionActor(_config(), timeout=0.005)
        actor._open_transport = lambda: _open_fake_transport(session, stack)
        await actor.start()
        with pytest.raises(asyncio.TimeoutError):
            await actor.call_tool("echo", {})
        assert stack.closed
        with pytest.raises(RuntimeError, match="正在关闭|尚未启动"):
            await actor.call_tool("echo", {})
        await actor.stop()
        await actor.stop()

    asyncio.run(scenario())


def test_actor_start_failure_closes_partially_opened_stack():
    """初始化中途失败也必须关闭已进入的上下文并唤醒启动调用。"""
    async def scenario():
        stack = FakeExitStack()
        actor = ConnectionActor(_config())

        async def fail_after_enter():
            await stack.__aenter__()
            actor._stack = stack
            raise ConnectionError("初始化失败")

        actor._open_transport = fail_after_enter
        with pytest.raises(ConnectionError, match="初始化失败"):
            await actor.start()
        assert stack.closed
        assert stack.enter_task == stack.close_task
        await actor.stop()

    asyncio.run(scenario())


def test_actor_repeated_start_stop_has_no_cancel_scope_warning():
    """反复启动停止 100 次，所有退出栈均正确关闭且无跨 Task 警告。"""
    async def scenario():
        for _ in range(RECONNECT_ITERATIONS):
            stack = FakeExitStack()
            actor = ConnectionActor(_config())
            actor._open_transport = lambda: _open_fake_transport(FakeSession(), stack)
            await actor.start()
            await actor.stop()
            assert stack.closed
            assert stack.enter_task == stack.close_task

    asyncio.run(scenario())



def test_shutdown_reports_close_failure_and_still_unregisters_tools():
    """单连接关闭失败必须进入报告，且不能跳过工具与连接表清理。"""

    class FailingActor:
        async def stop(self):
            raise RuntimeError("关闭失败")

    class Registry:
        def __init__(self):
            self.tools = {"mcp__test__echo"}

        def unregister(self, name):
            self.tools.discard(name)

    registry = Registry()
    manager = MCPClientManager(registry, timeout=0.1)
    manager._connections["test"] = MCPServerConnection(
        server_id="test",
        name="Test",
        config=_config(),
        session=None,
        actor=FailingActor(),
        tool_name_map={"mcp__test__echo": "echo"},
    )
    errors = manager.shutdown()
    assert len(errors) == 1
    assert "关闭失败" in errors[0]
    assert registry.tools == set()
    assert manager.list_connected_servers() == []



def test_cancel_pending_tasks_waits_for_cancellation():
    """事件循环关闭前必须取消并等待所有遗留后台任务。"""
    async def scenario():
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def background():
            started.set()
            try:
                await asyncio.sleep(60)
            finally:
                cancelled.set()

        task = asyncio.create_task(background())
        await started.wait()
        await cancel_pending_tasks()
        assert task.cancelled()
        assert cancelled.is_set()

    asyncio.run(scenario())



def test_connect_registration_failure_closes_opened_actor(monkeypatch):
    """连接成功后注册失败也必须关闭 actor，不能只取消已完成 Future。"""

    class OpenedActor:
        def __init__(self):
            self.stop_calls = 0

        async def start(self):
            return object(), SimpleNamespace(tools=[])

        async def stop(self):
            self.stop_calls += 1

    actor = OpenedActor()
    monkeypatch.setattr("core.mcp.client.ConnectionActor", lambda config, timeout: actor)
    manager = MCPClientManager(SimpleNamespace(), timeout=0.1)

    def fail_registration(*args, **kwargs):
        raise RuntimeError("注册失败")

    monkeypatch.setattr(manager, "_create_connection", fail_registration)
    with pytest.raises(RuntimeError, match="注册失败"):
        manager.connect(_config())
    assert actor.stop_calls == 1
    assert manager.shutdown() == ()
