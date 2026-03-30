"""
颜色转换插件元数据
"""

from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon
from typing import Dict, Any, Optional


class ColorConverterPluginInfo(IPluginInfo):
    """颜色转换插件元数据"""
    
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
        颜色转换插件提供颜色格式转换工具，包括：
        - HEX 颜色转 RGB 格式
        
        该插件适用于需要在不同颜色格式之间转换的场景，
        如设计工作、开发调试、颜色管理等。
        """
    
    @property
    def service_api(self) -> Dict[str, Any]:
        return {
            "hex_to_rgb": {
                "description": "将 HEX 颜色格式转换为 RGB 格式",
                "parameters": {
                    "hex_str": {
                        "type": "str",
                        "description": "HEX 颜色字符串（如 #FF5733 或 FF5733）",
                        "required": True
                    }
                },
                "returns": {
                    "type": "str",
                    "description": "RGB 格式字符串（如 rgb(255, 87, 51)），如果格式无效则返回错误信息"
                }
            }
        }
    
    @property
    def skill_icon(self) -> PluginIcon:
        return PluginIcon.builtin("SP_ArrowForward")
    
    @property
    def skill_description(self) -> str:
        return "提供颜色转换工具"
    
    @property
    def tags(self) -> Optional[list[str]]:
        return ["color", "conversion", "utility"]
    
    @property
    def dependencies(self) -> Optional[Dict[str, str]]:
        return None

    @property
    def plugin_type_id(self) -> str:
        """插件类型标识符"""
        return "color-converter"