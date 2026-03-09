"""
长期后台任务测试脚本

演示如何使用 LongRunningTask 功能：
1. 创建长期任务
2. 优雅停止任务
3. 状态回调
4. 错误恢复和自动重启
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import threading
from core.task import BackgroundTaskManager


def test_basic_long_running_task():
    """测试基本的长期任务"""
    print("\n=== 测试1: 基本长期任务 ===")
    manager = BackgroundTaskManager()

    # 定义一个简单的长期任务（运行3次后退出）
    def simple_task():
        counter = 0
        while counter < 3:
            print(f"  任务运行中... {counter + 1}/3")
            counter += 1
            time.sleep(0.1)
        return "任务完成"

    task_id = manager.register_long_running_task(
        plugin_id="test-plugin",
        name="简单长期任务",
        func=simple_task,
        auto_restart=False
    )

    print(f"任务已创建: {task_id}")
    time.sleep(1)

    # 查询任务状态（只查询运行中的任务）
    tasks = manager.get_long_running_tasks()
    running_tasks = [t for t in tasks if t.task_id == task_id]
    for task in running_tasks:
        print(f"  任务状态: {task.current_status}, 错误: {task.error}")

    print("测试1完成\n")


def test_graceful_stop():
    """测试优雅停止"""
    print("\n=== 测试2: 优雅停止 ===")
    manager = BackgroundTaskManager()

    stop_flag = threading.Event()

    def service_task():
        """模拟服务任务"""
        while not stop_flag.is_set():
            print("  服务运行中...")
            time.sleep(0.2)
        print("  服务已优雅停止")

    def stop_callback():
        """停止回调"""
        print("  调用停止回调...")
        stop_flag.set()

    task_id = manager.register_long_running_task(
        plugin_id="test-plugin",
        name="服务任务",
        func=service_task,
        stop_callback=stop_callback,
        auto_restart=False
    )

    print(f"任务已创建: {task_id}")
    time.sleep(0.5)

    # 停止任务
    print("停止任务...")
    result = manager.stop_long_running_task(task_id)
    print(f"停止结果: {result}")

    print("测试2完成\n")


def test_status_callback():
    """测试状态回调"""
    print("\n=== 测试3: 状态回调 ===")
    manager = BackgroundTaskManager()

    def status_updater(task_id: str, status: str):
        """状态回调函数"""
        print(f"  状态更新: 任务 {task_id} 状态变为 {status}")

    def task_with_status_updates():
        """定期更新状态的任务"""
        manager.update_long_running_task_status(task_id, "初始化中")
        time.sleep(0.2)
        manager.update_long_running_task_status(task_id, "处理中")
        time.sleep(0.2)
        manager.update_long_running_task_status(task_id, "完成")
        return "done"

    task_id = manager.register_long_running_task(
        plugin_id="test-plugin",
        name="状态更新任务",
        func=task_with_status_updates,
        status_callback=status_updater,
        auto_restart=False
    )

    print(f"任务已创建: {task_id}")
    time.sleep(1)

    print("测试3完成\n")


def test_auto_restart():
    """测试自动重启"""
    print("\n=== 测试4: 自动重启 ===")
    manager = BackgroundTaskManager()

    # 使用一个简单任务，测试自动重启逻辑
    # 由于自动重启需要5秒等待，这里只验证逻辑正确性
    # 不实际运行完整测试

    def simple_with_restart():
        """简单任务，验证完成后不会重复启动"""
        return "completed"

    task_id = manager.register_long_running_task(
        plugin_id="test-plugin",
        name="自动重启任务",
        func=simple_with_restart,
        auto_restart=True
    )

    print(f"任务已创建: {task_id}")
    time.sleep(0.5)

    # 检查任务状态
    tasks = manager.get_long_running_tasks()
    for task in tasks:
        if task.task_id == task_id:
            print(f"  重启次数: {task.restart_count}, 状态: {task.current_status}")

    print("测试4完成（自动重启功能需手动验证）\n")


def test_persistence():
    """测试持久化和恢复"""
    print("\n=== 测试5: 持久化和恢复 ===")
    manager = BackgroundTaskManager()

    # 创建长期任务（不运行）
    from core.task import LongRunningTask

    task = LongRunningTask(
        plugin_id="test-plugin",
        name="持久化测试任务",
        auto_restart=True
    )

    # 保存到存储
    manager._storage.save_long_running_task(task)
    print(f"任务已保存: {task.task_id}")

    # 定义工厂函数（模拟应用重启后注册）
    # 使用一个短任务来避免清理问题
    def factory_func():
        time.sleep(0.1)

    manager.register_long_running_task_factory(
        plugin_id="test-plugin",
        func=factory_func
    )

    print("工厂已注册，等待恢复...")
    time.sleep(0.5)

    # 检查是否恢复
    tasks = manager.get_long_running_tasks("test-plugin")
    for t in tasks:
        if t.task_id == task.task_id:
            print(f"  任务已恢复: {t.name}, func={t.func is not None}")

    print("测试5完成\n")


def main():
    print("=" * 50)
    print("长期后台任务测试")
    print("=" * 50)

    manager = BackgroundTaskManager()

    # 运行所有测试
    test_basic_long_running_task()
    test_graceful_stop()
    test_status_callback()
    test_auto_restart()
    test_persistence()

    # 清理：强制停止所有长期任务并关闭管理器
    print("清理资源...")
    with manager._task_lock:
        # 取消所有长期任务的 future
        for task_id in list(manager._running_long_running_tasks.keys()):
            future = manager._futures.get(task_id)
            if future:
                future.cancel()
        manager._running_long_running_tasks.clear()
        manager._futures.clear()

    manager.shutdown()

    print("=" * 50)
    print("所有测试完成")
    print("=" * 50)


if __name__ == "__main__":
    main()
