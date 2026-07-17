"""
插件版本号管理模块
提供版本号解析、比较和格式化功能
"""

from enum import Enum
from typing import Tuple
from dataclasses import dataclass
from functools import total_ordering


class VersionType(Enum):
    """版本类型枚举"""
    RELEASE = "release"
    PRE_RELEASE = "pre-release"
    BETA = "beta"
    ALPHA = "alpha"
    INTERNAL = "internal"
    
    # 优先级排序（数字越大优先级越高）
    def get_priority(self) -> int:
        """获取版本类型优先级"""
        priority_map = {
            VersionType.INTERNAL: 1,
            VersionType.ALPHA: 2,
            VersionType.BETA: 3,
            VersionType.PRE_RELEASE: 4,
            VersionType.RELEASE: 5
        }
        return priority_map[self]
    
    def get_display_name(self) -> str:
        """获取版本类型的显示名称"""
        display_map = {
            VersionType.RELEASE: "正式版",
            VersionType.PRE_RELEASE: "预发布版",
            VersionType.BETA: "测试版",
            VersionType.ALPHA: "内测版",
            VersionType.INTERNAL: "内部版"
        }
        return display_map[self]


@total_ordering
@dataclass(frozen=True)
class PluginVersion:
    """
    插件版本号类
    格式: <版本类型>.<大版本号>.<分支版本号>.<小版本号>
    示例: release.1.0.0
    """
    version_type: VersionType
    major: int
    minor: int
    patch: int
    
    @classmethod
    def from_string(cls, version_str: str) -> 'PluginVersion':
        """
        从字符串解析版本号
        
        Args:
            version_str: 版本字符串，如 "release.1.0.0"
            
        Returns:
            PluginVersion 实例
            
        Raises:
            ValueError: 版本格式无效时抛出异常
        """
        parts = version_str.split('.')
        if len(parts) != 4:
            raise ValueError(
                f"Invalid version format: {version_str}. "
                f"Expected format: <version_type>.<major>.<minor>.<patch>, "
                f"e.g., 'release.1.0.0'"
            )
        
        try:
            version_type = VersionType(parts[0].lower())
            major = int(parts[1])
            minor = int(parts[2])
            patch = int(parts[3])
            
            if major < 0 or minor < 0 or patch < 0:
                raise ValueError("Version numbers must be non-negative")
            
            return cls(version_type, major, minor, patch)
        except ValueError as e:
            if "is not a valid" in str(e):
                raise ValueError(
                    f"Invalid version type: {parts[0]}. "
                    f"Must be one of: {', '.join([vt.value for vt in VersionType])}"
                ) from e
            raise
    
    def to_string(self) -> str:
        """
        将版本号转换为字符串
        
        Returns:
            版本字符串
        """
        return f"{self.version_type.value}.{self.major}.{self.minor}.{self.patch}"
    
    def __str__(self) -> str:
        return self.to_string()
    
    def __repr__(self) -> str:
        return f"PluginVersion('{self.to_string()}')"
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, PluginVersion):
            return False
        return (
            self.version_type == other.version_type and
            self.major == other.major and
            self.minor == other.minor and
            self.patch == other.patch
        )
    
    def __lt__(self, other) -> bool:
        """比较版本号大小"""
        if not isinstance(other, PluginVersion):
            return NotImplemented
        
        # 先比较版本类型优先级
        if self.version_type != other.version_type:
            return self.version_type.get_priority() < other.version_type.get_priority()
        
        # 版本类型相同，比较数字部分
        if self.major != other.major:
            return self.major < other.major
        if self.minor != other.minor:
            return self.minor < other.minor
        return self.patch < other.patch
    
    # __le__/__gt__/__ge__ 由 functools.total_ordering 根据 __eq__/__lt__ 自动派生，
    # 对非 PluginVersion 类型一致地传播 NotImplemented/TypeError
    
    def get_display_version(self) -> str:
        """
        获取用于显示的版本号（带中文类型）
        
        Returns:
            格式化的版本显示字符串，如 "正式版 1.0.0"
        """
        return f"{self.version_type.get_display_name()} {self.major}.{self.minor}.{self.patch}"