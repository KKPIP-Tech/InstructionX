"""
测试共享工具函数

提供创建临时插件、配置文件的工厂函数，供各测试模块使用。
"""
import json
from pathlib import Path


def create_minimal_plugin(
    plugin_dir: Path,
    plugin_name: str = "TestPlugin",
    has_service: bool = False,
    service_methods: list = None,
    has_information: bool = False,
):
    """
    在指定目录创建最小有效的测试插件。

    Args:
        plugin_dir: 插件目录（应已存在）
        plugin_name: 插件类名和插件名
        has_service: 是否创建 service.py
        service_methods: service.py 中的方法名列表
        has_information: 是否创建 information.py
    """
    plugin_dir.mkdir(parents=True, exist_ok=True)

    # entrance.py — 必需的入口文件
    entrance = f'''
from core.plugin.plugin_interface import IPlugin
from PySide6.QtWidgets import QWidget, QLabel

class {plugin_name}(IPlugin):
    @property
    def plugin_name(self) -> str:
        return "{plugin_name}"

    def _create_widget(self, parent=None, data_provider=None) -> QWidget:
        from PySide6.QtWidgets import QWidget
        w = QWidget(parent)
        lbl = QLabel("{plugin_name} content", w)
        return w

plugin = {plugin_name}()
'''
    (plugin_dir / "entrance.py").write_text(entrance.lstrip())
    (plugin_dir / "__init__.py").write_text("")

    if has_service and service_methods:
        sigs = {
            "echo": 'def echo(self, text): return text',
            "upper": 'def upper(self, text): return text.upper()',
        }
        svc_methods = "\n    ".join(
            sigs.get(m, f"def {m}(self): pass")
            for m in service_methods
        )
        svc_code = f'''
class Service:
    {svc_methods}
'''
        (plugin_dir / "service.py").write_text(svc_code.lstrip())

    if has_information and service_methods:
        method = service_methods[0]
        info_code = f'''
from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon

class {plugin_name}Info(IPluginInfo):
    @property
    def version(self): return PluginVersion.from_string("release.1.0.0")
    @property
    def developer(self): return "TestDev"
    @property
    def developer_email(self): return "test@test.com"
    @property
    def developer_website(self): return "https://test.com"
    @property
    def is_free(self): return True
    @property
    def description(self): return "Test plugin description"
    @property
    def service_api(self):
        return {{
            "{method}": {{
                "description": "Test method",
                "parameters": {{"text": {{"type": "str", "description": "input", "required": True}}}},
                "returns": {{"type": "str", "description": "output"}}
            }}
        }}
    @property
    def skill_icon(self): return PluginIcon.none()
    @property
    def skill_description(self): return "Test skill"
    @property
    def plugin_type_id(self): return "test-plugin-type"
'''
        (plugin_dir / "information.py").write_text(info_code.lstrip())


def write_config_json(path: Path, data: dict) -> None:
    """
    将 dict 以 JSON 格式原子写入文件。

    Args:
        path: 文件路径（父目录应已存在）
        data: 要写入的字典数据
    """
    import os
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    os.replace(tmp, path)
