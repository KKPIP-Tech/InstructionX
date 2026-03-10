"""
本地HTTP服务器插件

提供本地HTTP服务器功能，可用于测试Webhook、API等场景。
"""

from core.data.data_provider import DataProvider, DataProviderError, DataNamespace


class Service:
    """本地HTTP服务器服务"""

    def __init__(self, plugin_id: str = None, data_provider=None):
        self.plugin_id = plugin_id
        self.data_provider = data_provider or DataProvider()

        # 从 DataProvider 恢复状态
        if plugin_id:
            self._server_task_id = self.load_data("server_task_id")
            self._request_count = self.load_data("request_count", 0)
            self._is_running = self.load_data("is_running", False)
        else:
            self._server_task_id = None
            self._request_count = 0
            self._is_running = False

    def get_status(self) -> dict:
        """获取服务器状态"""
        return {
            "is_running": self._is_running,
            "request_count": self._request_count,
            "task_id": self._server_task_id
        }

    def increment_request_count(self):
        """增加请求计数"""
        self._request_count += 1

        # 确保 plugin_id 存在
        if not self.plugin_id:
            return

        # 更新状态到 DataProvider
        self.data_provider.set_plugin_data(
            self.plugin_id,
            "request_count",
            self._request_count,
            DataNamespace.PRIVATE
        )

    def set_running(self, is_running: bool, task_id: str = None):
        """设置运行状态"""
        self._is_running = is_running
        self._server_task_id = task_id

        # 确保 plugin_id 存在
        if not self.plugin_id:
            return

        self.data_provider.set_plugin_data(
            self.plugin_id,
            "is_running",
            is_running,
            DataNamespace.PRIVATE
        )

    def save_data(self, key: str, value):
        """保存数据"""
        self.data_provider.set_plugin_data(
            self.plugin_id,
            key,
            value,
            DataNamespace.PRIVATE
        )

    def load_data(self, key: str, default=None):
        """加载数据"""
        try:
            return self.data_provider.get_plugin_data(
                self.plugin_id,
                key,
                DataNamespace.PRIVATE,
                default
            )
        except DataProviderError:
            # 插件尚未注册（首次安装），使用默认值
            return default
