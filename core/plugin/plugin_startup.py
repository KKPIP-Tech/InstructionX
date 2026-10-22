"""插件启动准备与失败诊断。

负责在导入插件入口前读取 ``IXPlugin.json``、检查并自动安装声明的
Python 依赖，并以结构化对象向界面层报告无法继续加载的原因。
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Dict, Optional, Tuple

from core.i18n import DEFAULT_LANGUAGE, resolve_i18n_field
from utils.logging_tools import LoggerManager, get_name

from .dependency_manager import DependencyManager


DESCRIPTOR_FILE = "IXPlugin.json"
ENTRANCE_FILE = "entrance.py"
IDENTITY_FILE = ".plugin_info.json"
DEFAULT_PLUGIN_VERSION = "release.0.0.0"

FAILURE_DEPENDENCY_CHECK = "dependency_check_failed"
FAILURE_DEPENDENCY_INSTALL = "dependency_install_failed"
FAILURE_INVALID_ENTRY = "invalid_plugin_entry"
FAILURE_MISSING_MODULE = "missing_module"
FAILURE_IMPORT = "import_failed"
FAILURE_UNEXPECTED = "unexpected_error"


@dataclass(frozen=True, slots=True)
class PluginDescriptorSnapshot:
    """启动阶段需要的插件描述信息快照。"""

    descriptor_id: str
    name: str
    version: str
    dependencies: Dict[str, str]


@dataclass(frozen=True, slots=True)
class PluginDependencyPreparation:
    """插件启动依赖准备结果。"""

    ready: bool
    reason: str = ""
    detail: str = ""
    missing_dependencies: Tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PluginLoadFailure:
    """无法加载插件时供界面展示的结构化信息。"""

    plugin_name: str
    plugin_dir: Path
    reason: str
    detail: str = ""
    missing_dependencies: Tuple[str, ...] = ()
    missing_module: str = ""


def is_plugin_candidate(plugin_dir: Path) -> bool:
    """判断顶层目录是否代表一个插件，而不是普通资源目录。

    仓库根目录中的 ``docs``、``assets`` 等文件夹可能被用户整体复制到
    ``plugin/`` 下。仅当目录包含插件描述、入口或身份文件时才进入加载与
    失败诊断流程，避免启动时产生误报。

    Args:
        plugin_dir: ``plugin/`` 或 ``custom_plugin/`` 下的直接子目录。

    Returns:
        目录具备插件特征时返回 ``True``。
    """
    return any(
        (plugin_dir / filename).is_file()
        for filename in (DESCRIPTOR_FILE, ENTRANCE_FILE, IDENTITY_FILE)
    )


def read_plugin_descriptor(plugin_dir: Path) -> Optional[PluginDescriptorSnapshot]:
    """读取插件目录中的 ``IXPlugin.json``。

    文件缺失时返回 ``None``，以兼容尚未提供描述文件的旧插件；文件损坏
    时记录警告并返回 ``None``，后续入口导入失败会形成用户可见的失败项。

    Args:
        plugin_dir: 插件目录。

    Returns:
        描述信息快照；文件不存在或无法解析时返回 ``None``。
    """
    descriptor_file = plugin_dir / DESCRIPTOR_FILE
    if not descriptor_file.is_file():
        return None
    try:
        with open(descriptor_file, "r", encoding="utf-8") as stream:
            raw = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        LoggerManager().warning(
            get_name(), f"读取插件描述文件失败 {descriptor_file}: {exc}")
        return None
    if not isinstance(raw, dict):
        LoggerManager().warning(
            get_name(), f"插件描述文件根节点不是对象: {descriptor_file}")
        return None
    raw_name = resolve_i18n_field(
        raw.get("name", plugin_dir.name), DEFAULT_LANGUAGE)
    return PluginDescriptorSnapshot(
        descriptor_id=str(raw.get("id") or plugin_dir.name),
        name=str(raw_name or plugin_dir.name),
        version=str(raw.get("version") or DEFAULT_PLUGIN_VERSION),
        dependencies=_normalize_dependencies(raw.get("dependencies", {})),
    )


def _normalize_dependencies(raw_dependencies: object) -> Dict[str, str]:
    """把描述文件依赖归一化为 ``{包名: 版本约束}``。"""
    if not isinstance(raw_dependencies, dict):
        LoggerManager().warning(
            get_name(), "IXPlugin.json 的 dependencies 不是对象，已忽略")
        return {}
    dependencies: Dict[str, str] = {}
    for package, constraint in raw_dependencies.items():
        if not isinstance(package, str) or not isinstance(constraint, str):
            LoggerManager().warning(
                get_name(),
                f"忽略非法插件依赖项: {package!r}: {constraint!r}",
            )
            continue
        dependencies[package] = constraint
    return dependencies


class PluginDependencyPreparer:
    """在插件导入前检查并安装其声明的 Python 依赖。"""

    def __init__(self, dependency_manager: Optional[DependencyManager] = None):
        """初始化依赖准备器。

        Args:
            dependency_manager: 可选的依赖管理器，供测试注入；默认新建。
        """
        self._dependency_manager = dependency_manager or DependencyManager()
        self._logger = LoggerManager()

    def prepare(
        self, descriptor: Optional[PluginDescriptorSnapshot]
    ) -> PluginDependencyPreparation:
        """确保插件声明的依赖已经安装。

        Args:
            descriptor: 插件描述快照；``None`` 表示旧插件没有描述文件。

        Returns:
            依赖准备结果。失败时包含缺失包与可供界面展示的原因。
        """
        if descriptor is None or not descriptor.dependencies:
            return PluginDependencyPreparation(ready=True)
        check_result = self._check(descriptor)
        if not check_result.ready:
            return check_result
        if check_result.missing_dependencies:
            return self._install(descriptor, check_result.missing_dependencies)
        return check_result

    def _check(
        self, descriptor: PluginDescriptorSnapshot
    ) -> PluginDependencyPreparation:
        """检查依赖并捕获检查阶段的异常。"""
        try:
            result = self._dependency_manager.check_dependencies(
                descriptor.dependencies)
        except Exception as exc:
            return PluginDependencyPreparation(
                ready=False,
                reason=FAILURE_DEPENDENCY_CHECK,
                detail=str(exc),
            )
        if result.satisfied:
            return PluginDependencyPreparation(ready=True)
        return PluginDependencyPreparation(
            ready=True,
            missing_dependencies=tuple(result.missing),
        )

    def _install(
        self,
        descriptor: PluginDescriptorSnapshot,
        missing: Tuple[str, ...],
    ) -> PluginDependencyPreparation:
        """安装缺失依赖，并在安装后重新验证。"""
        self._logger.info(
            get_name(),
            f"插件 {descriptor.descriptor_id} 启动前缺少依赖: {', '.join(missing)}",
        )
        result = self._dependency_manager.install_dependencies(
            descriptor.dependencies, callback=self._log_progress)
        if not result.success:
            return PluginDependencyPreparation(
                ready=False,
                reason=FAILURE_DEPENDENCY_INSTALL,
                detail=result.message,
                missing_dependencies=missing,
            )
        return self._verify_after_install(descriptor, missing)

    def _verify_after_install(
        self,
        descriptor: PluginDescriptorSnapshot,
        previous_missing: Tuple[str, ...],
    ) -> PluginDependencyPreparation:
        """安装后重新检查依赖并转换为最终结果。"""
        try:
            verification = self._dependency_manager.check_dependencies(
                descriptor.dependencies)
        except Exception as exc:
            return PluginDependencyPreparation(
                ready=False,
                reason=FAILURE_DEPENDENCY_CHECK,
                detail=str(exc),
                missing_dependencies=previous_missing,
            )
        if verification.satisfied:
            self._logger.info(
                get_name(),
                f"插件 {descriptor.descriptor_id} 启动依赖已准备完成",
            )
            return PluginDependencyPreparation(ready=True)
        return PluginDependencyPreparation(
            ready=False,
            reason=FAILURE_DEPENDENCY_INSTALL,
            detail="安装完成后依赖检查仍未通过",
            missing_dependencies=tuple(verification.missing),
        )

    @staticmethod
    def _log_progress(message: str) -> None:
        """记录依赖安装进度。"""
        LoggerManager().info(get_name(), f"插件启动依赖: {message}")
