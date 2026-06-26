"""InstructionX 框架版本信息（单一来源）"""

from core.plugin.plugin_version import PluginVersion, VersionType

APP_VERSION = PluginVersion(VersionType.ALPHA, 1, 0, 2)


def get_instructionx_version_string() -> str:
    """获取 InstructionX 框架版本字符串，如 'Alpha 1.0.2'"""
    type_map = {
        VersionType.ALPHA: "Alpha",
        VersionType.BETA: "Beta",
        VersionType.PRE_RELEASE: "Pre-release",
        VersionType.RELEASE: "",
        VersionType.INTERNAL: "Internal",
    }
    prefix = type_map.get(APP_VERSION.version_type, "")
    version_num = f"{APP_VERSION.major}.{APP_VERSION.minor}.{APP_VERSION.patch}"
    return f"{prefix} {version_num}" if prefix else version_num


def get_instructionx_version_display() -> str:
    """获取带'版本'前缀的 InstructionX 框架显示字符串，如 '版本 Alpha 1.0.2'"""
    return f"版本 {get_instructionx_version_string()}"
