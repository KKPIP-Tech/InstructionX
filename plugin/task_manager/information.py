"""
任务管理器插件元数据
"""

from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon
from typing import Dict, Any, Optional


class TaskManagerPluginInfo(IPluginInfo):
    """任务管理器插件元数据"""
    
    @property
    def version(self) -> PluginVersion:
        return PluginVersion.from_string("release.1.0.0")
    
    @property
    def developer(self) -> str:
        return "KKPIP-Tech"
    
    @property
    def developer_email(self) -> str:
        return "support@example.com"
    
    @property
    def developer_website(self) -> str:
        return "https://github.com/KKPIP-Tech/InstructionX"
    
    @property
    def is_free(self) -> bool:
        return True
    
    @property
    def description(self) -> str:
        return """
        任务管理器插件提供完整的任务管理功能，包括：
        - 创建、编辑和删除任务
        - 任务状态跟踪（待办、进行中、已完成、已取消）
        - 任务优先级设置（低、普通、高）
        - 任务筛选和搜索
        - 任务统计信息实时更新
        - 任务数据导出（JSON/CSV格式）
        - 任务附件管理
        
        该插件展示了 DataProvider 的所有核心功能：
        - 数据持久化（原子写入）
        - 命名空间隔离（private/public数据）
        - 发布/订阅模式（实时通知）
        - 资源文件管理
        - 缓存机制
        - 线程安全
        
        可以与任务报告生成器插件配合使用，
        自动生成任务统计报告和图表。
        """
    
    @property
    def service_api(self) -> Dict[str, Any]:
        return {
            "add_task": {
                "description": "添加新任务",
                "parameters": {
                    "title": {
                        "type": "str",
                        "description": "任务标题",
                        "required": True
                    },
                    "description": {
                        "type": "str",
                        "description": "任务描述",
                        "required": False
                    },
                    "priority": {
                        "type": "str",
                        "description": "优先级 (low, normal, high)",
                        "required": False
                    }
                },
                "returns": {
                    "type": "dict",
                    "description": "任务信息"
                }
            },
            "update_task_status": {
                "description": "更新任务状态",
                "parameters": {
                    "task_id": {
                        "type": "str",
                        "description": "任务ID",
                        "required": True
                    },
                    "status": {
                        "type": "str",
                        "description": "状态 (pending, in_progress, completed, cancelled)",
                        "required": True
                    }
                },
                "returns": {
                    "type": "bool",
                    "description": "是否成功"
                }
            },
            "get_tasks": {
                "description": "获取任务列表",
                "parameters": {
                    "status": {
                        "type": "str",
                        "description": "可选，筛选特定状态的任务",
                        "required": False
                    }
                },
                "returns": {
                    "type": "list",
                    "description": "任务列表"
                }
            },
            "delete_task": {
                "description": "删除任务",
                "parameters": {
                    "task_id": {
                        "type": "str",
                        "description": "任务ID",
                        "required": True
                    }
                },
                "returns": {
                    "type": "bool",
                    "description": "是否成功"
                }
            },
            "get_statistics": {
                "description": "获取任务统计信息",
                "parameters": {},
                "returns": {
                    "type": "dict",
                    "description": "统计信息（总数、各状态数量）"
                }
            },
            "export_tasks": {
                "description": "导出任务数据",
                "parameters": {
                    "format": {
                        "type": "str",
                        "description": "导出格式 (json, csv)",
                        "required": False
                    }
                },
                "returns": {
                    "type": "str",
                    "description": "导出文件的相对路径"
                }
            }
        }
    
    @property
    def skill_icon(self) -> PluginIcon:
        return PluginIcon.builtin("SP_DialogOpenButton")
    
    @property
    def skill_description(self) -> str:
        return "管理任务、跟踪状态、生成报告"
    
    @property
    def tags(self) -> Optional[list[str]]:
        return ["task", "management", "productivity", "tracker"]
    
    @property
    def dependencies(self) -> Optional[Dict[str, str]]:
        return None

    @property
    def plugin_type_id(self) -> str:
        """插件类型标识符"""
        return "task-manager"