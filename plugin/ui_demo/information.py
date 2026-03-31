"""
UI 控件演示插件元数据
"""

from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon
from typing import Dict, Any, Optional


class UiDemoPluginInfo(IPluginInfo):
    """UI 控件演示插件元数据"""

    @property
    def version(self) -> PluginVersion:
        return PluginVersion.from_string("release.1.0.0")

    @property
    def developer(self) -> str:
        return "InstructionX"

    @property
    def developer_email(self) -> str:
        return "support@example.com"

    @property
    def developer_website(self) -> str:
        return "https://github.com/InstructionX"

    @property
    def is_free(self) -> bool:
        return True

    @property
    def description(self) -> str:
        return """
        UI 控件演示插件用于展示所有控件效果。
        包含按钮、输入框、复选框、单选按钮、滑块、进度条、
        菜单、工具栏、标签页、列表、表格等常用控件的演示。
        """

    @property
    def service_api(self) -> Dict[str, Any]:
        return {
            "get_control_list": {
                "description": "获取所有可演示的控件列表",
                "parameters": {},
                "returns": {
                    "type": "list",
                    "description": "控件列表"
                }
            }
        }

    @property
    def skill_icon(self) -> PluginIcon:
        return PluginIcon.builtin("SP_DesktopIcon")

    @property
    def skill_description(self) -> str:
        return "展示所有控件"

    @property
    def tags(self) -> Optional[list[str]]:
        return ["ui", "demo", "controls"]

    @property
    def dependencies(self) -> Optional[Dict[str, str]]:
        return None

    @property
    def plugin_type_id(self) -> str:
        """插件类型标识符"""
        return "ui-demo"
