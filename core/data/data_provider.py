"""DataProvider - 插件式桌面应用程序的数据中枢和 API 网关

提供数据持久化、缓存、插件管理、发布/订阅通信和资源管理功能。
"""

import copy
import os
import json
import threading
from pathlib import Path, PurePath
from typing import Dict, Any, Optional, Callable, List

# DataNamespace 单一来源在接口层，此处 re-export 以保持
# `from core.data.data_provider import DataNamespace` 导入路径可用
from core.interfaces.i_data_provider import IDataProvider, DataNamespace
from utils.logging_tools import LoggerManager, get_name

from .sqlite_backend import SQLiteBackend, SQLiteBackendError


class DataProviderError(Exception):
    """DataProvider 自定义异常类"""
    pass


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
            # 单例已初始化：后续传入的不同参数不会生效，记录 debug 日志提示
            if data_dir is not None and Path(data_dir) != self.data_dir:
                self._logger.debug(
                    get_name(),
                    f"DataProvider 单例已初始化（data_dir={self.data_dir}），"
                    f"忽略本次传入的 data_dir 参数: {data_dir}"
                )
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
            # 数据文件不存在时创建默认空结构（应急 JSON 后端首次读取）
            self._json_ensure_data_file()
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
        # 返回深拷贝（与 SQLite 路径一致），避免调用方修改嵌套结构污染缓存；
        # 因此 register/set 等写路径必须将修改后的 data 重新赋值给 self._cache 才会生效
        return copy.deepcopy(self._cache) if self._cache else {}

    def _json_save_data(self) -> None:
        if self._cache is None:
            raise DataProviderError("没有可保存的数据")
        self._json_write_to_disk(self._cache)
        self._cache_dirty = False

    # -------------------------------------------------------------------------
    # 公共方法：数据加载/保存/缓存
    # -------------------------------------------------------------------------

    def load_data(self, force_reload: bool = False) -> Dict[str, Any]:
        """加载全量数据（含内存缓存与深拷贝返回）

        Args:
            force_reload: 为 True 时忽略缓存，强制从持久层重新加载

        Returns:
            完整数据字典（{"plugins": ..., "active_instances": ...} 的深拷贝），
            调用方修改返回值不会影响内部缓存

        Raises:
            DataProviderError: 底层持久化读取失败时抛出
        """
        if self._use_json_backend:
            return self._json_load_data()

        # 缓存命中判断与 deepcopy 都在锁内完成，避免并发 set_plugin_data
        # 修改嵌套结构时 deepcopy 抛出 RuntimeError
        with self._file_lock:
            if self._cache is None or force_reload or self._cache_dirty:
                try:
                    self._cache = self._backend.load_data()
                except SQLiteBackendError as e:
                    raise DataProviderError(str(e)) from e
                self._cache_dirty = False
            return copy.deepcopy(self._cache) if self._cache else {}

    def save_data(self) -> None:
        """将当前内存缓存全量写回持久层

        Raises:
            DataProviderError: 缓存为空（无可保存数据）或底层写入失败时抛出
        """
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
        """清空内存缓存与后端内部缓存，下次读取将从持久层重新加载"""
        with self._file_lock:
            self._cache = None
            self._cache_dirty = True
            if not self._use_json_backend:
                self._backend.clear_caches()


    # -------------------------------------------------------------------------
    # 公共方法：插件管理
    # -------------------------------------------------------------------------

    def _ensure_cache_loaded(self) -> None:
        """确保 _cache 已加载（用于保持与旧实现一致的行为）。"""
        if self._cache is None:
            self.load_data()

    def register_plugin(self, instance_id: str, plugin_type: str) -> None:
        """注册插件实例并初始化其数据结构

        Args:
            instance_id: 插件实例唯一标识（UUID）
            plugin_type: 插件类型标识（同一类型只能有一个活跃实例）

        Raises:
            DataProviderError: 插件已存在或底层写入失败时抛出
        """
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
        """注销插件实例，删除其全部数据并清理相关订阅

        Args:
            instance_id: 插件实例唯一标识

        Raises:
            DataProviderError: 插件不存在或底层删除失败时抛出
        """
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
        """查询指定插件类型的活跃实例

        Args:
            plugin_type: 插件类型标识

        Returns:
            活跃实例的 instance_id，无活跃实例时返回 None

        Raises:
            DataProviderError: 底层查询失败时抛出
        """
        if self._use_json_backend:
            data = self._json_load_data()
            return data.get("active_instances", {}).get(plugin_type)

        with self._file_lock:
            try:
                return self._backend.get_active_instance(plugin_type)
            except SQLiteBackendError as e:
                raise DataProviderError(str(e)) from e

    def set_active_instance(self, instance_id: str) -> None:
        """将指定插件实例设置为其类型的活跃实例（同类型其他实例自动置为非活跃）

        Args:
            instance_id: 插件实例唯一标识

        Raises:
            DataProviderError: 插件不存在或底层写入失败时抛出
        """
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
        """读取插件在指定命名空间下的单个数据项

        Args:
            instance_id: 插件实例唯一标识
            key: 数据键名
            namespace: 命名空间（PRIVATE 私有 / PUBLIC 公开），默认 PRIVATE
            default: 键不存在时返回的默认值，默认 None

        Returns:
            键对应的值，不存在时返回 default

        Raises:
            DataProviderError: 插件不存在或底层读取失败时抛出
        """
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
        """写入插件在指定命名空间下的单个数据项

        写入 PUBLIC 命名空间且 notify 为 True 时，会异步通知所有订阅者。

        Args:
            instance_id: 插件实例唯一标识
            key: 数据键名
            value: 要写入的值（必须可 JSON 序列化）
            namespace: 命名空间（PRIVATE 私有 / PUBLIC 公开），默认 PRIVATE
            notify: 写入 PUBLIC 数据时是否通知订阅者，默认 True

        Raises:
            DataProviderError: 插件不存在、值不可序列化或底层写入失败时抛出
        """
        namespace_str = namespace.value

        if self._use_json_backend:
            data = self._json_load_data()
            if instance_id not in data["plugins"]:
                raise DataProviderError(f"插件 {instance_id} 不存在")
            old_value = data["plugins"][instance_id][namespace_str].get(key)
            data["plugins"][instance_id][namespace_str][key] = value
            self._cache = data
            self._json_save_data()
            # 与 SQLite 路径统一使用 .value 比较
            if namespace_str == DataNamespace.PUBLIC.value and notify:
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
        """读取插件在指定命名空间下的全部数据

        Args:
            instance_id: 插件实例唯一标识
            namespace: 命名空间（PRIVATE 私有 / PUBLIC 公开），默认 PRIVATE

        Returns:
            该命名空间下的键值字典副本

        Raises:
            DataProviderError: 插件不存在或底层读取失败时抛出
        """
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
        """订阅目标插件公开数据的变化通知

        Args:
            subscriber_id: 订阅方插件实例标识
            target_plugin_id: 被订阅的目标插件实例标识
            target_key: 被订阅的数据键名
            callback: 变化回调，签名为 (publisher_id, key, old_value, new_value) -> None

        Raises:
            DataProviderError: 目标插件不存在时抛出
        """
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
        """取消订阅

        Args:
            subscriber_id: 订阅方插件实例标识
            target_plugin_id: 可选，仅取消对该目标插件的订阅；为 None 时取消该订阅方的全部订阅
        """
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
        """发布数据并通知订阅者（等价于 set_plugin_data(..., notify=True)）

        Args:
            publisher_id: 发布方插件实例标识
            key: 数据键名
            value: 要发布的值（必须可 JSON 序列化）
            namespace: 命名空间，默认 PUBLIC（只有 PUBLIC 数据会触发订阅通知）

        Raises:
            DataProviderError: 插件不存在、值不可序列化或底层写入失败时抛出
        """
        self.set_plugin_data(publisher_id, key, value, namespace, notify=True)

    def _notify_subscribers(self,
                          publisher_id: str,
                          key: str,
                          old_value: Any,
                          new_value: Any) -> None:
        # 锁内快照匹配的回调列表后释放锁，锁外逐个执行回调，
        # 避免回调中 unsubscribe/subscribe/再次 publish 时同线程死锁
        with self._subscription_lock:
            callbacks = [
                (subscriber_id, callback)
                for (subscriber_id, target_plugin_id, target_key), callback in self._subscriptions.items()
                if target_plugin_id == publisher_id and target_key == key
            ]
        for subscriber_id, callback in callbacks:
            try:
                callback(publisher_id, key, old_value, new_value)
            except Exception as e:
                # 单个回调异常不中断其他回调
                self._logger.warning(get_name(), f'Subscriber {subscriber_id} callback failed: {e}')

    def _remove_subscriptions_for_plugin(self, instance_id: str) -> None:
        with self._subscription_lock:
            keys_to_remove = [k for k in self._subscriptions.keys() if k[0] == instance_id or k[1] == instance_id]
            for key in keys_to_remove:
                del self._subscriptions[key]

    # -------------------------------------------------------------------------
    # 公共方法：资源文件管理
    # -------------------------------------------------------------------------

    @staticmethod
    def _validate_asset_component(part: str, kind: str) -> None:
        """校验资源路径片段（plugin_id / filename），与 get_asset_path 读侧校验对称。"""
        if not part:
            raise DataProviderError(f"无效的{kind}: 不能为空")
        pure = PurePath(part)
        if pure.is_absolute() or ".." in pure.parts:
            raise DataProviderError(f"无效的{kind}: {part}")

    def save_asset(self,
                  plugin_id: str,
                  filename: str,
                  content: bytes) -> str:
        """保存插件资源文件（写侧路径消毒：拒绝空名、绝对路径与 ".." 穿越）

        Args:
            plugin_id: 插件实例唯一标识
            filename: 资源文件名（相对路径）
            content: 文件二进制内容

        Returns:
            相对于数据目录的资源路径（如 "assets/plugins/{plugin_id}/{filename}"）

        Raises:
            DataProviderError: 路径非法或写入失败时抛出
        """
        try:
            # 写侧路径消毒：禁止空名、绝对路径与 ".." 路径穿越
            self._validate_asset_component(plugin_id, "插件 ID")
            self._validate_asset_component(filename, "资源文件名")
            plugin_dir = (self.assets_dir / plugin_id).resolve()
            plugin_dir.mkdir(parents=True, exist_ok=True)
            file_path = (plugin_dir / filename).resolve()
            # 规范化后必须仍位于插件资产目录内（防御分隔符/符号链接绕过）
            if plugin_dir != file_path.parent and plugin_dir not in file_path.parents:
                raise DataProviderError(f"无效的资源文件名: {filename}")
            with open(file_path, 'wb') as f:
                f.write(content)
            relative_path = f"assets/plugins/{plugin_id}/{filename}"
            return relative_path
        except Exception as e:
            if isinstance(e, DataProviderError):
                raise
            raise DataProviderError(f"保存资源文件失败: {e}")

    def get_asset_path(self, relative_path: str) -> str:
        """获取资源文件的绝对路径（读侧路径消毒，与 save_asset 写侧对齐）

        Args:
            relative_path: 相对于数据目录的资源路径（通常为 save_asset 的返回值）

        Returns:
            资源文件的绝对路径字符串

        Raises:
            DataProviderError: 路径非法（绝对路径/".." 穿越）或文件不存在时抛出
        """
        try:
            # 读侧路径消毒：与写侧 save_asset 对齐，拒绝绝对路径与 ".." 路径穿越，
            # 防止 Path(data_dir) / "C:/abs" 形式的目录逃逸读取任意文件
            self._validate_asset_component(relative_path, "相对路径")
            normalized_path = Path(relative_path).as_posix()
            if ".." in normalized_path.split("/"):
                raise DataProviderError(f"无效的相对路径: {relative_path}")
            absolute_path = self.data_dir / relative_path
            # 规范化后必须仍位于数据目录内（防御根相对路径/符号链接绕过，
            # 与 save_asset 写侧的目录包含校验对称）
            resolved_root = self.data_dir.resolve()
            resolved_path = absolute_path.resolve()
            if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
                raise DataProviderError(f"无效的相对路径: {relative_path}")
            if not resolved_path.exists():
                raise DataProviderError(f"资源文件不存在: {resolved_path}")
            return str(resolved_path)
        except Exception as e:
            if isinstance(e, DataProviderError):
                raise
            raise DataProviderError(f"获取资源路径失败: {e}")

    def load_asset(self, relative_path: str) -> bytes:
        """读取资源文件的二进制内容

        Args:
            relative_path: 相对于数据目录的资源路径（通常为 save_asset 的返回值）

        Returns:
            文件二进制内容

        Raises:
            DataProviderError: 路径非法、文件不存在或读取失败时抛出
        """
        try:
            absolute_path = self.get_asset_path(relative_path)
            with open(absolute_path, 'rb') as f:
                return f.read()
        except Exception as e:
            if isinstance(e, DataProviderError):
                raise
            raise DataProviderError(f"加载资源文件失败: {e}")

    def get_plugin_assets_dir(self, plugin_id: str) -> str:
        """获取（并创建）插件资源目录

        Args:
            plugin_id: 插件实例唯一标识

        Returns:
            插件资源目录的绝对路径字符串
        """
        plugin_dir = self.assets_dir / plugin_id
        plugin_dir.mkdir(parents=True, exist_ok=True)
        return str(plugin_dir.resolve())

    # -------------------------------------------------------------------------
    # 公共方法：工具方法
    # -------------------------------------------------------------------------

    def get_all_plugins(self) -> Dict[str, Dict[str, Any]]:
        """获取所有已注册插件的完整数据

        Returns:
            以 instance_id 为键的插件信息字典（含 type/active/private/public）

        Raises:
            DataProviderError: 底层读取失败时抛出
        """
        if self._use_json_backend:
            data = self._json_load_data()
            return data.get("plugins", {}).copy()

        with self._file_lock:
            try:
                return self._backend.get_all_plugins()
            except SQLiteBackendError as e:
                raise DataProviderError(str(e)) from e

    def get_plugin_info(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """获取单个插件的完整数据

        Args:
            instance_id: 插件实例唯一标识

        Returns:
            插件信息字典（含 type/active/private/public），不存在时返回 None

        Raises:
            DataProviderError: 底层读取失败时抛出
        """
        if self._use_json_backend:
            data = self._json_load_data()
            return data.get("plugins", {}).get(instance_id)

        with self._file_lock:
            try:
                return self._backend.get_plugin_info(instance_id)
            except SQLiteBackendError as e:
                raise DataProviderError(str(e)) from e

    def reset_all_data(self) -> None:
        """重置全部数据为空初始状态（清空所有插件数据与活跃实例记录）

        Raises:
            DataProviderError: 底层写入失败时抛出
        """
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
