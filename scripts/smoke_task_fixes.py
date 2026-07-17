"""
core/task 缺陷修复冒烟验证脚本

验证三项行为：
1. 同一插件注册两个不同 func 的定时任务工厂，后者不覆盖前者（重启恢复后各任务执行各自的函数）；
2. shutdown 在存在不响应 stop 的死循环任务时能在限时内返回；
3. cancel_task 后任务最终状态保持 CANCELLED（不被 worker 线程的完成状态覆盖）。

注意：场景 2 的死循环任务无法被 Python 强制杀死（线程池 worker 非 daemon），
脚本最后使用 os._exit(0) 退出以避免进程退出时挂起。
"""

import os
import sys
import tempfile
import time
from pathlib import Path

# 项目根目录加入 sys.path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.task.task_storage import TaskStorage

# 先用临时目录初始化 TaskStorage 单例，避免污染真实 data/tasks.json
_tmp_dir = tempfile.mkdtemp(prefix="task_smoke_")
TaskStorage(data_dir=_tmp_dir)

from core.task.background_task import BackgroundTaskManager
from core.task.task_model import TaskStatus


def scenario_1_multi_factory(manager: BackgroundTaskManager) -> bool:
    """场景 1：一插件多工厂互不覆盖，恢复后任务匹配各自的函数"""
    print("=== 场景 1: 一插件多工厂 ===")

    def func_alpha():
        return "alpha"

    def func_beta():
        return "beta"

    plugin = "smoke-plugin-1"

    # 同插件注册两个不同 func 的定时任务
    t1 = manager.register_scheduled_task(plugin, "task-alpha", func_alpha, interval=3600)
    t2 = manager.register_scheduled_task(plugin, "task-beta", func_beta, interval=3600)

    factory = manager._scheduled_task_factories[plugin]
    assert len(factory["funcs"]) == 2, f"工厂被覆盖: {list(factory['funcs'])}"

    # 模拟重启：清空运行时表，任务从存储恢复（func=None）
    manager._running_scheduled_tasks.clear()
    manager.register_scheduled_task_factory(plugin, func_alpha)
    manager.register_scheduled_task_factory(plugin, func_beta)

    restored_t1 = manager._running_scheduled_tasks.get(t1)
    restored_t2 = manager._running_scheduled_tasks.get(t2)
    assert restored_t1 is not None and restored_t2 is not None, "任务未被恢复"
    assert restored_t1.func is func_alpha, f"t1 恢复了错误的 func: {restored_t1.func}"
    assert restored_t2.func is func_beta, f"t2 恢复了错误的 func: {restored_t2.func}"

    print(f"  工厂数: {len(factory['funcs'])}（未被覆盖）")
    print(f"  t1 -> {restored_t1.func.__qualname__}, t2 -> {restored_t2.func.__qualname__}（精确匹配）")
    print("  通过")
    return True


def scenario_3_cancel_keeps_status(manager: BackgroundTaskManager) -> bool:
    """场景 3：cancel_task 后最终状态保持 CANCELLED"""
    print("=== 场景 3: 取消状态保持 ===")

    def slow_func():
        time.sleep(1.0)
        return "done"

    task_id = manager.register_async_task("smoke-plugin-3", "slow-task", slow_func)
    assert task_id is not None

    time.sleep(0.2)  # 等 worker 开始执行
    assert manager.cancel_task(task_id) is True

    time.sleep(1.5)  # 等 worker 执行完毕（试图 mark_completed）
    status = manager.get_task_status(task_id)
    assert status == TaskStatus.CANCELLED, f"取消状态被覆盖: {status}"

    print(f"  最终状态: {status.value}")
    print("  通过")
    return True


def scenario_2_shutdown_bounded() -> bool:
    """场景 2：死循环任务存在时 shutdown 限时返回"""
    print("=== 场景 2: shutdown 限时返回 ===")

    # 重置单例，模拟新的应用会话
    BackgroundTaskManager._instance = None
    BackgroundTaskManager._initialized = False
    manager = BackgroundTaskManager()

    def dead_loop():
        while True:
            time.sleep(0.1)  # 不响应任何停止信号

    task_id = manager.register_long_running_task(
        "smoke-plugin-2", "dead-loop-task", dead_loop,
        stop_callback=lambda: None,  # stop_callback 无效（任务循环不检查标志）
        auto_restart=False,
    )
    assert task_id is not None
    time.sleep(0.3)  # 确认任务进入死循环

    start = time.monotonic()
    manager.shutdown()
    elapsed = time.monotonic() - start

    limit = (manager.LONG_TASK_STOP_TIMEOUT + manager.EXECUTOR_SHUTDOWN_TIMEOUT + 5.0)
    print(f"  shutdown 总耗时: {elapsed:.2f}s（上限约 {limit:.0f}s）")
    assert elapsed < limit, f"shutdown 超时: {elapsed:.2f}s"

    # 存储记录未被删除，且标记为 stopped（重启后不自动恢复）
    stored = manager._storage.get_long_running_task(task_id)
    assert stored is not None, "长期任务记录在 shutdown 时被删除"
    assert stored.current_status == "stopped", f"状态应为 stopped: {stored.current_status}"
    print(f"  存储记录保留, current_status={stored.current_status}")
    print("  通过")
    return True


def main() -> None:
    manager = BackgroundTaskManager()

    scenario_1_multi_factory(manager)
    scenario_3_cancel_keeps_status(manager)
    scenario_2_shutdown_bounded()

    print("\n全部冒烟场景通过")
    sys.stdout.flush()
    # 场景 2 的死循环 worker 线程无法被杀死，跳过解释器的线程 join 直接退出
    os._exit(0)


if __name__ == "__main__":
    main()
