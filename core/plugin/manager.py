
"""
插件管理器

提供插件的加载、注册、查询、排序和 API 调用功能。
采用单例模式确保全局只有一个管理器实例。
"""

import os
import sys
import shutil
import inspect
import traceback
import importlib
import importlib.util
from enum import Enum
from pathlib import Path
from typing import List, Dict, Optional, Any, Callable, Tuple
from unittest.mock import MagicMock

from core.interfaces import IPlugin
from core.data import DataProvider
from core.task import BackgroundTaskManager
from .config_manager import PluginConfigManager
from .plugin_identity import PluginIdentity
from .plugin_info_interface import IPluginInfo
from .plugin_registry import PluginRegistry
from .plugin_groups import PluginGroup, PluginGroupStore
from core.interfaces.plugin_services import PluginServices
from core.interfaces.i_llm_service import ILLMService
from core.font import get_font_manager

# re-export：保持 `core.plugin.manager.sanitize_tool_name` 引用路径兼容
from .tool_name import sanitize_tool_name  # noqa: F401

from utils.logging_tools import LoggerManager, get_name


def get_plugin_manager() -> "PluginManager":
    """获取插件管理器单例实例

    Returns:
        PluginManager: 插件管理器单例实例
    """
    return PluginManager()


class PluginAPI:
    """插件 API 信息容器"""

    def __init__(self, plugin_id: str, plugin_name: str, plugin_type: str):
        self.plugin_id = plugin_id
        self.plugin_name = plugin_name
        self.plugin_type = plugin_type
        self.api_methods: Dict[str, Callable] = {}
        self.api_descriptions: Dict[str, Dict[str, Any]] = {}


