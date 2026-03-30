"""
代码格式化插件元数据
"""

from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon
from typing import Dict, Any, Optional


class CodeFormatterPluginInfo(IPluginInfo):
    """代码格式化插件元数据"""
    
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
        代码格式化插件提供常用的代码处理工具，包括：
        - JSON 格式化
        - XML 格式化
        - 移除代码注释（支持 Python 和 JavaScript）
        - 代码压缩（移除空白字符）
        
        该插件适用于需要快速处理代码的场景，
        如代码审查、数据清理、内容优化等。
        """
    
    @property
    def service_api(self) -> Dict[str, Any]:
        return {
            "format_json": {
                "description": "格式化JSON字符串",
                "parameters": {
                    "json_str": {
                        "type": "str",
                        "description": "JSON字符串",
                        "required": True
                    }
                },
                "returns": {
                    "type": "str",
                    "description": "格式化后的JSON字符串"
                }
            },
            "format_xml": {
                "description": "格式化XML字符串",
                "parameters": {
                    "xml_str": {
                        "type": "str",
                        "description": "XML字符串",
                        "required": True
                    }
                },
                "returns": {
                    "type": "str",
                    "description": "格式化后的XML字符串"
                }
            },
            "remove_comments": {
                "description": "移除代码注释",
                "parameters": {
                    "code": {
                        "type": "str",
                        "description": "代码字符串",
                        "required": True
                    },
                    "language": {
                        "type": "str",
                        "description": "编程语言（python, javascript）",
                        "required": True
                    }
                },
                "returns": {
                    "type": "str",
                    "description": "移除注释后的代码"
                }
            },
            "compress_code": {
                "description": "压缩代码（移除空白字符）",
                "parameters": {
                    "code": {
                        "type": "str",
                        "description": "代码字符串",
                        "required": True
                    }
                },
                "returns": {
                    "type": "str",
                    "description": "压缩后的代码"
                }
            }
        }
    
    @property
    def skill_icon(self) -> PluginIcon:
        return PluginIcon.builtin("SP_ArrowDown")
    
    @property
    def skill_description(self) -> str:
        return "提供代码格式化工具"
    
    @property
    def tags(self) -> Optional[list[str]]:
        return ["code", "formatting", "utility"]
    
    @property
    def dependencies(self) -> Optional[Dict[str, str]]:
        return None

    @property
    def plugin_type_id(self) -> str:
        """插件类型标识符"""
        return "code-formatter"