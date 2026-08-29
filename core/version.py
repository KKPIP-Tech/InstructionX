"""InstructionX 框架版本信息（单一来源）

VERSION 常量是版本号的唯一事实来源:pyproject.toml 通过
tool.setuptools.dynamic 以 AST 静态解析方式读取它,
APP_VERSION 也由它解析得到,修改版本号只需改动此处。
"""

from core.plugin.plugin_version import PluginVersion, VersionType

VERSION = "1.0.5"

_MAJOR, _MINOR, _PATCH = (int(part) for part in VERSION.split("."))

APP_VERSION = PluginVersion(VersionType.ALPHA, _MAJOR, _MINOR, _PATCH)


def get_instructionx_version_string() -> str:
    """获取 InstructionX 框架版本字符串，如 'Alpha 1.0.5'"""
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
    """获取带'版本'前缀的 InstructionX 框架显示字符串，如 '版本 Alpha 1.0.5'"""
    return f"版本 {get_instructionx_version_string()}"
