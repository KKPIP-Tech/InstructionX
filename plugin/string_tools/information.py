"""
字符串工具插件元数据
"""

from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon
from typing import Dict, Any, List

class StringToolsPluginInfo(IPluginInfo):
    """字符串工具插件元数据"""
    
    @property
    def version(self) -> PluginVersion:
        """插件版本"""
        return PluginVersion.from_string("release.1.0.0")
    
    @property
    def developer(self) -> str:
        """开发者名称"""
        return "KKPIP-Tech"
    
    @property
    def developer_email(self) -> str:
        """开发者邮箱"""
        return "support@example.com"
    
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
        字符串工具插件提供丰富的文本处理功能，包括：
        - 文本大小写转换（大写、小写）
        - 文本反转
        - 单词首字母大写
        - 单词统计
        - 字符统计
        - 移除空白字符
        
        该插件提供了多个 API 方法，可以被其他插件调用，
        用于处理各种字符串操作。
        
        示例使用场景：
        - 文本格式化工具
        - 数据清洗
        - 内容编辑
        - 自动化文本处理
        """
    
    @property
    def service_api(self) -> Dict[str, Any]:
        """Service API 定义"""
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
            },
            "reverse_text": {
                "description": "反转文本",
                "parameters": {
                    "text": {
                        "type": "str",
                        "description": "输入文本",
                        "required": True
                    }
                },
                "returns": {
                    "type": "str",
                    "description": "反转后的文本"
                }
            },
            "capitalize_words": {
                "description": "将每个单词的首字母大写",
                "parameters": {
                    "text": {
                        "type": "str",
                        "description": "输入文本",
                        "required": True
                    }
                },
                "returns": {
                    "type": "str",
                    "description": "首字母大写的文本"
                }
            },
            "count_words": {
                "description": "统计单词数量",
                "parameters": {
                    "text": {
                        "type": "str",
                        "description": "输入文本",
                        "required": True
                    }
                },
                "returns": {
                    "type": "int",
                    "description": "单词数量"
                }
            },
            "count_chars": {
                "description": "统计字符数量",
                "parameters": {
                    "text": {
                        "type": "str",
                        "description": "输入文本",
                        "required": True
                    },
                    "include_spaces": {
                        "type": "bool",
                        "description": "是否包含空格",
                        "required": False,
                        "default": True
                    }
                },
                "returns": {
                    "type": "int",
                    "description": "字符数量"
                }
            },
            "remove_whitespace": {
                "description": "移除所有空白字符",
                "parameters": {
                    "text": {
                        "type": "str",
                        "description": "输入文本",
                        "required": True
                    }
                },
                "returns": {
                    "type": "str",
                    "description": "移除空白后的文本"
                }
            }
        }
    
    @property
    def skill_icon(self) -> PluginIcon:
        """插件图标配置"""
        return PluginIcon.builtin("SP_ArrowForward")
    
    @property
    def skill_description(self) -> str:
        """插件简短描述"""
        return "提供字符串处理工具"
    
    @property
    def tags(self) -> List[str]:
        """插件标签"""
        return ["text", "string", "formatting", "utility"]
    
    @property
    def dependencies(self) -> None:
        """依赖项"""
        return None

    @property
    def plugin_type_id(self) -> str:
        """插件类型标识符"""
        return "string-tools"
