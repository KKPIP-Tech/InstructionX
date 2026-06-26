"""DataProvider - 插件式桌面应用程序的数据中枢和 API 网关

提供数据持久化、缓存、插件管理、发布/订阅通信和资源管理功能。
"""

import copy
import os
import json
import threading
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
from enum import Enum

from core.interfaces.i_data_provider import IDataProvider, DataNamespace as IDataNamespace
from utils.logging_tools import LoggerManager, get_name

from .sqlite_backend import SQLiteBackend, SQLiteBackendError


class DataProviderError(Exception):
    """DataProvider 自定义异常类"""
    pass


class DataNamespace(Enum):
    """数据命名空间枚举"""
    PRIVATE = "private"  # 仅插件内部使用
    PUBLIC = "public"    # 允许其他插件访问


class DataProvider(IDataProvider):
    """
    数据提供者 - 单例模式

    负责插件数据的持久化、缓存、管理和通信。
    迁移后底层使用 SQLite，插件接口保持不变。
    """

    _instance: Optional['DataProvider'] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """单例模式实现"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, data_dir: Optional[str] = None, data_filename: str = "data.json"):
        """
        初始化 DataProvider

        Args:
            data_dir: 数据文件存储目录，默认为项目根目录下的 data 文件夹
            data_filename: 数据文件名，默认为 data.json
        """
        # 避免重复初始化
        if hasattr(self, '_initialized') and self._initialized:
            return

        # 后端选择开关：环境变量 INSTRUCTIONX_DATAPROVIDER_BACKEND=json 使用旧 JSON 后端
        self._backend_type = os.environ.get("INSTRUCTIONX_DATAPROVIDER_BACKEND", "sqlite").lower()
        self._use_json_backend = self._backend_type == "json"

        # 设置数据文件路径
        if data_dir is None:
            self.data_dir = Path(__file__).parent.parent.parent / "data"
        else:
            self.data_dir = Path(data_dir)

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.data_file = self.data_dir / data_filename
        self.temp_file = self.data_dir / f"{data_filename}.tmp"

        # 资源文件目录
        self.assets_dir = self.data_dir / "assets" / "plugins"
        self.assets_dir.mkdir(parents=True, exist_ok=True)

        # 线程安全锁
        self._file_lock = threading.RLock()
        self._subscription_lock = threading.Lock()  # 普通 Lock，更快暴露死锁

        # 内存缓存（全量字典缓存，用于 load_data / save_data / clear_cache 语义）
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_dirty = True

        # 订阅管理器: {(subscriber_id, target_plugin_id, target_key): callback}
        self._subscriptions: Dict[tuple, Callable] = {}

        # 日志管理器
        self._logger = LoggerManager()

        if not self._use_json_backend:
            self._backend = SQLiteBackend(data_dir, data_filename)
            try:
                self._backend.ensure_database()
            except SQLiteBackendError as e:
                raise DataProviderError(str(e)) from e

        # 标记初始化完成
        self._initialized = True

    # -------------------------------------------------------------------------
    # JSON 后端兼容方法（应急回退）
    # -------------------------------------------------------------------------

    def _json_read_from_disk(self) -> Dict[str, Any]:
        with self._file_lock:
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                raise DataProviderError(f"JSON 解析失败: {e}")
            except Exception as e:
                raise DataProviderError(f"读取数据文件失败: {e}")

    def _json_write_to_disk(self, data: Dict[str, Any]) -> None:
        with self._file_lock:
            try:
                with open(self.temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(self.temp_file, self.data_file)
            except Exception as e:
                raise DataProviderError(f"写入数据文件失败: {e}")

    def _json_ensure_data_file(self) -> None:
        if not self.data_file.exists():
            default_data = {"plugins": {}, "active_instances": {}}
            self._json_write_to_disk(default_data)

    def _json_load_data(self) -> Dict[str, Any]:
        if self._cache is None or self._cache_dirty:
            self._cache = self._json_read_from_disk()
            self._cache_dirty = False
        return self._cache.copy() if self._cache else {}

    def _json_save_data(self) -> None:
        if self._cache is None:
            raise DataProviderError("没有可保存的数据")
        self._json_write_to_disk(self._cache)
        self._cache_dirty = False

    # -------------------------------------------------------------------------
    # 公共方法：数据加载/保存/缓存
    # -------------------------------------------------------------------------

    def load_data(self, force_reload: bool = False) -> Dict[str, Any]:
        if self._use_json_backend:
            return self._json_load_data()

        if self._cache is None or force_reload or self._cache_dirty:
            with self._file_lock:
                try:
                    self._cache = self._backend.load_data()
                except SQLiteBackendError as e:
                    raise DataProviderError(str(e)) from e
                self._cache_dirty = False
        return copy.deepcopy(self._cache) if self._cache else {}

    def save_data(self) -> None:
        if self._use_json_backend:
            self._json_save_data()
            return

        if self._cache is None:
            raise DataProviderError("没有可保存的数据")
        with self._file_lock:
            try:
                self._backend.save_data(self._cache)
            except SQLiteBackendError as e:
                raise DataProviderError(str(e)) from e
            self._cache_dirty = False

    def clear_cache(self) -> None:
        with self._file_lock:
            self._cache = None
            self._cache_dirty = True
            if not self._use_json_backend:
                self._backend._value_cache.clear()


    # -------------------------------------------------------------------------
    # 公共方法：插件管理
    # -------------------------------------------------------------------------

    def _ensure_cache_loaded(self) -> None:
        """确保 _cache 已加载（用于保持与旧实现一致的行为）。"""
        if self._cache is None:
            self.load_data()

    def register_plugin(self, instance_id: str, plugin_type: str) -> None:
        if self._use_json_backend:
            data = self._json_load_data()
            if instance_id in data["plugins"]:
                raise DataProviderError(f"插件 {instance_id} 已存在")
            data["plugins"][instance_id] = {
                "type": plugin_type,
                "active": False,
                "private": {},
                "public": {},
            }
            self._cache = data
            self._json_save_data()
            return

        with self._file_lock:
            try:
                self._backend.register_plugin(instance_id, plugin_type)
            except SQLiteBackendError as e:
                raise DataProviderError(str(e)) from e
            self._ensure_cache_loaded()
            if instance_id not in self._cache["plugins"]:
                self._cache["plugins"][instance_id] = {
                    "type": plugin_type,
                    "active": False,
                    "private": {},
                    "public": {},
                }

    def unregister_plugin(self, instance_id: str) -> None:
        if self._use_json_backend:
            data = self._json_load_data()
            if instance_id not in data["plugins"]:
                raise DataProviderError(f"插件 {instance_id} 不存在")
            plugin_type = data["plugins"][instance_id]["type"]
            if plugin_type in data["active_instances"] and data["active_instances"][plugin_type] == instance_id:
                del data["active_instances"][plugin_type]
            del data["plugins"][instance_id]
            self._cache = data
            self._json_save_data()
            self._remove_subscriptions_for_plugin(instance_id)
            return

        with self._file_lock:
            try:
                self._backend.unregister_plugin(instance_id)
            except SQLiteBackendError as e:
                raise DataProviderError(str(e)) from e
            self._ensure_cache_loaded()
            self._cache["plugins"].pop(instance_id, None)
            for ptype, pid in list(self._cache["active_instances"].items()):
                if pid == instance_id:
                    del self._cache["active_instances"][ptype]
        # 释放 _file_lock 后再清理订阅
        self._remove_subscriptions_for_plugin(instance_id)

    def get_active_instance(self, plugin_type: str) -> Optional[str]:
        if self._use_json_backend:
            data = self._json_load_data()
            return data.get("active_instances", {}).get(plugin_type)

        with self._file_lock:
            try:
                return self._backend.get_active_instance(plugin_type)
            except SQLiteBackendError as e:
                raise DataProviderError(str(e)) from e

    def set_active_instance(self, instance_id: str) -> None:
        if self._use_json_backend:
            data = self._json_load_data()
            if instance_id not in data["plugins"]:
                raise DataProviderError(f"插件 {instance_id} 不存在")
            plugin_type = data["plugins"][instance_id]["type"]
            data["active_instances"][plugin_type] = instance_id
            data["plugins"][instance_id]["active"] = True
            for pid, plugin_data in data["plugins"].items():
                if plugin_data["type"] == plugin_type and pid != instance_id:
                    plugin_data["active"] = False
            self._cache = data
            self._json_save_data()
            return

        with self._file_lock:
            try:
                self._backend.set_active_instance(instance_id)
            except SQLiteBackendError as e:
                raise DataProviderError(str(e)) from e
            self._ensure_cache_loaded()
            plugin_type = self._backend.get_plugin_type(instance_id)
            if plugin_type is None:
                raise DataProviderError(f"插件 {instance_id} 不存在")
            self._cache["plugins"][instance_id]["active"] = True
            self._cache["active_instances"][plugin_type] = instance_id
            for pid, plugin_data in self._cache["plugins"].items():
                if plugin_data["type"] == plugin_type and pid != instance_id:
                    plugin_data["active"] = False

    # -------------------------------------------------------------------------
    # 公共方法：数据访问
    # -------------------------------------------------------------------------

    def get_plugin_data(self,
                       instance_id: str,
                       key: str,
                       namespace: DataNamespace = DataNamespace.PRIVATE,
                       default: Any = None) -> Any:
        namespace_str = namespace.value

        if self._use_json_backend:
            data = self._json_load_data()
            if instance_id not in data["plugins"]:
                raise DataProviderError(f"插件 {instance_id} 不存在")
            return data["plugins"][instance_id][namespace_str].get(key, default)

        with self._file_lock:
            if not self._backend.plugin_exists(instance_id):
                raise DataProviderError(f"插件 {instance_id} 不存在")
            try:
                return self._backend.get_plugin_data(instance_id, namespace_str, key, default)
            except SQLiteBackendError as e:
                raise DataProviderError(str(e)) from e

    def set_plugin_data(self,
                       instance_id: str,
                       key: str,
                       value: Any,
                       namespace: DataNamespace = DataNamespace.PRIVATE,
                       notify: bool = True) -> None:
        namespace_str = namespace.value

        if self._use_json_backend:
            data = self._json_load_data()
            if instance_id not in data["plugins"]:
                raise DataProviderError(f"插件 {instance_id} 不存在")
            old_value = data["plugins"][instance_id][namespace_str].get(key)
            data["plugins"][instance_id][namespace_str][key] = value
            self._cache = data
            self._json_save_data()
            if namespace == DataNamespace.PUBLIC and notify:
                self._notify_subscribers(instance_id, key, old_value, value)
            return

        with self._file_lock:
            if not self._backend.plugin_exists(instance_id):
                raise DataProviderError(f"插件 {instance_id} 不存在")
            # 获取旧值（用于回调）
            try:
                old_value = self._backend.get_plugin_data(instance_id, namespace_str, key)
            except SQLiteBackendError as e:
                raise DataProviderError(str(e)) from e
            # 写入新值
            try:
                self._backend.set_plugin_data(instance_id, namespace_str, key, value)
            except SQLiteBackendError as e:
                raise DataProviderError(str(e)) from e
            # 同步 _cache
            self._ensure_cache_loaded()
            self._cache["plugins"][instance_id][namespace_str][key] = copy.deepcopy(value)
            new_value = copy.deepcopy(value)

        # 释放 _file_lock 后再通知订阅者
        if namespace_str == DataNamespace.PUBLIC.value and notify:
            self._notify_subscribers(instance_id, key, old_value, new_value)

    def get_all_plugin_data(self,
                           instance_id: str,
                           namespace: DataNamespace = DataNamespace.PRIVATE) -> Dict[str, Any]:
        namespace_str = namespace.value

        if self._use_json_backend:
            data = self._json_load_data()
            if instance_id not in data["plugins"]:
                raise DataProviderError(f"插件 {instance_id} 不存在")
            return data["plugins"][instance_id][namespace_str].copy()

        with self._file_lock:
            if not self._backend.plugin_exists(instance_id):
                raise DataProviderError(f"插件 {instance_id} 不存在")
            try:
                return self._backend.get_all_plugin_data(instance_id, namespace_str)
            except SQLiteBackendError as e:
                raise DataProviderError(str(e)) from e


    # -------------------------------------------------------------------------
    # 公共方法：发布/订阅模式
    # -------------------------------------------------------------------------

    def subscribe(self,
                 subscriber_id: str,
                 target_plugin_id: str,
                 target_key: str,
                 callback: Callable[[str, str, Any, Any], None]) -> None:
        if self._use_json_backend:
            data = self._json_load_data()
            if target_plugin_id not in data["plugins"]:
                raise DataProviderError(f"目标插件 {target_plugin_id} 不存在")
            with self._subscription_lock:
                subscription_key = (subscriber_id, target_plugin_id, target_key)
                self._subscriptions[subscription_key] = callback
            return

        # 在 _file_lock 保护下仅验证目标插件存在，然后释放锁再注册订阅
        with self._file_lock:
            try:
                if not self._backend.plugin_exists(target_plugin_id):
                    raise DataProviderError(f"目标插件 {target_plugin_id} 不存在")
            except SQLiteBackendError as e:
                raise DataProviderError(str(e)) from e

        with self._subscription_lock:
            subscription_key = (subscriber_id, target_plugin_id, target_key)
            self._subscriptions[subscription_key] = callback

    def unsubscribe(self, subscriber_id: str, target_plugin_id: Optional[str] = None) -> None:
        with self._subscription_lock:
            if target_plugin_id is None:
                keys_to_remove = [k for k in self._subscriptions.keys() if k[0] == subscriber_id]
                for key in keys_to_remove:
                    del self._subscriptions[key]
            else:
                keys_to_remove = [k for k in self._subscriptions.keys()
                                 if k[0] == subscriber_id and k[1] == target_plugin_id]
                for key in keys_to_remove:
                    del self._subscriptions[key]

    def publish(self,
                publisher_id: str,
                key: str,
                value: Any,
                namespace: DataNamespace = DataNamespace.PUBLIC) -> None:
        self.set_plugin_data(publisher_id, key, value, namespace, notify=True)

    def _notify_subscribers(self,
                          publisher_id: str,
                          key: str,
                          old_value: Any,
                          new_value: Any) -> None:
        with self._subscription_lock:
            for (subscriber_id, target_plugin_id, target_key), callback in self._subscriptions.items():
                if target_plugin_id == publisher_id and target_key == key:
                    try:
                        callback(target_plugin_id, key, old_value, new_value)
                    except Exception as e:
                        self._logger.warning(get_name(), f'Subscriber {subscriber_id} callback failed: {e}')

    def _remove_subscriptions_for_plugin(self, instance_id: str) -> None:
        with self._subscription_lock:
            keys_to_remove = [k for k in self._subscriptions.keys() if k[0] == instance_id or k[1] == instance_id]
            for key in keys_to_remove:
                del self._subscriptions[key]

    # -------------------------------------------------------------------------
    # 公共方法：资源文件管理
    # -------------------------------------------------------------------------

    def save_asset(self,
                  plugin_id: str,
                  filename: str,
                  content: bytes) -> str:
        try:
            plugin_dir = self.assets_dir / plugin_id
            plugin_dir.mkdir(parents=True, exist_ok=True)
            file_path = plugin_dir / filename
            with open(file_path, 'wb') as f:
                f.write(content)
            relative_path = f"assets/plugins/{plugin_id}/{filename}"
            return relative_path
        except Exception as e:
            raise DataProviderError(f"保存资源文件失败: {e}")

    def get_asset_path(self, relative_path: str) -> str:
        try:
            normalized_path = Path(relative_path).as_posix()
            if ".." in normalized_path.split("/"):
                raise DataProviderError(f"无效的相对路径: {relative_path}")
            absolute_path = self.data_dir / relative_path
            if not absolute_path.exists():
                raise DataProviderError(f"资源文件不存在: {absolute_path}")
            return str(absolute_path.resolve())
        except Exception as e:
            if isinstance(e, DataProviderError):
                raise
            raise DataProviderError(f"获取资源路径失败: {e}")

    def load_asset(self, relative_path: str) -> bytes:
        try:
            absolute_path = self.get_asset_path(relative_path)
            with open(absolute_path, 'rb') as f:
                return f.read()
        except Exception as e:
            if isinstance(e, DataProviderError):
                raise
            raise DataProviderError(f"加载资源文件失败: {e}")

    def get_plugin_assets_dir(self, plugin_id: str) -> str:
        plugin_dir = self.assets_dir / plugin_id
        plugin_dir.mkdir(parents=True, exist_ok=True)
        return str(plugin_dir.resolve())

    # -------------------------------------------------------------------------
    # 公共方法：工具方法
    # -------------------------------------------------------------------------

    def get_all_plugins(self) -> Dict[str, Dict[str, Any]]:
        if self._use_json_backend:
            data = self._json_load_data()
            return data.get("plugins", {}).copy()

        with self._file_lock:
            try:
                return self._backend.get_all_plugins()
            except SQLiteBackendError as e:
                raise DataProviderError(str(e)) from e

    def get_plugin_info(self, instance_id: str) -> Optional[Dict[str, Any]]:
        if self._use_json_backend:
            data = self._json_load_data()
            return data.get("plugins", {}).get(instance_id)

        with self._file_lock:
            try:
                return self._backend.get_plugin_info(instance_id)
            except SQLiteBackendError as e:
                raise DataProviderError(str(e)) from e

    def reset_all_data(self) -> None:
        if self._use_json_backend:
            default_data = {"plugins": {}, "active_instances": {}}
            self._cache = default_data
            self._json_save_data()
            self.clear_cache()
            return

        with self._file_lock:
            try:
                self._backend.reset_all_data()
            except SQLiteBackendError as e:
                raise DataProviderError(str(e)) from e
        self.clear_cache()


# ==================== 演示代码 ====================

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
