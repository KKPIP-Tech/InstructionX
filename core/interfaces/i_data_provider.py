"""
DataProvider 数据提供者接口

定义数据持久化、缓存、插件管理、发布/订阅通信和资源管理功能的抽象接口。
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional, Callable


class DataNamespace(Enum):
    """数据命名空间枚举"""
    PRIVATE = "private"  # 仅插件内部使用
    PUBLIC = "public"    # 允许其他插件访问


class IDataProvider(ABC):
    """
    数据提供者接口

    定义插件数据的持久化、缓存、管理和通信的抽象接口。
    插件通过此接口访问数据存储能力，而非直接依赖 DataProvider 实现。
    """

    # ==================== 插件管理 ====================

    @abstractmethod
    def register_plugin(self, instance_id: str, plugin_type: str) -> None:
        """注册插件实例"""
        pass

    @abstractmethod
    def unregister_plugin(self, instance_id: str) -> None:
        """注销插件实例"""
        pass

    @abstractmethod
    def get_active_instance(self, plugin_type: str) -> Optional[str]:
        """根据插件类型获取当前活跃的实例 ID"""
        pass

    @abstractmethod
    def set_active_instance(self, instance_id: str) -> None:
        """将某实例标记为当前活跃实例"""
        pass

    # ==================== 数据访问 ====================

    @abstractmethod
    def get_plugin_data(
        self,
        instance_id: str,
        key: str,
        namespace: DataNamespace = DataNamespace.PRIVATE,
        default: Any = None
    ) -> Any:
        """获取插件数据"""
        pass

    @abstractmethod
    def set_plugin_data(
        self,
        instance_id: str,
        key: str,
        value: Any,
        namespace: DataNamespace = DataNamespace.PRIVATE,
        notify: bool = True
    ) -> None:
        """设置插件数据"""
        pass

    @abstractmethod
    def get_all_plugin_data(
        self,
        instance_id: str,
        namespace: DataNamespace = DataNamespace.PRIVATE
    ) -> Dict[str, Any]:
        """获取插件的所有数据（指定命名空间）"""
        pass

    # ==================== 发布/订阅模式 ====================

    @abstractmethod
    def subscribe(
        self,
        subscriber_id: str,
        target_plugin_id: str,
        target_key: str,
        callback: Callable[[str, str, Any, Any], None]
    ) -> None:
        """
        订阅其他插件的 public 数据变化

        Args:
            subscriber_id: 订阅者插件 ID
            target_plugin_id: 目标插件 ID
            target_key: 要订阅的数据键
            callback: 回调函数，签名为 callback(target_plugin_id, key, old_value, new_value)
        """
        pass

    @abstractmethod
    def unsubscribe(self, subscriber_id: str, target_plugin_id: Optional[str] = None) -> None:
        """
        取消订阅

        Args:
            subscriber_id: 订阅者插件 ID
            target_plugin_id: 可选，目标插件 ID。如果为 None，则取消该订阅者的所有订阅
        """
        pass

    @abstractmethod
    def publish(
        self,
        publisher_id: str,
        key: str,
        value: Any,
        namespace: DataNamespace = DataNamespace.PUBLIC
    ) -> None:
        """发布数据更新"""
        pass

    # ==================== 资源文件管理 ====================

    @abstractmethod
    def save_asset(
        self,
        plugin_id: str,
        filename: str,
        content: bytes
    ) -> str:
        """保存资源文件"""
        pass

    @abstractmethod
    def get_asset_path(self, relative_path: str) -> str:
        """获取资源文件的绝对路径"""
        pass

    @abstractmethod
    def load_asset(self, relative_path: str) -> bytes:
        """加载资源文件内容"""
        pass

    @abstractmethod
    def get_plugin_assets_dir(self, plugin_id: str) -> str:
        """获取插件的资源目录路径"""
        pass

    # ==================== 工具方法 ====================

    @abstractmethod
    def get_all_plugins(self) -> Dict[str, Dict[str, Any]]:
        """获取所有插件信息"""
        pass

    @abstractmethod
    def get_plugin_info(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """获取指定插件的信息"""
        pass
