"""LLM 预设目录包

该包承载随程序发布的只读目录数据：提供商预设元数据（provider_presets）、
预设模型目录（model_presets）与厂商 Logo 资源（logos/）。
目录层提供默认值与元数据，用户配置层在运行时继承并覆写。

使用示例:
    >>> from core.llm.catalog import get_provider_preset, get_preset_logo_path
    >>> preset = get_provider_preset("glm")
    >>> print(preset.default_base_url)
    >>> logo = get_preset_logo_path("glm")
"""

from pathlib import Path
from typing import Optional

from .provider_presets import CUSTOM_ADAPTER, PROVIDER_PRESETS, ProviderPreset
from .model_presets import PRESET_MODELS


# 厂商 Logo 资源目录（catalog/logos/）
LOGO_DIR = Path(__file__).resolve().parent / "logos"


def get_provider_preset(preset_id: str) -> Optional[ProviderPreset]:
    """按预设 ID 查询提供商预设元数据

    Args:
        preset_id: 预设唯一标识（如 "openai" / "siliconflow"）

    Returns:
        Optional[ProviderPreset]: 预设元数据，不存在时返回 None
    """
    return PROVIDER_PRESETS.get(preset_id)


def get_preset_logo_path(preset_id: str) -> Optional[str]:
    """解析预设 Logo 的绝对路径

    Args:
        preset_id: 预设唯一标识

    Returns:
        Optional[str]: Logo 文件绝对路径；预设不存在、未配置 Logo
            或文件不存在时返回 None
    """
    preset = PROVIDER_PRESETS.get(preset_id)
    if preset is None or not preset.logo_filename:
        return None
    logo_path = LOGO_DIR / preset.logo_filename
    if not logo_path.is_file():
        return None
    return str(logo_path)


__all__ = [
    "CUSTOM_ADAPTER",
    "LOGO_DIR",
    "PROVIDER_PRESETS",
    "PRESET_MODELS",
    "ProviderPreset",
    "get_provider_preset",
    "get_preset_logo_path",
]
