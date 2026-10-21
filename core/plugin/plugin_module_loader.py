"""插件入口模块与插件类的发现逻辑。

该模块只负责导入 ``entrance.py`` 并定位 ``IPlugin`` 子类，不处理插件
实例化、服务注入或注册表更新，以便启动流程按职责拆分。
"""

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Type

from core.interfaces import IPlugin

from .plugin_startup import (
    FAILURE_IMPORT,
    FAILURE_INVALID_ENTRY,
    FAILURE_MISSING_MODULE,
)


class PluginModuleLoadError(Exception):
    """插件入口模块加载失败。"""

    def __init__(
        self,
        reason: str,
        detail: str,
        missing_module: str = "",
    ) -> None:
        """保存结构化加载失败原因。"""
        super().__init__(detail)
        self.reason = reason
        self.detail = detail
        self.missing_module = missing_module


class PluginModuleLoader:
    """导入插件入口并定位其 ``IPlugin`` 实现类。"""

    def load(self, plugin_dir: Path) -> Type[IPlugin]:
        """加载指定插件目录中的插件类。

        Args:
            plugin_dir: 插件目录。

        Returns:
            继承自 ``IPlugin`` 的具体插件类。

        Raises:
            PluginModuleLoadError: 入口不存在、导入失败或找不到插件类。
        """
        entrance_file = self._require_entrance(plugin_dir)
        module = self._import_entrance(plugin_dir, entrance_file)
        plugin_class = self._find_plugin_class(module)
        if plugin_class is None:
            raise PluginModuleLoadError(
                FAILURE_INVALID_ENTRY,
                f"{entrance_file} 中未找到 IPlugin 子类",
            )
        return plugin_class

    @staticmethod
    def _require_entrance(plugin_dir: Path) -> Path:
        """确认入口文件存在并返回其路径。"""
        entrance_file = plugin_dir / "entrance.py"
        if entrance_file.is_file():
            return entrance_file
        raise PluginModuleLoadError(
            FAILURE_INVALID_ENTRY,
            f"插件目录缺少 entrance.py: {plugin_dir}",
        )

    def _import_entrance(self, plugin_dir: Path, entrance_file: Path):
        """导入插件入口模块并转换为结构化错误。"""
        try:
            return self._execute_entrance(plugin_dir, entrance_file)
        except PluginModuleLoadError:
            raise
        except ModuleNotFoundError as exc:
            raise PluginModuleLoadError(
                FAILURE_MISSING_MODULE,
                str(exc),
                missing_module=exc.name or "",
            ) from exc
        except Exception as exc:
            raise PluginModuleLoadError(FAILURE_IMPORT, str(exc)) from exc

    @staticmethod
    def _execute_entrance(plugin_dir: Path, entrance_file: Path):
        """在插件包上下文中执行入口文件。"""
        init_file = plugin_dir / "__init__.py"
        if not init_file.exists():
            init_file.write_text("", encoding="utf-8")
        parent_dir = str(plugin_dir.parent)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        module_name = f"{plugin_dir.name}.entrance"
        spec = importlib.util.spec_from_file_location(module_name, entrance_file)
        if spec is None or spec.loader is None:
            raise PluginModuleLoadError(
                FAILURE_INVALID_ENTRY,
                f"无法创建入口模块 spec: {entrance_file}",
            )
        module = importlib.util.module_from_spec(spec)
        module.__package__ = plugin_dir.name
        module.__path__ = [str(plugin_dir)]
        sys.modules[module_name] = module
        sys.modules[plugin_dir.name] = importlib.import_module(plugin_dir.name)
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _find_plugin_class(module) -> Type[IPlugin] | None:
        """在入口模块中定位第一个具体 ``IPlugin`` 子类。"""
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if not isinstance(attr, type) or not issubclass(attr, IPlugin):
                continue
            if attr is IPlugin:
                continue
            if getattr(attr, "__module__", "") == "core.plugin.plugin_interface":
                continue
            return attr
        return None
