"""
LLM Chat 插件信息
"""

from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon
from typing import Dict, Any


class LLMChatPluginInfo(IPluginInfo):
    """LLM Chat 插件信息"""

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
        return (
            "LLM Chat 插件 - 智能对话工具\n\n"
            "功能特点:\n"
            "• 支持多个 LLM Provider (MiniMax, SiliconFlow, GLM, Ollama)\n"
            "• 自由选择模型\n"
            "• 支持多模态 (Vision 图片理解)\n"
            "• 流式输出，实时显示\n"
            "• 对话历史保存\n"
            "• 完善的错误处理"
        )

    @property
    def service_api(self) -> Dict[str, Any]:
        """
        定义可被其他插件调用的方法
        """
        return {
            "send_message": {
                "description": "发送消息并获取 LLM 回复",
                "parameters": {
                    "message": {
                        "type": "str",
                        "description": "用户消息",
                        "required": True
                    },
                    "provider": {
                        "type": "str",
                        "description": "Provider 名称",
                        "required": True
                    },
                    "model": {
                        "type": "str",
                        "description": "模型名称（可选）",
                        "required": False
                    },
                    "temperature": {
                        "type": "float",
                        "description": "温度参数 (0.0-2.0)",
                        "required": False,
                        "default": 0.7
                    },
                    "max_tokens": {
                        "type": "int",
                        "description": "最大 token 数",
                        "required": False
                    },
                    "images": {
                        "type": "list",
                        "description": "图片 base64 列表（用于 Vision）",
                        "required": False
                    }
                },
                "returns": {
                    "type": "dict",
                    "description": "包含 success, response, error 等字段的字典"
                }
            },
            "get_providers": {
                "description": "获取所有可用的 Provider 列表",
                "parameters": {},
                "returns": {
                    "type": "list",
                    "description": "Provider 名称列表"
                }
            },
            "get_models": {
                "description": "获取指定 Provider 的模型列表",
                "parameters": {
                    "provider": {
                        "type": "str",
                        "description": "Provider 名称",
                        "required": True
                    }
                },
                "returns": {
                    "type": "list",
                    "description": "模型信息列表"
                }
            },
            "validate_provider": {
                "description": "验证 Provider 配置是否有效",
                "parameters": {
                    "provider": {
                        "type": "str",
                        "description": "Provider 名称",
                        "required": True
                    }
                },
                "returns": {
                    "type": "dict",
                    "description": "包含 valid, message, supports_vision 的字典"
                }
            }
        }

    @property
    def skill_icon(self) -> PluginIcon:
        """技能按钮图标"""
        # 使用内置图标 - 对话图标
        return PluginIcon.builtin("SP_MessageBoxInformation")

    @property
    def skill_description(self) -> str:
        """技能简短描述"""
        return "LLM 智能对话"

    @property
    def tags(self) -> list:
        """插件标签"""
        return ["AI", "LLM", "对话", "多模态"]

    @property
    def plugin_type_id(self) -> str:
        """插件类型标识符"""
        return "llm-chat"
