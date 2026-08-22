"""i18n 配置持久化。

管理两个配置文件（均 schema v1，遵循项目既有惯例：顶层 ``version``
字段、原子写、损坏备份重建）：

- ``config/i18n.json``：框架语言设置（默认语言 + 当前语言）
- ``config/plugin_languages.json``：每插件语言覆盖（键为插件 UUID）
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional

from utils.logging_tools import LoggerManager, get_name

# ===== 配置文件常量 =====
I18N_CONFIG_FILENAME = "i18n.json"
PLUGIN_LANGUAGES_FILENAME = "plugin_languages.json"
CONFIG_SCHEMA_VERSION = 1

# 开发者设定的默认语言（随程序发布；用户不可修改，仅配置文件层面可改）
DEFAULT_LANGUAGE = "zh"

# 配置键名
_KEY_VERSION = "version"
_KEY_DEFAULT_LANGUAGE = "default_language"
_KEY_CURRENT_LANGUAGE = "current_language"
_KEY_OVERRIDES = "overrides"


class I18nSettingsStore:
    """i18n 配置读写封装

    职责：框架语言设置与每插件语言覆盖两个 JSON 文件的读写。
    启动早期即被使用（主窗口构造前），不依赖 Qt 与 DataProvider。
    """

    def __init__(self, config_dir: Optional[Path] = None):
        """初始化配置存储

        Args:
            config_dir: 配置文件目录，默认为项目根目录下 config/
        """
        if config_dir is None:
            # core/i18n/settings_store.py → core/i18n → core → 项目根
            config_dir = Path(__file__).resolve().parents[2] / "config"
        self._config_dir = config_dir
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._logger = LoggerManager()

    # ==================== 框架语言设置 ====================

    def load_framework_settings(self) -> Dict[str, str]:
        """读取框架语言设置

        Returns:
            ``{"default_language": ..., "current_language": ...}``；
            文件缺失/损坏时按默认语言填充，不阻断启动
        """
        data = self._read_json(self._config_dir / I18N_CONFIG_FILENAME)
        default_lang = data.get(_KEY_DEFAULT_LANGUAGE) or DEFAULT_LANGUAGE
        current_lang = data.get(_KEY_CURRENT_LANGUAGE) or default_lang
        return {
            _KEY_DEFAULT_LANGUAGE: default_lang,
            _KEY_CURRENT_LANGUAGE: current_lang,
        }

    def save_framework_settings(self, default_language: str, current_language: str) -> bool:
        """原子写框架语言设置

        Args:
            default_language: 开发者设定的默认语言
            current_language: 用户选择的当前语言

        Returns:
            写入成功返回 True
        """
        payload = {
            _KEY_VERSION: CONFIG_SCHEMA_VERSION,
            _KEY_DEFAULT_LANGUAGE: default_language,
            _KEY_CURRENT_LANGUAGE: current_language,
        }
        return self._write_json(self._config_dir / I18N_CONFIG_FILENAME, payload)

    # ==================== 每插件语言覆盖 ====================

    def load_plugin_overrides(self) -> Dict[str, str]:
        """读取全部插件语言覆盖

        Returns:
            ``{插件UUID: 语言代码}``；文件缺失/损坏时返回空表
        """
        data = self._read_json(self._config_dir / PLUGIN_LANGUAGES_FILENAME)
        overrides = data.get(_KEY_OVERRIDES)
        if not isinstance(overrides, dict):
            return {}
        return {str(k): str(v) for k, v in overrides.items()}

    def set_plugin_override(self, plugin_id: str, language: Optional[str]) -> bool:
        """设置或清除某插件的语言覆盖并持久化

        Args:
            plugin_id: 插件 UUID
            language: 语言代码；None 表示清除覆盖（恢复跟随框架）

        Returns:
            写入成功返回 True
        """
        overrides = self.load_plugin_overrides()
        if language is None:
            overrides.pop(plugin_id, None)
        else:
            overrides[plugin_id] = language
        payload = {_KEY_VERSION: CONFIG_SCHEMA_VERSION, _KEY_OVERRIDES: overrides}
        return self._write_json(self._config_dir / PLUGIN_LANGUAGES_FILENAME, payload)

    def remove_plugin_override(self, plugin_id: str) -> bool:
        """清除某插件的语言覆盖（插件卸载时调用）

        Args:
            plugin_id: 插件 UUID

        Returns:
            写入成功返回 True
        """
        return self.set_plugin_override(plugin_id, None)

    # ==================== 通用读写 ====================

    def _read_json(self, path: Path) -> Dict:
        """读取 JSON 配置；损坏时备份为 .corrupt.bak 并按空配置处理"""
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("配置结构无效（顶层应为对象）")
            return data
        except (OSError, json.JSONDecodeError, ValueError) as e:
            self._logger.error(get_name(), f"i18n 配置读取失败，按空配置运行: {path}: {e}")
            self._backup_corrupt_file(path)
            return {}

    def _write_json(self, path: Path, payload: Dict) -> bool:
        """原子写 JSON 配置（临时文件 + os.replace）"""
        try:
            temp_file = path.with_suffix(".json.tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, path)
            return True
        except (OSError, TypeError, ValueError) as e:
            self._logger.error(get_name(), f"i18n 配置写入失败: {path}: {e}")
            return False

    def _backup_corrupt_file(self, path: Path) -> None:
        """备份损坏的配置文件（覆盖旧备份）"""
        try:
            os.replace(path, path.with_suffix(".json.corrupt.bak"))
        except OSError as e:
            self._logger.warning(get_name(), f"备份损坏 i18n 配置失败: {path}: {e}")
