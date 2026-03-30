"""
后台任务演示器插件信息
"""

from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon
from typing import Dict


class BackgroundTaskDemoInfo(IPluginInfo):
    """后台任务演示器插件元数据"""

    @property
    def version(self) -> PluginVersion:
        return PluginVersion(major=1, minor=0, patch=0)

    @property
    def developer(self) -> str:
        return "InstructionX Team"

    @property
    def developer_email(self) -> str:
        return "support@instructionx.com"

    @property
    def developer_website(self) -> str:
        return "https://instructionx.com"

    @property
    def is_free(self) -> bool:
        return True

    @property
    def description(self) -> str:
        return "演示 BackgroundTask 后台任务模块的所有功能，包括同步任务、异步任务、定时任务和任务状态管理"

    @property
    def service_api(self) -> Dict:
        """定义插件提供的 API"""
        return {
            "methods": {
                "get_tasks": {
                    "description": "获取所有后台任务",
                    "parameters": {}
                },
                "get_scheduled_tasks": {
                    "description": "获取所有定时任务",
                    "parameters": {}
                },
                "create_sync_task": {
                    "description": "创建同步任务",
                    "parameters": {
                        "name": {"type": "string", "required": True},
                        "func_name": {"type": "string", "required": True}
                    }
                },
                "create_async_task": {
                    "description": "创建异步任务",
                    "parameters": {
                        "name": {"type": "string", "required": True}
                    }
                }
            }
        }

    @property
    def skill_icon(self) -> PluginIcon:
        # 使用暂停图标 - 代表后台/定时任务的暂停与调度
        return PluginIcon.builtin("SP_MediaPause")

    @property
    def skill_description(self) -> str:
        return "后台任务演示"

    @property
    def plugin_type_id(self) -> str:
        """插件类型标识符"""
        return "background-task-demo"
