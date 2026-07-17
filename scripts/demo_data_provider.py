#!/usr/bin/env python3
"""DataProvider 演示脚本

本脚本由 core/data/data_provider.py 的 `if __name__ == "__main__":` 演示代码迁移而来，
用于演示 DataProvider 的插件注册、数据读写、发布/订阅、资源文件管理等功能。

运行方式（项目根目录下）:
    .venv\\Scripts\\python.exe scripts\\demo_data_provider.py
"""

import sys
from pathlib import Path
from typing import Any

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.data.data_provider import DataProvider, DataNamespace
from utils.logging_tools import LoggerManager, get_name


def demo_callback(target_plugin_id: str, key: str, old_value: Any, new_value: Any):
    """演示用的回调函数"""
    logger = LoggerManager()
    logger.info(get_name(), f"通知: 插件 '{target_plugin_id}' 的 '{key}' 从 '{old_value}' 变更为 '{new_value}'")


if __name__ == "__main__":
    logger = LoggerManager()
    logger.info(get_name(), "=" * 60)
    logger.info(get_name(), "DataProvider 演示程序")
    logger.info(get_name(), "=" * 60)

    # 创建 DataProvider 实例（单例）
    provider = DataProvider()

    # 重置数据以获得干净的演示环境
    provider.reset_all_data()
    logger.info(get_name(), "数据已重置")

    # 注册插件 A（VideoEditor 类型）
    plugin_a_id = "video-editor-001"
    provider.register_plugin(plugin_a_id, "VideoEditor")
    logger.info(get_name(), f"已注册插件 A: {plugin_a_id} (类型: VideoEditor)")

    # 注册插件 B（Exporter 类型）
    plugin_b_id = "exporter-001"
    provider.register_plugin(plugin_b_id, "Exporter")
    logger.info(get_name(), f"已注册插件 B: {plugin_b_id} (类型: Exporter)")

    # 设置插件 A 为活跃实例
    provider.set_active_instance(plugin_a_id)
    logger.info(get_name(), "已将插件 A 设为 VideoEditor 类型的活跃实例")

    # 插件 A 存储一些私有数据
    provider.set_plugin_data(plugin_a_id, "project_name", "My Awesome Project", DataNamespace.PRIVATE)
    provider.set_plugin_data(plugin_a_id, "resolution", "1920x1080", DataNamespace.PRIVATE)
    logger.info(get_name(), "插件 A 存储了私有数据")

    # 插件 A 存储一些公共数据
    provider.set_plugin_data(plugin_a_id, "video_duration", 120, DataNamespace.PUBLIC)
    provider.set_plugin_data(plugin_a_id, "frame_rate", 30, DataNamespace.PUBLIC)
    logger.info(get_name(), "插件 A 存储了公共数据")

    # 插件 B 订阅插件 A 的公共数据变化
    provider.subscribe(plugin_b_id, plugin_a_id, "video_duration", demo_callback)
    provider.subscribe(plugin_b_id, plugin_a_id, "frame_rate", demo_callback)
    logger.info(get_name(), "插件 B 订阅了插件 A 的 'video_duration' 和 'frame_rate' 变化")

    # 模拟数据变更
    logger.info(get_name(), "-" * 60)
    logger.info(get_name(), "模拟数据变更...")
    logger.info(get_name(), "-" * 60)

    provider.set_plugin_data(plugin_a_id, "video_duration", 150, DataNamespace.PUBLIC)
    provider.set_plugin_data(plugin_a_id, "frame_rate", 60, DataNamespace.PUBLIC)

    # 查询数据
    logger.info(get_name(), "-" * 60)
    logger.info(get_name(), "查询数据...")
    logger.info(get_name(), "-" * 60)

    duration = provider.get_plugin_data(plugin_a_id, "video_duration", DataNamespace.PUBLIC)
    frame_rate = provider.get_plugin_data(plugin_a_id, "frame_rate", DataNamespace.PUBLIC)
    logger.info(get_name(), f"插件 A 的公共数据: video_duration={duration}, frame_rate={frame_rate}")

    # 保存资源文件
    logger.info(get_name(), "-" * 60)
    logger.info(get_name(), "保存资源文件...")
    logger.info(get_name(), "-" * 60)

    test_content = b"This is a test video thumbnail data."
    relative_path = provider.save_asset(plugin_a_id, "thumbnail.png", test_content)
    logger.info(get_name(), f"已保存资源文件: {relative_path}")

    # 获取资源路径
    absolute_path = provider.get_asset_path(relative_path)
    logger.info(get_name(), f"资源文件绝对路径: {absolute_path}")

    # 加载资源文件
    loaded_content = provider.load_asset(relative_path)
    logger.info(get_name(), f"已加载资源文件，内容: {loaded_content.decode()}")

    # 获取所有插件信息
    logger.info(get_name(), "-" * 60)
    logger.info(get_name(), "所有插件信息:")
    logger.info(get_name(), "-" * 60)

    all_plugins = provider.get_all_plugins()
    for pid, info in all_plugins.items():
        logger.info(get_name(), f"插件 ID: {pid}, 类型: {info['type']}, 活跃: {info['active']}, 公共数据: {info['public']}, 私有数据: {info['private']}")

    # 取消订阅
    logger.info(get_name(), "-" * 60)
    logger.info(get_name(), "取消订阅...")
    logger.info(get_name(), "-" * 60)

    provider.unsubscribe(plugin_b_id)
    logger.info(get_name(), "已取消插件 B 的所有订阅")

    # 再次变更数据（不会触发通知）
    logger.info(get_name(), "模拟再次变更数据（已取消订阅，不应触发通知）...")
    provider.set_plugin_data(plugin_a_id, "video_duration", 180, DataNamespace.PUBLIC)
    logger.info(get_name(), "没有触发通知，符合预期")

    logger.info(get_name(), "=" * 60)
    logger.info(get_name(), "演示完成！")
    logger.info(get_name(), "=" * 60)
