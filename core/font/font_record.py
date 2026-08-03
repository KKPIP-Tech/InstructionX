"""字体记录数据模型。

每条 FontRecord 对应一个经框架安装到 ``data/fonts/`` 的字体文件，
记录其 Qt 家族名、样式名与来源信息，持久化于 ``data/fonts/fonts.json``。
"""

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True, slots=True)
class FontRecord:
    """一条已安装字体的注册记录。

    Attributes:
        font_id: 字体标识（字体文件名去扩展名，安装时由文件名生成）
        family: Qt 字体家族名（注册后从 QFontDatabase 读取的真实名称）
        style: 字体样式名（如 Regular / Bold）
        filename: ``data/fonts/`` 目录下的字体文件名
        source: 安装来源（``"user"`` 表示用户在字体管理窗口安装，
            插件安装时为插件 id）
        installed_at: 安装时间（ISO 8601 字符串）
    """

    font_id: str
    family: str
    style: str
    filename: str
    source: str
    installed_at: str

    def to_dict(self) -> Dict[str, Any]:
        """序列化为可 JSON 写入的字典。"""
        return {
            "font_id": self.font_id,
            "family": self.family,
            "style": self.style,
            "filename": self.filename,
            "source": self.source,
            "installed_at": self.installed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FontRecord":
        """从字典反序列化（注册表记录）。

        Args:
            data: 注册表中的单条字体记录

        Returns:
            FontRecord 实例

        Raises:
            KeyError: 必需字段缺失时
        """
        return cls(
            font_id=data["font_id"],
            family=data["family"],
            style=data["style"],
            filename=data["filename"],
            source=data["source"],
            installed_at=data["installed_at"],
        )
