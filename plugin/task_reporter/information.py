"""
任务报告生成器插件元数据
"""

from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon
from typing import Dict, Any, Optional


class TaskReporterPluginInfo(IPluginInfo):
    """任务报告生成器插件元数据"""
    
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
        任务报告生成器插件提供任务统计和报告生成功能，包括：
        - 实时订阅任务管理器的数据变更
        - 自动记录所有任务事件（添加、更新、删除）
        - 生成详细的统计报告（JSON/TXT/HTML格式）
        - 计算性能指标（完成率、待办比例等）
        - 可视化事件历史记录
        - 支持多种报告导出格式
        
        该插件完美展示了 DataProvider 的发布/订阅模式：
        - 自动监听任务管理器的 public 数据变更
        - 实时接收统计信息更新通知
        - 记录所有任务操作事件
        - 生成综合分析报告
        
        与任务管理器插件配合使用，实现完整的数据流：
        任务管理器 → 发布数据变更 → 报告生成器订阅 → 生成报告
        
        功能演示：
        1. 订阅任务管理器
        2. 在任务管理器中添加/更新/删除任务
        3. 报告生成器自动接收变更通知
        4. 查看实时统计信息和事件历史
        5. 生成多种格式的报告
        """
    
    @property
    def service_api(self) -> Dict[str, Any]:
        return {
            "subscribe_to_task_manager": {
                "description": "订阅任务管理器的数据变更",
                "parameters": {
                    "task_manager_id": {
                        "type": "str",
                        "description": "任务管理器插件ID",
                        "required": True
                    }
                },
                "returns": {
                    "type": "bool",
                    "description": "是否订阅成功"
                }
            },
            "unsubscribe_from_task_manager": {
                "description": "取消订阅任务管理器",
                "parameters": {
                    "task_manager_id": {
                        "type": "str",
                        "description": "任务管理器插件ID（可选）",
                        "required": False
                    }
                },
                "returns": {
                    "type": "None",
                    "description": "无返回值"
                }
            },
            "get_statistics_report": {
                "description": "获取统计报告",
                "parameters": {
                    "task_manager_id": {
                        "type": "str",
                        "description": "任务管理器插件ID",
                        "required": True
                    }
                },
                "returns": {
                    "type": "dict",
                    "description": "统计报告（包含统计数据和性能指标）"
                }
            },
            "get_event_history": {
                "description": "获取事件历史",
                "parameters": {
                    "limit": {
                        "type": "int",
                        "description": "最大返回数量",
                        "required": False
                    }
                },
                "returns": {
                    "type": "list",
                    "description": "事件列表"
                }
            },
            "generate_report": {
                "description": "生成完整报告",
                "parameters": {
                    "task_manager_id": {
                        "type": "str",
                        "description": "任务管理器插件ID",
                        "required": True
                    },
                    "format": {
                        "type": "str",
                        "description": "报告格式 (json, txt, html)",
                        "required": False
                    }
                },
                "returns": {
                    "type": "str",
                    "description": "报告文件的相对路径"
                }
            },
            "clear_event_log": {
                "description": "清除事件日志",
                "parameters": {},
                "returns": {
                    "type": "None",
                    "description": "无返回值"
                }
            }
        }
    
    @property
    def skill_icon(self) -> PluginIcon:
        return PluginIcon.builtin("SP_DialogOkButton")
    
    @property
    def skill_description(self) -> str:
        return "生成任务报告、统计分析"
    
    @property
    def tags(self) -> Optional[list[str]]:
        return ["report", "statistics", "analytics", "monitoring"]
    
    @property
    def dependencies(self) -> Optional[Dict[str, str]]:
        return None

    @property
    def plugin_type_id(self) -> str:
        """插件类型标识符"""
        return "task-reporter"