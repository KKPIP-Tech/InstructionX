"""
Framework API Demo 插件服务层

提供演示 InstructionX 框架 API 的服务类。
"""

import time
import uuid
from typing import Any, Dict, Optional, List

from core.data.data_provider import DataProvider, DataNamespace
from core.task import BackgroundTaskManager, TaskStatus
from core.llm.llm_provider import LLMProvider
from core.plugin.manager import PluginManager
from utils.logging_tools import LoggerManager, get_name


class Service:
    """服务基类"""

    def __init__(self, plugin_id: str, data_provider: DataProvider):
        self.plugin_id = plugin_id
        self.data_provider = data_provider
        self.logger = LoggerManager()


class DataDemoService(Service):
    """演示 DataProvider 接口的服务类"""

    def __init__(self, plugin_id: str, data_provider: DataProvider):
        super().__init__(plugin_id, data_provider)
        self.demo_plugin_id = f"demo-target-{uuid.uuid4().hex[:8]}"

    def register_demo_plugin(self) -> Dict[str, Any]:
        """演示注册插件"""
        try:
            self.data_provider.register_plugin(self.demo_plugin_id, "DemoTarget")
            self.logger.info(get_name(), f"成功注册演示插件: {self.demo_plugin_id}")
            return {"success": True, "message": f"插件 {self.demo_plugin_id} 注册成功"}
        except Exception as e:
            self.logger.error(get_name(), f"注册插件失败: {e}")
            return {"success": False, "error": str(e)}

    def unregister_demo_plugin(self) -> Dict[str, Any]:
        """演示注销插件"""
        try:
            self.data_provider.unregister_plugin(self.demo_plugin_id)
            self.logger.info(get_name(), f"成功注销演示插件: {self.demo_plugin_id}")
            return {"success": True, "message": f"插件 {self.demo_plugin_id} 注销成功"}
        except Exception as e:
            self.logger.error(get_name(), f"注销插件失败: {e}")
            return {"success": False, "error": str(e)}

    def write_private_data(self, key: str, value: Any) -> Dict[str, Any]:
        """演示写入私有数据"""
        try:
            self.data_provider.set_plugin_data(
                self.plugin_id, key, value, DataNamespace.PRIVATE
            )
            return {"success": True, "message": f"写入私有数据成功: {key}={value}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def read_private_data(self, key: str, default: Any = None) -> Dict[str, Any]:
        """演示读取私有数据"""
        try:
            value = self.data_provider.get_plugin_data(
                self.plugin_id, key, DataNamespace.PRIVATE, default
            )
            return {"success": True, "value": value}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def write_public_data(self, key: str, value: Any) -> Dict[str, Any]:
        """演示写入公共数据"""
        try:
            self.data_provider.set_plugin_data(
                self.plugin_id, key, value, DataNamespace.PUBLIC
            )
            return {"success": True, "message": f"写入公共数据成功: {key}={value}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def read_public_data(self, key: str, default: Any = None) -> Dict[str, Any]:
        """演示读取公共数据"""
        try:
            value = self.data_provider.get_plugin_data(
                self.plugin_id, key, DataNamespace.PUBLIC, default
            )
            return {"success": True, "value": value}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_all_data(self) -> Dict[str, Any]:
        """演示获取所有数据"""
        try:
            private_data = self.data_provider.get_all_plugin_data(
                self.plugin_id, DataNamespace.PRIVATE
            )
            public_data = self.data_provider.get_all_plugin_data(
                self.plugin_id, DataNamespace.PUBLIC
            )
            return {
                "success": True,
                "private": private_data,
                "public": public_data
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_demo_asset(self) -> Dict[str, Any]:
        """演示保存资源文件"""
        try:
            content = b"Demo asset content"
            relative_path = self.data_provider.save_asset(
                self.plugin_id, "demo.txt", content
            )
            return {"success": True, "path": relative_path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def load_demo_asset(self, relative_path: str) -> Dict[str, Any]:
        """演示加载资源文件"""
        try:
            content = self.data_provider.load_asset(relative_path)
            return {"success": True, "content": content.decode()}
        except Exception as e:
            return {"success": False, "error": str(e)}


class TaskDemoService(Service):
    """演示 BackgroundTaskManager 接口的服务类"""

    def __init__(self, plugin_id: str, data_provider: DataProvider):
        super().__init__(plugin_id, data_provider)
        self.task_manager = BackgroundTaskManager()

    def create_sync_task(self, name: str = "sync_task") -> Dict[str, Any]:
        """演示创建同步任务"""
        def sync_func(seconds: int):
            time.sleep(seconds)
            return f"同步任务完成，耗时 {seconds} 秒"

        try:
            task_id = self.task_manager.register_sync_task(
                plugin_id=self.plugin_id,
                name=name,
                func=sync_func,
                args=(1,)
            )
            return {"success": True, "task_id": task_id, "message": "同步任务已创建并执行"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_async_task(self, name: str = "async_task") -> Dict[str, Any]:
        """演示创建异步任务"""
        def async_func(seconds: int):
            time.sleep(seconds)
            return f"异步任务完成，耗时 {seconds} 秒"

        try:
            task_id = self.task_manager.register_async_task(
                plugin_id=self.plugin_id,
                name=name,
                func=async_func,
                args=(2,)
            )
            return {"success": True, "task_id": task_id, "message": "异步任务已创建"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_scheduled_task(self, name: str = "scheduled_task", interval: int = 60) -> Dict[str, Any]:
        """演示创建定时任务"""
        def scheduled_func():
            return "定时任务执行"

        try:
            task_id = self.task_manager.register_scheduled_task(
                plugin_id=self.plugin_id,
                name=name,
                func=scheduled_func,
                interval=interval
            )
            return {"success": True, "task_id": task_id, "message": f"定时任务已创建，间隔 {interval} 秒"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def query_tasks(self) -> Dict[str, Any]:
        """演示查询任务"""
        try:
            all_tasks = self.task_manager.get_tasks_by_plugin(self.plugin_id)
            scheduled_tasks = self.task_manager.get_scheduled_tasks(self.plugin_id)

            return {
                "success": True,
                "tasks": [
                    {"task_id": t.task_id, "name": t.name, "status": t.status.value}
                    for t in all_tasks
                ],
                "scheduled_tasks": [
                    {"task_id": t.task_id, "name": t.name, "interval": t.interval, "enabled": t.enabled}
                    for t in scheduled_tasks
                ]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def clear_completed(self) -> Dict[str, Any]:
        """演示清理已完成任务"""
        try:
            count = self.task_manager.clear_completed_tasks(self.plugin_id)
            return {"success": True, "message": f"已清理 {count} 个任务"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class LLMDemoService(Service):
    """演示 LLMProvider 接口的服务类"""

    def __init__(self, plugin_id: str, data_provider: DataProvider):
        super().__init__(plugin_id, data_provider)
        self.llm_provider = LLMProvider()

    def get_providers(self) -> Dict[str, Any]:
        """演示获取 Provider 列表"""
        try:
            providers = self.llm_provider.get_all_providers()
            return {
                "success": True,
                "providers": list(providers.keys()),
                "enabled": list(self.llm_provider.get_enabled_providers().keys())
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_models(self, provider: str = None) -> Dict[str, Any]:
        """演示获取模型列表"""
        try:
            if provider:
                models = self.llm_provider.get_cached_models(provider)
            else:
                models_dict = self.llm_provider.get_models()
                return {
                    "success": True,
                    "models": {
                        k: [{"id": m.id, "name": m.name} for m in v]
                        for k, v in models_dict.items()
                    }
                }

            return {
                "success": True,
                "models": [{"id": m.id, "name": m.name} for m in models]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def send_chat(self, message: str = "你好", provider: str = "default") -> Dict[str, Any]:
        """演示发送聊天请求"""
        try:
            messages = [{"role": "user", "content": message}]
            response = self.llm_provider.chat(messages, provider=provider)
            return {
                "success": True,
                "response": response.content,
                "model": response.model,
                "provider": provider
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def send_embedding(self, text: str = "Hello world", provider: str = "default") -> Dict[str, Any]:
        """演示发送嵌入请求"""
        try:
            response = self.llm_provider.embed(texts=text, provider=provider)
            return {
                "success": True,
                "embedding_size": len(response[0].embedding) if response else 0,
                "provider": provider
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class APIDemoService(Service):
    """演示 PluginManager API 接口的服务类"""

    def __init__(self, plugin_id: str, data_provider: DataProvider):
        super().__init__(plugin_id, data_provider)
        self.plugin_manager = PluginManager()

    def get_all_plugins(self) -> Dict[str, Any]:
        """演示获取所有插件"""
        try:
            plugins = self.plugin_manager.get_all_plugins()
            return {
                "success": True,
                "count": len(plugins),
                "plugins": [
                    {"name": p.plugin_name, "id": p.plugin_id}
                    for p in plugins
                ]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_plugin_by_id(self, plugin_id: str = None) -> Dict[str, Any]:
        """演示通过 ID 获取插件"""
        try:
            if not plugin_id:
                plugins = self.plugin_manager.get_all_plugins()
                if plugins:
                    plugin_id = plugins[0].plugin_id

            plugin = self.plugin_manager.get_plugin_by_id(plugin_id)
            if plugin:
                return {
                    "success": True,
                    "plugin": {"name": plugin.plugin_name, "id": plugin.plugin_id}
                }
            return {"success": False, "error": "插件不存在"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_all_apis(self) -> Dict[str, Any]:
        """演示获取所有注册的 API"""
        try:
            apis = self.plugin_manager.get_all_apis()
            return {
                "success": True,
                "count": len(apis),
                "apis": {
                    pid: {
                        "name": info["plugin_name"],
                        "methods": list(info.get("methods", []))
                    }
                    for pid, info in apis.items()
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_all_function_tools(self) -> Dict[str, Any]:
        """演示获取所有 Function Tools（MCP/OpenAI 格式）"""
        try:
            tools = self.plugin_manager.get_all_function_tools()
            return {
                "success": True,
                "count": len(tools),
                "tools": tools
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_api_description(self, plugin_id: str = None, method_name: str = None) -> Dict[str, Any]:
        """演示获取 API 描述"""
        try:
            if not plugin_id:
                apis = self.plugin_manager.get_all_apis()
                if apis:
                    plugin_id = list(apis.keys())[0]

            desc = self.plugin_manager.get_api_description(plugin_id, method_name)
            return {
                "success": True,
                "description": desc
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def call_plugin_method(self, plugin_id: str = None, method_name: str = None, **kwargs) -> Dict[str, Any]:
        """演示跨插件调用方法"""
        try:
            if not plugin_id or not method_name:
                return {"success": False, "error": "需要指定 plugin_id 和 method_name"}

            result = self.plugin_manager.call_plugin_method(
                caller_id=self.plugin_id,
                plugin_id=plugin_id,
                method_name=method_name,
                **kwargs
            )
            return {
                "success": True,
                "result": result
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class FrameworkInfoService(Service):
    """获取框架信息的服务类"""

    def __init__(self, plugin_id: str, data_provider: DataProvider):
        super().__init__(plugin_id, data_provider)

    def get_framework_info(self) -> Dict[str, Any]:
        """获取框架信息"""
        return {
            "framework": "InstructionX",
            "version": "1.0.0",
            "apis": [
                "DataProvider",
                "BackgroundTaskManager",
                "LLMProvider",
                "PluginManager",
                "LoggerManager"
            ]
        }
