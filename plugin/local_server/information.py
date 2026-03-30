from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon
from typing import Dict, Any


class LocalServerPluginInfo(IPluginInfo):
    """本地HTTP服务器插件信息"""

    @property
    def version(self) -> PluginVersion:
        """插件版本"""
        return PluginVersion.from_string("release.1.0.0")

    @property
    def developer(self) -> str:
        """开发者名称"""
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
        return "提供本地HTTP服务器功能，可用于测试Webhook、API等场景"

    @property
    def service_api(self) -> Dict[str, Any]:
        """插件API定义"""
        return {
            "get_status": {
                "description": "获取服务器状态",
                "parameters": {},
                "returns": {
                    "type": "dict",
                    "description": "包含 is_running, request_count, task_id"
                }
            }
        }

    @property
    def skill_icon(self) -> PluginIcon:
        """技能按钮图标"""
        return PluginIcon.builtin("SP_ComputerIcon")

    @property
    def skill_description(self) -> str:
        """技能简短描述"""
        return "本地HTTP服务器"

    @property
    def tags(self) -> list:
        """插件标签"""
        return ["开发工具", "服务器", "HTTP"]

    @property
    def plugin_type_id(self) -> str:
        """插件类型标识符"""
        return "local-server"
