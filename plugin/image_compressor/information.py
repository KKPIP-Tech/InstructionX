"""
图片压缩插件元数据
"""

from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon
from typing import Dict, Any, Optional


class ImageCompressorPluginInfo(IPluginInfo):
    """图片压缩插件元数据"""
    
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
        图片压缩插件提供图片处理工具，包括：
        - 图片压缩（支持调整质量参数）
        - 获取图片信息（文件大小等）
        
        该插件适用于需要优化图片大小的场景，
        如网站优化、存储节省、传输加速等。
        """
    
    @property
    def service_api(self) -> Dict[str, Any]:
        return {
            "compress_image": {
                "description": "压缩图片",
                "parameters": {
                    "file_path": {
                        "type": "str",
                        "description": "图片文件路径",
                        "required": True
                    },
                    "quality": {
                        "type": "int",
                        "description": "压缩质量 (1-100)，默认85",
                        "required": False,
                        "default": 85
                    }
                },
                "returns": {
                    "type": "bool",
                    "description": "是否成功"
                }
            },
            "get_image_info": {
                "description": "获取图片信息",
                "parameters": {
                    "file_path": {
                        "type": "str",
                        "description": "图片文件路径",
                        "required": True
                    }
                },
                "returns": {
                    "type": "dict",
                    "description": "图片信息字典，包含file_path, file_size, file_size_str"
                }
            }
        }
    
    @property
    def skill_icon(self) -> PluginIcon:
        return PluginIcon.builtin("SP_MessageBoxWarning")
    
    @property
    def skill_description(self) -> str:
        return "提供图片压缩工具"
    
    @property
    def tags(self) -> Optional[list[str]]:
        return ["image", "compression", "utility"]
    
    @property
    def dependencies(self) -> Optional[Dict[str, str]]:
        return None

    @property
    def plugin_type_id(self) -> str:
        """插件类型标识符"""
        return "image-compressor"