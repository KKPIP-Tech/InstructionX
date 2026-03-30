"""
文本格式化插件元数据
"""

from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon
from typing import Dict, Any, Optional


class TextFormattingPluginInfo(IPluginInfo):
    """文本格式化插件元数据"""
    
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
        文本格式化插件提供常用的文本处理工具，包括：
        - 文本大小写转换（大写、小写）
        - 支持批量文本处理
        
        该插件适用于需要快速格式化文本的场景，
        如数据处理、内容编辑等。
        """
    
    @property
    def service_api(self) -> Dict[str, Any]:
        return {
            "to_uppercase": {
                "description": "将文本转换为大写",
                "parameters": {
                    "text": {
                        "type": "str",
                        "description": "输入文本",
                        "required": True
                    }
                },
                "returns": {
                    "type": "str",
                    "description": "大写后的文本"
                }
            },
            "to_lowercase": {
                "description": "将文本转换为小写",
                "parameters": {
                    "text": {
                        "type": "str",
                        "description": "输入文本",
                        "required": True
                    }
                },
                "returns": {
                    "type": "str",
                    "description": "小写后的文本"
                }
            }
        }
    
    @property
    def skill_icon(self) -> PluginIcon:
        return PluginIcon.builtin("SP_ArrowForward")
    
    @property
    def skill_description(self) -> str:
        return "提供文本格式化工具"
    
    @property
    def tags(self) -> Optional[list[str]]:
        return ["text", "formatting", "utility"]
    
    @property
    def dependencies(self) -> Optional[Dict[str, str]]:
        return None

    @property
    def plugin_type_id(self) -> str:
        """插件类型标识符"""
        return "text-formatting"