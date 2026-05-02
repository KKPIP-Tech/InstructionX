"""
DataProvider - 插件式桌面应用程序的数据中枢和 API 网关

提供数据持久化、缓存、插件管理、发布/订阅通信和资源管理功能。
"""

import os
import json
import threading
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
from enum import Enum

from core.interfaces.i_data_provider import IDataProvider, DataNamespace as IDataNamespace
from utils.logging_tools import LoggerManager, get_name


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
        
        # 设置数据文件路径
        if data_dir is None:
            # 默认使用项目根目录下的 data 文件夹
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
        self._subscription_lock = threading.RLock()
        
        # 内存缓存
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_dirty = True
        
        # 订阅管理器: {(subscriber_id, target_plugin_id, target_key): callback}
        self._subscriptions: Dict[tuple, Callable] = {}

        # 日志管理器
        self._logger = LoggerManager()

        # 标记初始化完成
        self._initialized = True
        
        # 初始化数据文件（如果不存在）
        self._ensure_data_file()
    
    def _ensure_data_file(self) -> None:
        """确保数据文件存在，如果不存在则创建默认结构"""
        if not self.data_file.exists():
            default_data = {
                "plugins": {},
                "active_instances": {}
            }
            self._write_to_disk(default_data)
    
    def _read_from_disk(self) -> Dict[str, Any]:
        """
        从磁盘读取数据
        
        Returns:
            数据字典
            
        Raises:
            DataProviderError: 读取失败时抛出
        """
        with self._file_lock:
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                raise DataProviderError(f"JSON 解析失败: {e}")
            except Exception as e:
                raise DataProviderError(f"读取数据文件失败: {e}")
    
    def _write_to_disk(self, data: Dict[str, Any]) -> None:
        """
        原子写入数据到磁盘
        
        使用临时文件 + 原子重命名机制，防止程序崩溃时数据损坏
        
        Args:
            data: 要写入的数据字典
            
        Raises:
            DataProviderError: 写入失败时抛出
        """
        with self._file_lock:
            try:
                # 写入临时文件
                with open(self.temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                # 原子重命名（在 Windows 和 Unix 系统上都是原子操作）
                os.replace(self.temp_file, self.data_file)
                
            except Exception as e:
                raise DataProviderError(f"写入数据文件失败: {e}")
    
    def load_data(self, force_reload: bool = False) -> Dict[str, Any]:
        """
        从磁盘加载数据到缓存
        
        Args:
            force_reload: 是否强制重新加载，忽略缓存
            
        Returns:
            数据字典
        """
        if self._cache is None or force_reload or self._cache_dirty:
            self._cache = self._read_from_disk()
            self._cache_dirty = False
        return self._cache.copy() if self._cache else {}
    
    def save_data(self) -> None:
        """
        将当前缓存数据保存到磁盘
        
        Raises:
            DataProviderError: 保存失败时抛出
        """
        if self._cache is None:
            raise DataProviderError("没有可保存的数据")
        
        self._write_to_disk(self._cache)
        self._cache_dirty = False
    
    def clear_cache(self) -> None:
        """清除缓存，下次读取时将重新从磁盘加载"""
        with self._file_lock:
            self._cache = None
            self._cache_dirty = True
    
    # ==================== 插件管理 ====================
    
    def register_plugin(self, instance_id: str, plugin_type: str) -> None:
        """
        注册插件实例
        
        Args:
            instance_id: 插件实例的唯一标识符
            plugin_type: 插件类型
            
        Raises:
            DataProviderError: 插件已存在时抛出
        """
        data = self.load_data()
        
        if instance_id in data["plugins"]:
            raise DataProviderError(f"插件 {instance_id} 已存在")
        
        data["plugins"][instance_id] = {
            "type": plugin_type,
            "active": False,
            "private": {},
            "public": {}
        }
        
        self._cache = data
        self.save_data()
    
    def unregister_plugin(self, instance_id: str) -> None:
        """
        注销插件实例
        
        Args:
            instance_id: 插件实例的唯一标识符
            
        Raises:
            DataProviderError: 插件不存在时抛出
        """
        data = self.load_data()
        
        if instance_id not in data["plugins"]:
            raise DataProviderError(f"插件 {instance_id} 不存在")
        
        # 获取插件类型
        plugin_type = data["plugins"][instance_id]["type"]
        
        # 从活跃实例中移除
        if plugin_type in data["active_instances"]:
            if data["active_instances"][plugin_type] == instance_id:
                del data["active_instances"][plugin_type]
        
        # 移除插件数据
        del data["plugins"][instance_id]
        
        # 移除所有相关订阅
        self._remove_subscriptions_for_plugin(instance_id)
        
        self._cache = data
        self.save_data()
    
    def get_active_instance(self, plugin_type: str) -> Optional[str]:
        """
        根据插件类型获取当前活跃的实例 ID
        
        Args:
            plugin_type: 插件类型
            
        Returns:
            活跃实例 ID，如果不存在则返回 None
        """
        data = self.load_data()
        return data.get("active_instances", {}).get(plugin_type)
    
    def set_active_instance(self, instance_id: str) -> None:
        """
        将某实例标记为当前活跃实例
        
        Args:
            instance_id: 插件实例的唯一标识符
            
        Raises:
            DataProviderError: 插件不存在时抛出
        """
        data = self.load_data()
        
        if instance_id not in data["plugins"]:
            raise DataProviderError(f"插件 {instance_id} 不存在")
        
        plugin_type = data["plugins"][instance_id]["type"]
        
        # 更新活跃实例
        data["active_instances"][plugin_type] = instance_id
        
        # 更新插件的 active 标志
        data["plugins"][instance_id]["active"] = True
        
        # 将同类型的其他插件标记为非活跃
        for pid, plugin_data in data["plugins"].items():
            if plugin_data["type"] == plugin_type and pid != instance_id:
                plugin_data["active"] = False
        
        self._cache = data
        self.save_data()
    
    # ==================== 数据访问 ====================
    
    def get_plugin_data(self, 
                       instance_id: str, 
                       key: str, 
                       namespace: DataNamespace = DataNamespace.PRIVATE,
                       default: Any = None) -> Any:
        """
        获取插件数据
        
        Args:
            instance_id: 插件实例 ID
            key: 数据键
            namespace: 命名空间（private 或 public）
            default: 默认值，如果键不存在则返回该值
            
        Returns:
            数据值
            
        Raises:
            DataProviderError: 插件不存在时抛出
        """
        data = self.load_data()
        
        if instance_id not in data["plugins"]:
            raise DataProviderError(f"插件 {instance_id} 不存在")
        
        namespace_str = namespace.value
        return data["plugins"][instance_id][namespace_str].get(key, default)
    
    def set_plugin_data(self, 
                       instance_id: str, 
                       key: str, 
                       value: Any,
                       namespace: DataNamespace = DataNamespace.PRIVATE,
                       notify: bool = True) -> None:
        """
        设置插件数据
        
        Args:
            instance_id: 插件实例 ID
            key: 数据键
            value: 数据值
            namespace: 命名空间（private 或 public）
            notify: 是否通知订阅者（仅对 public 数据有效）
            
        Raises:
            DataProviderError: 插件不存在时抛出
        """
        data = self.load_data()
        
        if instance_id not in data["plugins"]:
            raise DataProviderError(f"插件 {instance_id} 不存在")
        
        namespace_str = namespace.value
        old_value = data["plugins"][instance_id][namespace_str].get(key)
        data["plugins"][instance_id][namespace_str][key] = value
        
        self._cache = data
        self.save_data()
        
        # 如果是 public 数据且需要通知
        if namespace == DataNamespace.PUBLIC and notify:
            self._notify_subscribers(instance_id, key, old_value, value)
    
    def get_all_plugin_data(self, 
                           instance_id: str, 
                           namespace: DataNamespace = DataNamespace.PRIVATE) -> Dict[str, Any]:
        """
        获取插件的所有数据（指定命名空间）
        
        Args:
            instance_id: 插件实例 ID
            namespace: 命名空间（private 或 public）
            
        Returns:
            数据字典的副本
            
        Raises:
            DataProviderError: 插件不存在时抛出
        """
        data = self.load_data()
        
        if instance_id not in data["plugins"]:
            raise DataProviderError(f"插件 {instance_id} 不存在")
        
        namespace_str = namespace.value
        return data["plugins"][instance_id][namespace_str].copy()
    
    # ==================== 发布/订阅模式 ====================
    
    def subscribe(self, 
                 subscriber_id: str, 
                 target_plugin_id: str, 
                 target_key: str, 
                 callback: Callable[[str, str, Any, Any], None]) -> None:
        """
        订阅其他插件的 public 数据变化
        
        Args:
            subscriber_id: 订阅者插件 ID
            target_plugin_id: 目标插件 ID
            target_key: 要订阅的数据键
            callback: 回调函数，签名为 callback(target_plugin_id, key, old_value, new_value)
            
        Raises:
            DataProviderError: 目标插件不存在时抛出

        注意: 系统不阻止订阅任意 key，仅在 namespace=PUBLIC 时才会触发回调通知。
        """
        data = self.load_data()
        
        # 验证目标插件存在
        if target_plugin_id not in data["plugins"]:
            raise DataProviderError(f"目标插件 {target_plugin_id} 不存在")
        
        with self._subscription_lock:
            subscription_key = (subscriber_id, target_plugin_id, target_key)
            self._subscriptions[subscription_key] = callback
    
    def unsubscribe(self, subscriber_id: str, target_plugin_id: Optional[str] = None) -> None:
        """
        取消订阅
        
        Args:
            subscriber_id: 订阅者插件 ID
            target_plugin_id: 可选，目标插件 ID。如果为 None，则取消该订阅者的所有订阅
        """
        with self._subscription_lock:
            if target_plugin_id is None:
                # 移除该订阅者的所有订阅
                keys_to_remove = [k for k in self._subscriptions.keys() if k[0] == subscriber_id]
                for key in keys_to_remove:
                    del self._subscriptions[key]
            else:
                # 移除该订阅者对特定插件的所有订阅
                keys_to_remove = [k for k in self._subscriptions.keys() 
                                 if k[0] == subscriber_id and k[1] == target_plugin_id]
                for key in keys_to_remove:
                    del self._subscriptions[key]
    
    def publish(self, 
                publisher_id: str, 
                key: str, 
                value: Any,
                namespace: DataNamespace = DataNamespace.PUBLIC) -> None:
        """
        发布数据更新（等同于 set_plugin_data 的别名）
        
        Args:
            publisher_id: 发布者插件 ID
            key: 数据键
            value: 数据值
            namespace: 命名空间（默认为 public）
        """
        self.set_plugin_data(publisher_id, key, value, namespace, notify=True)
    
    def _notify_subscribers(self, 
                          publisher_id: str, 
                          key: str, 
                          old_value: Any, 
                          new_value: Any) -> None:
        """
        通知所有订阅者
        
        Args:
            publisher_id: 发布者插件 ID
            key: 数据键
            old_value: 旧值
            new_value: 新值
        """
        with self._subscription_lock:
            # 查找所有匹配的订阅
            for (subscriber_id, target_plugin_id, target_key), callback in self._subscriptions.items():
                if target_plugin_id == publisher_id and target_key == key:
                    try:
                        callback(target_plugin_id, key, old_value, new_value)
                    except Exception as e:
                        self._logger.warning(get_name(), f'Subscriber {subscriber_id} callback failed: {e}')
    
    def _remove_subscriptions_for_plugin(self, instance_id: str) -> None:
        """
        移除与指定插件相关的所有订阅
        
        Args:
            instance_id: 插件实例 ID
        """
        with self._subscription_lock:
            # 移除该插件作为订阅者的订阅
            keys_to_remove = [k for k in self._subscriptions.keys() if k[0] == instance_id]
            for key in keys_to_remove:
                del self._subscriptions[key]
            
            # 移除其他插件对该插件的订阅
            keys_to_remove = [k for k in self._subscriptions.keys() if k[1] == instance_id]
            for key in keys_to_remove:
                del self._subscriptions[key]
    
    # ==================== 资源文件管理 ====================
    
    def save_asset(self, 
                  plugin_id: str, 
                  filename: str, 
                  content: bytes) -> str:
        """
        保存资源文件
        
        Args:
            plugin_id: 插件 ID
            filename: 文件名
            content: 文件内容（bytes）
            
        Returns:
            相对路径（相对于 assets 目录）
            
        Raises:
            DataProviderError: 保存失败时抛出
        """
        try:
            # 创建插件专属目录
            plugin_dir = self.assets_dir / plugin_id
            plugin_dir.mkdir(parents=True, exist_ok=True)
            
            # 保存文件
            file_path = plugin_dir / filename
            with open(file_path, 'wb') as f:
                f.write(content)
            
            # 返回相对路径
            relative_path = f"assets/plugins/{plugin_id}/{filename}"
            return relative_path
            
        except Exception as e:
            raise DataProviderError(f"保存资源文件失败: {e}")
    
    def get_asset_path(self, relative_path: str) -> str:
        """
        将相对路径转换为绝对路径
        
        Args:
            relative_path: 相对路径（例如：assets/plugins/plugin_id/filename.ext）
            
        Returns:
            绝对路径
            
        Raises:
            DataProviderError: 路径无效时抛出
        """
        try:
            # 确保相对路径不包含危险的路径遍历
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
        """
        加载资源文件内容
        
        Args:
            relative_path: 相对路径
            
        Returns:
            文件内容（bytes）
            
        Raises:
            DataProviderError: 加载失败时抛出
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
        """
        获取插件的资源目录路径
        
        Args:
            plugin_id: 插件 ID
            
        Returns:
            资源目录的绝对路径
        """
        plugin_dir = self.assets_dir / plugin_id
        plugin_dir.mkdir(parents=True, exist_ok=True)
        return str(plugin_dir.resolve())
    
    # ==================== 工具方法 ====================
    
    def get_all_plugins(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有插件信息
        
        Returns:
            插件信息字典 {instance_id: {type, active, private, public}}
        """
        data = self.load_data()
        return data.get("plugins", {}).copy()
    
    def get_plugin_info(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """
        获取指定插件的信息
        
        Args:
            instance_id: 插件实例 ID
            
        Returns:
            插件信息字典，如果不存在则返回 None
        """
        data = self.load_data()
        return data.get("plugins", {}).get(instance_id)
    
    def reset_all_data(self) -> None:
        """重置所有数据（慎用！）"""
        default_data = {
            "plugins": {},
            "active_instances": {}
        }
        self._cache = default_data
        self.save_data()
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