class PluginManager:
    """
    插件管理器（单例模式）

    核心功能：
    - 动态加载官方插件和第三方插件
    - 维护插件注册表和名称映射
    - 提供插件 API 注册和跨插件调用
    - 管理插件显示顺序配置

    单例访问方式：PluginManager()
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        """单例模式：确保全局只有一个实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """初始化插件管理器（仅执行一次）"""
        if PluginManager._initialized:
            return

        PluginManager._initialized = True
        self._official_plugins: List[IPlugin] = []
        self._thirdparty_plugins: List[IPlugin] = []
        self._plugin_registry: Dict[str, IPlugin] = {}  # plugin_id -> plugin
        self._plugin_name_to_id: Dict[str, str] = {}    # plugin_name -> plugin_id

        # API 注册表：存储插件暴露的方法
        self._api_registry: Dict[str, PluginAPI] = {}

        # 插件目录路径
        self.official_plugin_dir = Path(__file__).parent.parent.parent / "plugin"
        self.thirdparty_plugin_dir = Path(__file__).parent.parent.parent / "custom_plugin"

        # 配置管理器
        self.config_manager = PluginConfigManager()

        # 已安装插件注册表（版本/来源，用于升级降级）
        self.registry = PluginRegistry()

        # 用户自定义分组存储
        self.group_store = PluginGroupStore()

        # 日志管理器
        self._logger = LoggerManager()

    def _create_plugin_services(self) -> PluginServices:
        """创建插件服务依赖注入容器

        创建包含所有核心服务的 PluginServices 对象，
        供插件在构造器和 on_plugin_loaded 回调中使用。

        Returns:
            PluginServices: 服务容器实例
        """
        # NOTE: 函数级导入用于打破 core.plugin ↔ core.llm/mcp 循环依赖，待 P2 事件化重构后移除
        from core.llm import get_llm_plugin_service
        try:
            data_provider = DataProvider()
        except Exception:
            data_provider = None

        try:
            task_manager = BackgroundTaskManager()
        except Exception:
            task_manager = None

        logger = LoggerManager()

        return PluginServices(
            llm_facade=get_llm_plugin_service(),
            data_provider=data_provider,
            task_manager=task_manager,
            logger=logger,
            mcp_manager=self._get_mcp_manager(),
            mcp_client=self._get_mcp_client(),
            font_manager=get_font_manager(),
        )

    def _get_mcp_manager(self) -> Any:
        """获取 MCPManager 单例"""
        try:
            # NOTE: 函数级导入用于打破 core.plugin ↔ core.llm/mcp 循环依赖，待 P2 事件化重构后移除
            from core.mcp import get_mcp_manager
            return get_mcp_manager()
        except Exception:
            return None

    def _get_mcp_client(self) -> Any:
        """获取 MCPClientManager 实例"""
        try:
            # NOTE: 函数级导入用于打破 core.plugin ↔ core.llm/mcp 循环依赖，待 P2 事件化重构后移除
            from core.mcp import get_mcp_manager
            from core.llm import get_llm_plugin_service
            mcp_mgr = get_mcp_manager()
            tool_registry = get_llm_plugin_service().get_shared_tool_registry()
            return mcp_mgr.get_client_manager(tool_registry)
        except Exception:
            return None

    def load_plugins(self):
        """加载所有插件（包括官方插件和第三方插件），并回填版本注册表"""
        self.load_official_plugins()
        self.load_thirdparty_plugins()
        self._backfill_registry()

    def _backfill_registry(self) -> None:
        """扫描已加载插件，为注册表中缺失记录的插件回填版本信息"""
        entries: List[Tuple[str, str, Path]] = []
        for plugin in self._official_plugins:
            entries.append((plugin.plugin_id, "official", plugin._plugin_dir))
        for plugin in self._thirdparty_plugins:
            entries.append((plugin.plugin_id, "thirdparty", plugin._plugin_dir))
        try:
            self.registry.backfill(entries)
        except Exception as e:
            # 回填失败不影响插件加载主流程
            self._logger.warning(get_name(), f'插件注册表回填失败: {e}')

    def load_official_plugins(self) -> List[IPlugin]:
        """
        扫描并加载 plugin 目录下的所有官方插件

        Returns:
            已加载的官方插件列表
        """
        self._official_plugins.clear()

        if not self.official_plugin_dir.exists():
            # 不做 mkdir 写副作用，仅记录日志并返回空列表
            self._logger.debug(get_name(), f'Official plugin dir not found: {self.official_plugin_dir}')
            return self._official_plugins

        # 遍历目录，加载每个子目录中的插件
        for plugin_path in self.official_plugin_dir.iterdir():
            if plugin_path.is_dir() and not plugin_path.name.startswith('_'):
                plugin = self._load_plugin_from_directory(plugin_path)
                if plugin:
                    self._official_plugins.append(plugin)

        return self._official_plugins

    def load_thirdparty_plugins(self) -> List[IPlugin]:
        """
        扫描并加载 custom_plugin 目录下的所有第三方插件

        Returns:
            已加载的第三方插件列表
        """
        self._thirdparty_plugins.clear()

        if not self.thirdparty_plugin_dir.exists():
            # 不做 mkdir 写副作用，仅记录日志并返回空列表
            self._logger.debug(get_name(), f'Thirdparty plugin dir not found: {self.thirdparty_plugin_dir}')
            return self._thirdparty_plugins

        # 遍历目录，加载每个子目录中的插件
        for plugin_path in self.thirdparty_plugin_dir.iterdir():
            if plugin_path.is_dir() and not plugin_path.name.startswith('_'):
                plugin = self._load_plugin_from_directory(plugin_path)
                if plugin:
                    self._thirdparty_plugins.append(plugin)

        return self._thirdparty_plugins

    def _load_plugin_from_directory(self, plugin_dir: Path) -> Optional[IPlugin]:
        """
        从指定目录动态加载插件

        加载流程：
        1. 检查并创建 __init__.py 使目录成为 Python 包
        2. 动态导入 entrance.py 模块
        3. 查找并实例化继承自 IPlugin 的类
        4. 生成或加载插件唯一标识符
        5. 调用插件生命周期回调

        Args:
            plugin_dir: 插件目录路径

        Returns:
            插件实例，加载失败时返回 None
        """
        try:
            # 检查入口文件是否存在
            entrance_file = plugin_dir / "entrance.py"

            if not entrance_file.exists():
                self._logger.warning(get_name(), f'No entrance.py found in {plugin_dir}')
                return None

            # 确保插件目录有 __init__.py 文件
            init_file = plugin_dir / "__init__.py"
            if not init_file.exists():
                init_file.write_text("")

            # 将插件目录添加到 Python 模块搜索路径
            parent_dir = str(plugin_dir.parent)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)

            # 动态导入 entrance.py 模块
            module_name = f"{plugin_dir.name}.entrance"
            spec = importlib.util.spec_from_file_location(module_name, entrance_file)
            if spec is None or spec.loader is None:
                self._logger.warning(get_name(), f'Could not load spec for {entrance_file}')
                return None

            # 设置包上下文
            module = importlib.util.module_from_spec(spec)
            module.__package__ = plugin_dir.name
            module.__path__ = [str(plugin_dir)]

            sys.modules[module_name] = module
            sys.modules[plugin_dir.name] = importlib.import_module(plugin_dir.name)

            spec.loader.exec_module(module)

            # 在模块中查找 IPlugin 的子类
            # 排除：core.interfaces.IPlugin（框架基类）和 core.plugin.plugin_interface.IPlugin（中间基类）
            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (not isinstance(attr, type) or not issubclass(attr, IPlugin)):
                    continue
                # 排除框架级 IPlugin 类（来自 core.interfaces 或 core.plugin.plugin_interface）
                if attr is IPlugin:
                    continue
                if getattr(attr, '__module__', '') == 'core.plugin.plugin_interface':
                    continue
                plugin_class = attr
                break

            if plugin_class is None:
                self._logger.warning(get_name(), f'No IPlugin subclass found in {entrance_file}')
                return None

            # 生成或加载唯一标识符
            identity = PluginIdentity(plugin_dir)
            plugin_id = identity.load_or_create_id()

            # 创建插件服务依赖注入容器
            services = self._create_plugin_services()

            # 实例化插件（尝试注入 services）
            sig = inspect.signature(plugin_class)
            params = [p.name for p in sig.parameters.values()]
            if 'services' in params:
                plugin_instance = plugin_class(services=services)
            else:
                plugin_instance = plugin_class()

            plugin_instance._plugin_dir = plugin_dir  # 用于 _load_plugin_info() 直接定位文件
            plugin_instance._plugin_id = plugin_id
            plugin_instance._services = services  # 注入 services 以实例属性方式访问

            # 调用插件加载完成回调（不传参数保证向后兼容旧插件）
            plugin_instance.on_plugin_loaded()

            # 维护注册表映射
            plugin_instance._plugin_name = plugin_instance.plugin_name
            if (plugin_instance.plugin_name in self._plugin_name_to_id and
                    self._plugin_name_to_id[plugin_instance.plugin_name] != plugin_id):
                self._logger.warning(
                    get_name(),
                    f'Duplicate plugin name "{plugin_instance.plugin_name}": '
                    f'{self._plugin_name_to_id[plugin_instance.plugin_name]} overwritten by {plugin_id}'
                )
            self._plugin_registry[plugin_id] = plugin_instance
            self._plugin_name_to_id[plugin_instance.plugin_name] = plugin_id

            # 尝试自动注册插件 API
            self._auto_register_plugin_api(plugin_dir, plugin_id)

            return plugin_instance

        except Exception as e:
            self._logger.error(
                get_name(),
                f'Error loading plugin from {plugin_dir}: {e}\n{traceback.format_exc()}'
            )
            return None
    
    def get_official_plugins(self) -> List[IPlugin]:
        """获取所有官方插件实例列表"""
        return self._official_plugins.copy()

    def get_thirdparty_plugins(self) -> List[IPlugin]:
        """获取所有第三方插件实例列表"""
        return self._thirdparty_plugins.copy()

    def get_all_plugins(self) -> List[IPlugin]:
        """获取所有已加载的插件（官方 + 第三方）"""
        return self._official_plugins + self._thirdparty_plugins

    def get_plugin_by_name(self, name: str) -> Optional[IPlugin]:
        """
        通过插件名称查询插件实例

        Args:
            name: 插件名称

        Returns:
            插件实例，未找到时返回 None
        """
        plugin_id = self._plugin_name_to_id.get(name)
        if plugin_id is None:
            return None
        return self._plugin_registry.get(plugin_id)

    def reload_plugins(self):
        """重新加载所有插件（先完整卸载旧实例，再重新扫描目录）"""
        for plugin in list(self._plugin_registry.values()):
            self._unload_plugin_instance(plugin)
        self._official_plugins.clear()
        self._thirdparty_plugins.clear()
        self._plugin_registry.clear()
        self._plugin_name_to_id.clear()
        self._api_registry.clear()
        self.load_plugins()

    def _unload_plugin_instance(self, plugin: IPlugin) -> None:
        """卸载单个插件实例的运行时状态

        依次执行：生命周期回调 → API/MCP 注销 → 缓存 Widget 销毁 → sys.modules 清理。
        各步骤独立容错，单步失败不阻断后续清理。

        Args:
            plugin: 待卸载的插件实例
        """
        plugin_id = plugin.plugin_id
        # 1. 生命周期回调，让插件自行释放资源（订阅、定时器等）
        try:
            plugin.on_plugin_unloaded()
        except Exception as e:
            self._logger.warning(get_name(), f'插件 {plugin_id} on_plugin_unloaded 执行失败: {e}')
        # 2. 注销跨插件 API 并同步移除 MCP 工具
        if plugin_id:
            self.unregister_plugin_api(plugin_id)
        # 3. 销毁缓存的 Widget（必须在 GUI 线程调用，失败仅记录）
        self._destroy_cached_widget(plugin)
        # 4. 清理 sys.modules 中的插件模块，保证重载时拿到新代码
        plugin_dir = getattr(plugin, '_plugin_dir', None)
        if plugin_dir is not None:
            self._remove_plugin_sys_modules(plugin_dir.name)

    def _destroy_cached_widget(self, plugin: IPlugin) -> None:
        """销毁插件缓存的 Widget 并清空缓存引用"""
        widget = getattr(plugin, '_cached_widget', None)
        if widget is None:
            return
        try:
            widget.hide()
            widget.deleteLater()
        except Exception as e:
            self._logger.warning(get_name(), f'销毁插件缓存 Widget 失败: {e}')
        plugin._cached_widget = None
        plugin._cached_parent = None

    def _remove_plugin_sys_modules(self, dir_name: str) -> None:
        """从 sys.modules 移除插件相关模块

        覆盖三种命名形态：
        - {dir_name} 及其子模块（entrance 加载路径）
        - plugin.{dir_name}.* / custom_plugin.{dir_name}.*（API 自动注册路径）

        Args:
            dir_name: 插件目录名
        """
        prefix = f"{dir_name}."
        infix = f".{dir_name}."
        for mod_name in list(sys.modules):
            if mod_name == dir_name or mod_name.startswith(prefix) or infix in mod_name:
                sys.modules.pop(mod_name, None)

    def get_plugin_by_id(self, plugin_id: str) -> Optional[IPlugin]:
        """
        通过唯一标识符查询插件实例

        Args:
            plugin_id: 插件 UUID

        Returns:
            插件实例，未找到时返回 None
        """
        return self._plugin_registry.get(plugin_id)

    def get_plugin_id_by_name(self, plugin_name: str) -> Optional[str]:
        """
        通过插件名称查询其唯一标识符

        Args:
            plugin_name: 插件名称

        Returns:
            UUID 字符串，未找到时返回 None
        """
        return self._plugin_name_to_id.get(plugin_name)

    def get_plugin_id_by_type_id(self, plugin_type_id: str) -> Optional[str]:
        """
        通过插件类型标识符查询其唯一标识符

        Args:
            plugin_type_id: 插件类型标识符（如 "string-tools"）

        Returns:
            UUID 字符串，未找到时返回 None
        """
        for plugin in self._plugin_registry.values():
            try:
                plugin_info = plugin.plugin_info
                if plugin_info and plugin_info.plugin_type_id == plugin_type_id:
                    return plugin.plugin_id
            except Exception:
                continue
        return None

    def get_plugin_by_type_id(self, plugin_type_id: str) -> Optional[IPlugin]:
        """
        通过插件类型标识符查询插件实例

        Args:
            plugin_type_id: 插件类型标识符

        Returns:
            插件实例，未找到时返回 None
        """
        plugin_id = self.get_plugin_id_by_type_id(plugin_type_id)
        if plugin_id is None:
            return None
        return self._plugin_registry.get(plugin_id)

    def register_plugin(self, plugin: IPlugin, is_official: bool = False):
        """
        手动注册插件到管理器

        Args:
            plugin: 插件实例
            is_official: 是否属于官方插件
        """
        plugin_id = plugin.plugin_id
        if not plugin_id:
            plugin_id = plugin.plugin_name
        # 重复注册检查：同 plugin_id 已注册时先注销旧的再注册，避免重复 append
        old_plugin = self._plugin_registry.get(plugin_id)
        if old_plugin is not None:
            self._logger.warning(
                get_name(),
                f'Plugin id "{plugin_id}" already registered, replacing old instance'
            )
            old_name = getattr(old_plugin, 'plugin_name', None)
            if old_name:
                self.unregister_plugin(old_name)
            else:
                self._plugin_registry.pop(plugin_id, None)
                # 旧实例 plugin_name 为 None 时 unregister_plugin 无法按名称清理，
                # 需显式从官方/第三方插件列表移除，避免残留失效实例
                if old_plugin in self._official_plugins:
                    self._official_plugins.remove(old_plugin)
                if old_plugin in self._thirdparty_plugins:
                    self._thirdparty_plugins.remove(old_plugin)
        self._plugin_registry[plugin_id] = plugin
        self._plugin_name_to_id[plugin.plugin_name] = plugin_id
        if is_official:
            self._official_plugins.append(plugin)
        else:
            self._thirdparty_plugins.append(plugin)

    def unregister_plugin(self, plugin_name: str):
        """
        从管理器中移除插件

        Args:
            plugin_name: 插件名称
        """
        plugin_id = self._plugin_name_to_id.get(plugin_name)
        if not plugin_id:
            return
        plugin = self._plugin_registry.pop(plugin_id, None)
        self._plugin_name_to_id.pop(plugin_name, None)
        if plugin:
            if plugin in self._official_plugins:
                self._official_plugins.remove(plugin)
            if plugin in self._thirdparty_plugins:
                self._thirdparty_plugins.remove(plugin)

    # ==================== 插件卸载 ====================

    def uninstall_plugin(self, plugin_id: str, remove_data: bool = False) -> Dict[str, Any]:
        """完整卸载指定插件

        流程：运行时卸载 → 注册表移除 → 删除插件目录 → 清理 UUID 文件 →
        清理排序/分组/版本注册表 → 可选删除插件数据。
        各步骤独立容错，尽可能多的清理项会被执行。

        Args:
            plugin_id: 插件 UUID
            remove_data: 为 True 时同时删除 DataProvider 中的插件数据

        Returns:
            {"success": bool, "message": str, "warnings": List[str]}
        """
        plugin = self._plugin_registry.get(plugin_id)
        if plugin is None:
            return {"success": False, "message": "插件不存在或未加载", "warnings": []}

        plugin_name = plugin.plugin_name
        plugin_dir = getattr(plugin, '_plugin_dir', None)
        warnings: List[str] = []
        self._logger.info(get_name(), f'开始卸载插件: {plugin_name} ({plugin_id})')

        # 1. 运行时卸载（生命周期回调、API/MCP、Widget、sys.modules）
        self._unload_plugin_instance(plugin)

        # 2. 从注册表与列表移除
        self._plugin_registry.pop(plugin_id, None)
        self._plugin_name_to_id.pop(plugin_name, None)
        if plugin in self._official_plugins:
            self._official_plugins.remove(plugin)
        if plugin in self._thirdparty_plugins:
            self._thirdparty_plugins.remove(plugin)

        # 3. 删除插件目录
        if plugin_dir is not None and plugin_dir.exists():
            try:
                shutil.rmtree(plugin_dir)
            except OSError as e:
                warnings.append(f"删除插件目录失败: {e}")
                self._logger.error(get_name(), f'删除插件目录失败 {plugin_dir}: {e}')

        # 4. 清理 UUID 持久化文件
        if plugin_dir is not None:
            PluginIdentity(plugin_dir).delete()

        # 5. 清理排序、分组与版本注册表
        self._remove_from_order_config(plugin_id)
        self.group_store.remove_plugin(plugin_id)
        self.registry.remove(plugin_id)

        # 6. 可选删除插件持久化数据
        if remove_data:
            self._remove_plugin_data(plugin_id, warnings)

        self._logger.info(get_name(), f'插件卸载完成: {plugin_name} ({plugin_id})')
        return {"success": True, "message": f"插件 {plugin_name} 已卸载", "warnings": warnings}

    def _remove_from_order_config(self, plugin_id: str) -> None:
        """从 plugin_order.json 中移除指定插件 UUID"""
        config = self.config_manager.load_plugin_order()
        changed = False
        for key in ("official_plugins", "thirdparty_plugins"):
            if plugin_id in config[key]:
                config[key] = [pid for pid in config[key] if pid != plugin_id]
                changed = True
        if changed:
            self.config_manager.save_plugin_order(
                config["official_plugins"], config["thirdparty_plugins"]
            )

    def _remove_plugin_data(self, plugin_id: str, warnings: List[str]) -> None:
        """删除 DataProvider 中的插件数据，失败时记录警告"""
        try:
            provider = DataProvider()
            # 插件从未在 DataProvider 注册（未写入过数据）时无数据可删；
            # unregister_plugin 对未注册插件会抛错，此处先检查存在性
            if provider.get_plugin_info(plugin_id) is None:
                self._logger.debug(
                    get_name(), f'插件 {plugin_id} 无持久化数据，跳过数据删除'
                )
                return
            provider.unregister_plugin(plugin_id)
        except Exception as e:
            warnings.append(f"删除插件数据失败: {e}")
            self._logger.error(get_name(), f'删除插件数据失败 {plugin_id}: {e}')

    # ==================== 自定义分组与排序 ====================

    def get_groups(self, scope: str) -> List[PluginGroup]:
        """获取指定 scope 的用户自定义分组列表

        Args:
            scope: "official" 或 "thirdparty"

        Returns:
            PluginGroup 列表（顺序即显示顺序）
        """
        return self.group_store.load(scope)

    def save_groups(self, scope: str, groups: List[PluginGroup],
                    order: Optional[List[tuple]] = None) -> bool:
        """保存指定 scope 的分组配置与面板统一顺序

        Args:
            scope: "official" 或 "thirdparty"
            groups: PluginGroup 列表
            order: 面板统一顺序 [("group"|"plugin", id), ...]，
                   None 时保留已有顺序（新分组追加在后）

        Returns:
            保存是否成功
        """
        return self.group_store.save(scope, groups, order)

    def get_sorted_plugins(self, scope: str) -> List[tuple]:
        """按面板统一顺序（分组与未分组插件混排）返回渲染序列

        Args:
            scope: "official" 或 "thirdparty"

        Returns:
            渲染项列表，每项为：
            - ("group", PluginGroup, [插件实例...])：一个分组及其组内插件
            - ("plugin", 插件实例)：未分组插件
        """
        plugins = self._official_plugins if scope == "official" else self._thirdparty_plugins
        by_id = {p.plugin_id: p for p in plugins if p.plugin_id}
        groups_by_id = {g.id: g for g in self.group_store.load(scope)}

        result: List[tuple] = []
        assigned = set()   # 已分配进分组的插件 UUID
        emitted = set()    # 已输出的分组 ID / 插件 UUID
        for item_type, item_id in self.group_store.load_order(scope):
            if item_type == "group":
                group = groups_by_id.get(item_id)
                if group is not None and item_id not in emitted:
                    members = [by_id[pid] for pid in group.plugins if pid in by_id]
                    assigned.update(p.plugin_id for p in members)
                    emitted.add(item_id)
                    result.append(("group", group, members))
            elif item_id in by_id and item_id not in assigned and item_id not in emitted:
                emitted.add(item_id)
                result.append(("plugin", by_id[item_id]))

        result.extend(self._get_tail_items(scope, groups_by_id, by_id, assigned, emitted))
        return result

    def _get_tail_items(self, scope: str, groups_by_id: Dict[str, PluginGroup],
                        by_id: Dict[str, IPlugin], assigned: set,
                        emitted: set) -> List[tuple]:
        """收集未出现在面板顺序中的分组与插件，追加在末尾

        分组按保存顺序、插件按 plugin_order.json 顺序追加（新插件排最后）。
        """
        tail: List[tuple] = []
        for group in groups_by_id.values():
            if group.id in emitted:
                continue
            members = [by_id[pid] for pid in group.plugins if pid in by_id]
            assigned.update(p.plugin_id for p in members)
            emitted.add(group.id)
            tail.append(("group", group, members))

        for plugin in self._get_ungrouped_plugins(scope, by_id, assigned):
            if plugin.plugin_id not in emitted:
                emitted.add(plugin.plugin_id)
                tail.append(("plugin", plugin))
        return tail

    def _get_ungrouped_plugins(self, scope: str, by_id: Dict[str, IPlugin],
                               assigned: set) -> List[IPlugin]:
        """获取未分组插件，按 plugin_order.json 顺序排列，新插件追加在后"""
        order_key = "official_plugins" if scope == "official" else "thirdparty_plugins"
        order = self.config_manager.load_plugin_order().get(order_key, [])

        ungrouped: List[IPlugin] = []
        seen = set()
        for pid in order:
            plugin = by_id.get(pid)
            if plugin is not None and pid not in assigned:
                ungrouped.append(plugin)
                seen.add(pid)
        for pid, plugin in by_id.items():
            if pid not in assigned and pid not in seen:
                ungrouped.append(plugin)
        return ungrouped

    def apply_custom_order(self):
        """从配置文件加载并应用用户自定义的插件显示顺序"""
        config = self.config_manager.load_plugin_order()

        # 对官方插件按照配置文件的 UUID 顺序排序
        if config["official_plugins"]:
            ordered_plugins = []
            for plugin_id in config["official_plugins"]:
                plugin = self._plugin_registry.get(plugin_id)
                if plugin and plugin in self._official_plugins:
                    ordered_plugins.append(plugin)

            # 追加未在配置中的新增插件
            for plugin in self._official_plugins:
                if plugin not in ordered_plugins:
                    ordered_plugins.append(plugin)

            self._official_plugins = ordered_plugins

        # 对第三方插件按照配置文件的 UUID 顺序排序
        if config["thirdparty_plugins"]:
            ordered_plugins = []
            for plugin_id in config["thirdparty_plugins"]:
                plugin = self._plugin_registry.get(plugin_id)
                if plugin and plugin in self._thirdparty_plugins:
                    ordered_plugins.append(plugin)

            # 追加未在配置中的新增插件
            for plugin in self._thirdparty_plugins:
                if plugin not in ordered_plugins:
                    ordered_plugins.append(plugin)

            self._thirdparty_plugins = ordered_plugins

    def save_plugin_order(self, official_plugin_ids: List[str], thirdparty_plugin_ids: List[str]) -> bool:
        """
        将插件显示顺序持久化到配置文件

        Args:
            official_plugin_ids: 官方插件 UUID 列表
            thirdparty_plugin_ids: 第三方插件 UUID 列表

        Returns:
            保存操作是否成功
        """
        return self.config_manager.save_plugin_order(official_plugin_ids, thirdparty_plugin_ids)

    def get_official_plugin_ids(self) -> List[str]:
        """获取当前顺序下所有官方插件的 UUID 列表"""
        return [plugin.plugin_id for plugin in self._official_plugins if plugin.plugin_id]

    def get_thirdparty_plugin_ids(self) -> List[str]:
        """获取当前顺序下所有第三方插件的 UUID 列表"""
        return [plugin.plugin_id for plugin in self._thirdparty_plugins if plugin.plugin_id]

    # ==================== API 管理功能 ====================

    def _auto_register_plugin_api(self, plugin_dir: Path, plugin_id: str) -> None:
        """
        自动扫描并注册插件的公开方法作为 API

        扫描插件目录下的 information.py 和 service.py 文件，
        从 information.py 获取 API 方法描述，从 service.py 获取实际方法引用。

        Args:
            plugin_dir: 插件目录路径
            plugin_id: 插件唯一标识符
        """
        try:
            # 检查必要文件是否存在
            info_file = plugin_dir / "information.py"
            if not info_file.exists():
                return

            service_file = plugin_dir / "service.py"
            if not service_file.exists():
                return

            # 动态导入模块
            module_name = plugin_dir.name
            parent_pkg = plugin_dir.parent.name  # e.g. "plugin"
            info_mod_name = f"{parent_pkg}.{module_name}.information"
            svc_mod_name = f"{parent_pkg}.{module_name}.service"

            # 确保父目录在搜索路径中
            grandparent_dir = str(plugin_dir.parent.parent)
            if grandparent_dir not in sys.path:
                sys.path.insert(0, grandparent_dir)

            try:
                # 确保父包（如 plugin/__init__.py）已导入
                if parent_pkg not in sys.modules:
                    importlib.import_module(parent_pkg)

                # 使用 importlib.reload 获取最新定义
                if info_mod_name in sys.modules:
                    info_module = importlib.reload(sys.modules[info_mod_name])
                else:
                    info_module = importlib.import_module(info_mod_name)

                if svc_mod_name in sys.modules:
                    service_module = importlib.reload(sys.modules[svc_mod_name])
                else:
                    service_module = importlib.import_module(svc_mod_name)
            except Exception as e:
                self._logger.warning(get_name(), f'Skipping API registration ({plugin_dir.name}): {e}')
                return

            # 获取 PluginInfo 类
            plugin_info_class = None
            for attr_name in dir(info_module):
                attr = getattr(info_module, attr_name)
                if (isinstance(attr, type) and
                    issubclass(attr, IPluginInfo) and
                    attr is not IPluginInfo):
                    plugin_info_class = attr
                    break

            if not plugin_info_class:
                self._logger.warning(get_name(), f'Skipping API registration ({plugin_dir.name}): no IPluginInfo subclass found')
                return

            # 实例化 PluginInfo
            plugin_info = plugin_info_class()

            # 获取 service_api 方法描述
            api_descriptions = plugin_info.service_api
            if not api_descriptions:
                self._logger.warning(get_name(), f'Skipping API registration ({plugin_dir.name}): service_api is empty')
                return

            # 获取 Service 类
            # 优先查找名称以 "Service" 结尾的类，其次取第一个候选
            service_class = None
            for attr_name in dir(service_module):
                attr = getattr(service_module, attr_name)
                if not isinstance(attr, type):
                    continue
                if attr.__name__ in ('IPlugin', 'object'):
                    continue
                if attr.__name__.endswith('Info') or attr.__name__ == 'PluginInfo':
                    continue
                if attr.__module__ == 'typing':
                    continue
                if issubclass(attr, Enum):
                    continue
                # 优先选择名称以 Service 结尾的类
                if attr.__name__.endswith('Service'):
                    service_class = attr
                    break
                # 否则记录候选
                if service_class is None:
                    service_class = attr

            if not service_class:
                self._logger.warning(get_name(), f'Skipping API registration ({plugin_dir.name}): no Service class found')
                return

            # 实例化 Service（优先使用真实单例 DataProvider/TaskManager，
            # 仅在核心服务不可用（如测试环境）时回退为 MagicMock）
            # NOTE: 函数级导入用于打破 core.plugin ↔ core.llm/mcp 循环依赖，待 P2 事件化重构后移除
            from core.llm import get_llm_plugin_service

            try:
                mock_dp = DataProvider()
            except Exception:
                mock_dp = MagicMock()

            real_llm = get_llm_plugin_service()

            try:
                mock_ts = BackgroundTaskManager()
            except Exception:
                mock_ts = MagicMock()

            service_instance = self._instantiate_service(
                service_class, plugin_id, mock_dp, real_llm, mock_ts
            )

            if service_instance is None:
                self._logger.warning(get_name(), f'Skipping API registration ({plugin_dir.name}): cannot instantiate Service class')
                return

            # 注册 API 方法
            self.register_plugin_api(plugin_id, service_instance, api_descriptions)

        except Exception as e:
            self._logger.error(get_name(), f'API auto registration failed: {e}')

    def _instantiate_service(
        self,
        service_class: type,
        plugin_id: str,
        data_provider: Any,
        llm_service: ILLMService,
        task_manager: Any,
    ) -> Optional[Any]:
        """实例化 Service 类

        先用 inspect.signature 分析构造函数可接受的位置参数个数，
        直接选择匹配的参数组合，避免试错法掩盖构造函数内部的 TypeError；
        仅当签名分析失败（如内置类型/C 扩展）时才回退为逐个尝试。

        保持以下 5 种组合的兼容顺序（参数从多到少）：
        (plugin_id, dp, llm, ts) → (plugin_id, dp, llm) → (plugin_id, dp) → (plugin_id,) → ()
        """
        candidates = [
            (plugin_id, data_provider, llm_service, task_manager),
            (plugin_id, data_provider, llm_service),
            (plugin_id, data_provider),
            (plugin_id,),
            (),
        ]

        try:
            sig = inspect.signature(service_class)
        except (TypeError, ValueError):
            sig = None

        if sig is not None:
            # 统计构造函数可接受的位置参数个数范围
            positional_kinds = (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
            params = list(sig.parameters.values())
            has_var_positional = any(
                p.kind == inspect.Parameter.VAR_POSITIONAL for p in params
            )
            max_positional = sum(1 for p in params if p.kind in positional_kinds)
            min_positional = sum(
                1 for p in params
                if p.kind in positional_kinds and p.default is inspect.Parameter.empty
            )

            for args in candidates:
                argc = len(args)
                if argc < min_positional:
                    continue  # 参数不足，必然 TypeError
                if not has_var_positional and argc > max_positional:
                    continue  # 参数过多，必然 TypeError
                try:
                    return service_class(*args)
                except TypeError as e:
                    # 签名匹配的调用仍抛 TypeError，说明是构造函数内部错误，不再降级掩盖
                    self._logger.warning(
                        get_name(),
                        f'Service constructor raised TypeError with {argc} args (signature matched): {e}'
                    )
                    return None
            return None

        # 签名分析失败，回退为逐个尝试（保持原有兼容行为）
        for args in candidates:
            try:
                return service_class(*args)
            except TypeError:
                continue
        return None

    def register_plugin_api(self,
                          plugin_id: str,
                          service_instance: Any,
                          api_descriptions: Dict[str, Dict[str, Any]]) -> None:
        """
        注册插件的公开方法到 API 注册表

        Args:
            plugin_id: 插件唯一标识符
            service_instance: Service 类实例
            api_descriptions: API 方法描述字典（来自 information.py 的 service_api）
        """
        # 获取插件信息
        plugin = self.get_plugin_by_id(plugin_id)
        if not plugin:
            raise ValueError(f"插件 {plugin_id} 不存在")

        # 创建 API 容器
        plugin_api = PluginAPI(
            plugin_id=plugin_id,
            plugin_name=plugin.plugin_name,
            plugin_type=plugin.__class__.__name__
        )

        # 遍历方法描述，绑定实际方法到 API 容器
        # 过滤私有方法（以下划线开头）
        for method_name, desc in api_descriptions.items():
            # 跳过私有方法
            if method_name.startswith('_'):
                continue
            if hasattr(service_instance, method_name):
                method = getattr(service_instance, method_name)
                if callable(method):
                    plugin_api.api_methods[method_name] = method
                    plugin_api.api_descriptions[method_name] = desc

        # 存入注册表
        self._api_registry[plugin_id] = plugin_api

        # 通知 MCP 系统有新工具注册
        self._notify_mcp_new_tools(plugin_id, api_descriptions)

    def _notify_mcp_new_tools(
        self,
        plugin_id: str,
        api_descriptions: Dict[str, Dict[str, Any]],
    ) -> None:
        """通知 MCP 系统有新插件工具注册

        工具命名规则与 get_all_function_tools() 一致：
        sanitize_tool_name(f"{plugin_id}__{method_name}")，符合 OpenAI function 命名规范。
        回调链路不受影响：MCP 侧仍按原始 (plugin_id, method_name) 元组回调
        call_plugin_method()。
        """
        try:
            mcp_mgr = self._get_mcp_manager()
            if mcp_mgr is None:
                return
            for method_name, desc in api_descriptions.items():
                # 工具名规范（供 MCP 侧对齐）：sanitize_tool_name(f"{plugin_id}__{method_name}")。
                # 此处仍传原始 (plugin_id, method_name)，由 MCP 桥接层组装并净化工具名，
                # 回调链路 call_plugin_method() 始终使用原始元组，不受影响。
                mcp_mgr.sync_plugin_tool(
                    plugin_id=plugin_id,
                    method_name=method_name,
                    description=desc.get("description", ""),
                    parameters={
                        "type": "object",
                        "properties": {
                            k: {
                                "type": v.get("type", "string"),
                                "description": v.get("description", ""),
                                **({"default": v["default"]} if "default" in v else {}),
                            }
                            for k, v in desc.get("parameters", {}).items()
                        },
                        "required": [
                            k for k, v in desc.get("parameters", {}).items()
                            if v.get("required", False)
                        ],
                    },
                )
        except Exception as e:
            # MCP 系统可能未初始化，仅记录告警不影响插件注册
            self._logger.warning(get_name(), f'Failed to notify MCP new tools for {plugin_id}: {e}')
            
    def unregister_plugin_api(self, plugin_id: str) -> None:
        """
        移除插件的 API 注册

        Args:
            plugin_id: 插件唯一标识符
        """
        if plugin_id in self._api_registry:
            # 通知 MCP 系统注销工具
            self._notify_mcp_remove_tools(plugin_id)
            del self._api_registry[plugin_id]

    def _notify_mcp_remove_tools(self, plugin_id: str) -> None:
        """通知 MCP 系统移除插件工具"""
        try:
            mcp_mgr = self._get_mcp_manager()
            if mcp_mgr is None:
                return
            if plugin_id in self._api_registry:
                for method_name in self._api_registry[plugin_id].api_methods:
                    mcp_mgr.remove_plugin_tool(plugin_id, method_name)
        except Exception as e:
            # MCP 系统可能未初始化，仅记录告警
            self._logger.warning(get_name(), f'Failed to notify MCP remove tools for {plugin_id}: {e}')

    def get_plugin_api(self, plugin_id: str) -> Optional[Dict[str, Any]]:
        """
        获取指定插件的 API 信息

        Args:
            plugin_id: 插件唯一标识符

        Returns:
            包含插件 ID、名称、类型和方法的字典，不存在时返回 None
        """
        plugin_api = self._api_registry.get(plugin_id)
        if not plugin_api:
            return None

        return {
            "plugin_id": plugin_api.plugin_id,
            "plugin_name": plugin_api.plugin_name,
            "plugin_type": plugin_api.plugin_type,
            "methods": list(plugin_api.api_methods.keys()),
            "descriptions": plugin_api.api_descriptions
        }

    def get_all_apis(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有已注册的插件 API

        Returns:
            以插件 ID 为键的 API 信息字典
        """
        result = {}
        for plugin_id, plugin_api in self._api_registry.items():
            result[plugin_id] = {
                "plugin_id": plugin_api.plugin_id,
                "plugin_name": plugin_api.plugin_name,
                "plugin_type": plugin_api.plugin_type,
                "methods": list(plugin_api.api_methods.keys()),
                "descriptions": plugin_api.api_descriptions
            }
        return result

    def call_plugin_method(self,
                         caller_id: str,
                         plugin_id: str,
                         method_name: str,
                         **kwargs) -> Any:
        """
        跨插件调用方法

        允许一个插件通过唯一标识符调用另一个插件的公开方法。
        用于实现插件间的功能协作。

        Args:
            caller_id: 调用方插件的唯一标识符（用于日志记录）
            plugin_id: 目标插件的唯一标识符
            method_name: 要调用的方法名
            **kwargs: 传递给目标方法的参数

        Returns:
            方法的返回值

        Raises:
            ValueError: 目标插件或方法不存在时抛出
            RuntimeError: 方法执行失败时抛出
        """
        plugin_api = self._api_registry.get(plugin_id)

        if plugin_api is None:
            raise ValueError(f"插件 {plugin_id} 未注册 API")

        if method_name not in plugin_api.api_methods:
            available = ", ".join(plugin_api.api_methods.keys())
            raise ValueError(f"插件 {plugin_id} 没有方法 '{method_name}'。可用方法: {available}")

        method = plugin_api.api_methods[method_name]

        self._logger.debug(
            get_name(),
            f'Plugin method call: caller={caller_id} -> {plugin_id}.{method_name}'
        )

        try:
            # 执行方法调用
            return method(**kwargs)
        except Exception as e:
            raise RuntimeError(f"调用插件 {plugin_id} 的方法 {method_name} 失败: {e}") from e

    def get_api_description(self,
                         plugin_id: str,
                         method_name: Optional[str] = None) -> Dict[str, Any]:
        """
        获取 API 的结构化描述（适用于 MCP 或函数工具）

        Args:
            plugin_id: 插件唯一标识符
            method_name: 可选，指定方法名。None 时返回所有方法的描述

        Returns:
            API 描述字典，包含方法名、参数、返回值等信息
        """
        plugin_api = self._api_registry.get(plugin_id)

        if plugin_api is None:
            return {}

        if method_name is None:
            # 返回所有方法的描述
            return {
                name: {
                    "plugin_id": plugin_id,
                    "plugin_name": plugin_api.plugin_name,
                    "plugin_type": plugin_api.plugin_type,
                    "description": desc.get("description", ""),
                    "parameters": desc.get("parameters", {}),
                    "returns": desc.get("returns", {})
                }
                for name, desc in plugin_api.api_descriptions.items()
            }
        else:
            # 返回指定方法的描述
            desc = plugin_api.api_descriptions.get(method_name)
            if desc is None:
                return {}

            return {
                "plugin_id": plugin_id,
                "plugin_name": plugin_api.plugin_name,
                "plugin_type": plugin_api.plugin_type,
                "name": method_name,
                "description": desc.get("description", ""),
                "parameters": desc.get("parameters", {}),
                "returns": desc.get("returns", {})
            }

    def get_all_function_tools(self) -> List[Dict[str, Any]]:
        """
        获取所有可用的函数工具（适用于 MCP 集成）

        将所有插件 API 转换为符合 MCP/OpenAI 函数调用规范的格式。

        Returns:
            函数工具列表，每个元素包含类型、函数名、描述和参数定义
        """

        tools = []

        for plugin_id, plugin_api in self._api_registry.items():
            for method_name, desc in plugin_api.api_descriptions.items():
                # 提取必需参数
                parameters = desc.get("parameters", {})
                required_params = [
                    k for k, v in parameters.items()
                    if v.get("required", False)
                ]

                tool = {
                    "type": "function",
                    "function": {
                        # OpenAI function 名只允许 [a-zA-Z0-9_-]，最长 64 字符；
                        # 使用 `__` 作为 plugin_id 与 method_name 的分隔符再整体净化。
                        # 注意：call_plugin_method() 仍使用原始 (plugin_id, method_name) 调用，不受影响
                        "name": sanitize_tool_name(f"{plugin_id}__{method_name}"),
                        "description": f"[{plugin_api.plugin_name}] {desc.get('description', '')}",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                k: {
                                    "type": v.get("type", "string"),
                                    "description": v.get("description", ""),
                                    **({"default": v["default"]} if "default" in v else {}),
                                }
                                for k, v in parameters.items()
                            },
                            "required": required_params
                        }
                    }
                }
                tools.append(tool)

        return tools
