"""
Framework API Demo 插件元数据

展示 InstructionX 框架提供的所有核心 API 接口的使用方法。
"""

from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon
from typing import Dict, Any, List


class FrameworkAPIDemoPluginInfo(IPluginInfo):
    """Framework API Demo 插件元数据"""

    @property
    def version(self) -> PluginVersion:
        """插件版本"""
        return PluginVersion.from_string("release.1.0.0")

    @property
    def developer(self) -> str:
        """开发者名称"""
        return "InstructionX"

    @property
    def developer_email(self) -> str:
        """开发者邮箱"""
        return "support@instructionx.dev"

    @property
    def developer_website(self) -> str:
        """开发者网站"""
        return "https://github.com/KKPIP-Tech/InstructionX"

    @property
    def is_free(self) -> bool:
        """是否免费"""
        return True

    @property
    def description(self) -> str:
        """插件详细描述"""
        return """
        Framework API Demo 插件用于演示 InstructionX 框架提供的所有核心 API 接口。

        演示的接口包括：
        - DataProvider: 数据持久化、发布/订阅、资源管理
        - BackgroundTaskManager: 同步/异步/定时/长期任务
        - LLMProvider: 聊天、嵌入、模型管理
        - PluginManager: 插件查询、API 注册与调用
        - LoggerManager: 日志记录

        该插件是一个学习工具，帮助开发者了解如何使用框架的各种功能。
        """

    @property
    def service_api(self) -> Dict[str, Any]:
        """Service API 定义"""
        return {
            "demo_data_operation": {
                "description": "演示 DataProvider 数据操作",
                "parameters": {
                    "operation": {
                        "type": "str",
                        "description": "操作类型: read/write/list",
                        "required": True
                    },
                    "key": {
                        "type": "str",
                        "description": "数据键名",
                        "required": False
                    },
                    "value": {
                        "type": "any",
                        "description": "数据值",
                        "required": False
                    }
                },
                "returns": {
                    "type": "any",
                    "description": "操作结果"
                }
            },
            "demo_task_operation": {
                "description": "演示任务操作",
                "parameters": {
                    "operation": {
                        "type": "str",
                        "description": "操作类型: create/query/cancel",
                        "required": True
                    },
                    "task_type": {
                        "type": "str",
                        "description": "任务类型: sync/async/scheduled",
                        "required": False
                    }
                },
                "returns": {
                    "type": "any",
                    "description": "操作结果"
                }
            },
            "get_framework_info": {
                "description": "获取框架信息",
                "parameters": {},
                "returns": {
                    "type": "dict",
                    "description": "框架信息字典"
                }
            }
        }

    @property
    def skill_icon(self) -> PluginIcon:
        """插件图标配置"""
        return PluginIcon.builtin("SP_VistaShield")

    @property
    def skill_description(self) -> str:
        """插件简短描述"""
        return "演示框架所有 API 接口"

    @property
    def tags(self) -> List[str]:
        """插件标签"""
        return ["demo", "api", "framework", "learning"]

    @property
    def dependencies(self) -> None:
        """依赖项"""
        return None

    @property
    def plugin_type_id(self) -> str:
        """插件类型标识符"""
        return "framework-api-demo"
