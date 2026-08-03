"""字体管理器。

框架级字体子系统：负责字体的安装、卸载、注册表持久化与系统字体回退。
字体经 ``QFontDatabase.addApplicationFont`` 做应用级注册（进程内生效，
不写入操作系统字体目录），持久化记录位于 ``data/fonts/``。

单例访问：``get_font_manager()``。
"""

import json
import os
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtGui import QFont, QFontDatabase

from utils.logging_tools import LoggerManager, get_name

from .exceptions import FontInstallError
from .font_record import FontRecord

# 项目根目录（core/font/manager.py → core/font → core → 根目录）
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent

# 字体存储目录与注册表文件
_FONTS_DIR: Path = _PROJECT_ROOT / "data" / "fonts"
_REGISTRY_FILE: Path = _FONTS_DIR / "fonts.json"

# 注册表 schema 版本（顶层 version 字段）
_REGISTRY_VERSION: int = 1

# 支持安装的字体文件扩展名
SUPPORTED_SUFFIXES = (".ttf", ".otf", ".ttc")


class FontManager:
    """字体管理器单例

    职责：管理框架级字体的全生命周期——安装（复制到 ``data/fonts/``
    并注册进 QFontDatabase）、卸载、注册表持久化（启动时恢复注册），
    以及带系统字体回退的字体解析。

    典型用法（插件侧）：

        font_manager = services.font_manager  # 或 get_font_manager()
        font = font_manager.get_font("得意黑", point_size=16)
        label.setFont(font)  # 未安装时自动回退系统默认字体
    """

    _instance: Optional["FontManager"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "FontManager":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._logger = LoggerManager()
        self._lock = threading.RLock()
        # 字体记录表：font_id -> FontRecord
        self._records: Dict[str, FontRecord] = {}
        # 运行时映射：font_id -> QFontDatabase 应用字体 id（每次注册动态分配）
        self._app_font_ids: Dict[str, int] = {}
        self._loaded = False

    # ------------------------------------------------------------- 持久化

    def _ensure_loaded(self) -> None:
        """惰性加载注册表并恢复字体注册（仅首次访问时执行）"""
        with self._lock:
            if self._loaded:
                return
            self._loaded = True
            self._load_registry()
            self._register_all()

    def _load_registry(self) -> None:
        """读取注册表；文件缺失或损坏时按空注册表处理"""
        if not _REGISTRY_FILE.exists():
            return
        try:
            with open(_REGISTRY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data.get("fonts", []):
                record = FontRecord.from_dict(item)
                self._records[record.font_id] = record
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
            # 注册表损坏不阻断启动：记日志后按空表运行
            self._logger.error(get_name(), f"字体注册表读取失败，按空注册表运行: {e}")

    def _save_registry(self) -> None:
        """原子写注册表（临时文件 + os.replace）"""
        _FONTS_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": _REGISTRY_VERSION,
            "fonts": [r.to_dict() for r in self._records.values()],
        }
        temp_file = _REGISTRY_FILE.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(temp_file, _REGISTRY_FILE)

    def _register_all(self) -> None:
        """启动恢复：重新注册注册表中的全部字体（文件缺失的记录剔除）"""
        for font_id in list(self._records):
            record = self._records[font_id]
            if not (_FONTS_DIR / record.filename).is_file():
                self._logger.warning(
                    get_name(), f"字体文件缺失，剔除注册记录: {record.filename}")
                del self._records[font_id]
                continue
            self._register_to_qt(record)

    def _register_to_qt(self, record: FontRecord) -> bool:
        """把单个字体文件注册进 QFontDatabase，成功时记录应用字体 id"""
        app_id = QFontDatabase.addApplicationFont(str(_FONTS_DIR / record.filename))
        if app_id < 0:
            self._logger.warning(get_name(), f"字体注册失败: {record.filename}")
            return False
        self._app_font_ids[record.font_id] = app_id
        return True

    # ------------------------------------------------------------- 安装 / 卸载

    def install_font(self, path: str, source: str = "user") -> FontRecord:
        """安装字体文件（复制到 data/fonts/ 并注册进 QFontDatabase）

        Args:
            path: 字体文件路径（.ttf/.otf/.ttc）
            source: 安装来源（"user" 或插件 id）

        Returns:
            安装成功的字体记录；同名（font_id 相同）字体已安装时返回既有记录

        Raises:
            FontInstallError: 文件不存在、格式不支持、复制或 Qt 注册失败时
        """
        source_path = Path(path)
        if not source_path.is_file():
            raise FontInstallError(f"字体文件不存在: {path}")
        if source_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise FontInstallError(
                f"不支持的字体格式: {source_path.suffix}（支持 {'/'.join(SUPPORTED_SUFFIXES)}）")

        self._ensure_loaded()
        with self._lock:
            font_id = source_path.stem
            existing = self._records.get(font_id)
            if existing is not None:
                self._logger.info(get_name(), f"字体已安装，跳过重复安装: {font_id}")
                return existing

            record = self._copy_and_register(source_path, font_id, source)
            self._records[font_id] = record
            try:
                self._save_registry()
            except OSError as e:
                raise FontInstallError(f"字体注册表写入失败: {e}") from e
            self._logger.info(
                get_name(), f"字体安装成功: {record.family}（来源: {source}）")
            return record

    def _copy_and_register(
            self, source_path: Path, font_id: str, source: str) -> FontRecord:
        """复制字体文件到 data/fonts/ 并注册进 Qt，返回字体记录"""
        target_path = _FONTS_DIR / source_path.name
        try:
            _FONTS_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
        except OSError as e:
            raise FontInstallError(f"字体文件复制失败: {e}") from e

        app_id = QFontDatabase.addApplicationFont(str(target_path))
        if app_id < 0:
            target_path.unlink(missing_ok=True)
            raise FontInstallError(f"Qt 字体注册失败（文件可能已损坏）: {source_path.name}")

        families = QFontDatabase.applicationFontFamilies(app_id)
        family = families[0] if families else font_id
        record = FontRecord(
            font_id=font_id,
            family=family,
            style="",
            filename=source_path.name,
            source=source,
            installed_at=datetime.now().isoformat(timespec="seconds"),
        )
        self._app_font_ids[font_id] = app_id
        return record

    def uninstall_font(self, font_id: str) -> bool:
        """卸载字体（从 QFontDatabase 移除、删除文件、更新注册表）

        Args:
            font_id: 字体标识（FontRecord.font_id）

        Returns:
            是否成功卸载；字体不存在时返回 False
        """
        self._ensure_loaded()
        with self._lock:
            record = self._records.pop(font_id, None)
            if record is None:
                return False

            app_id = self._app_font_ids.pop(font_id, None)
            if app_id is not None:
                QFontDatabase.removeApplicationFont(app_id)
            (_FONTS_DIR / record.filename).unlink(missing_ok=True)
            self._save_registry()
            self._logger.info(get_name(), f"字体已卸载: {record.family}")
            return True

    # ------------------------------------------------------------- 查询与回退

    def list_fonts(self) -> List[FontRecord]:
        """返回全部已安装字体的记录列表"""
        self._ensure_loaded()
        return list(self._records.values())

    def installed_families(self) -> List[str]:
        """返回框架安装字体的家族名列表"""
        return [r.family for r in self.list_fonts()]

    def is_available(self, family: str) -> bool:
        """检查字体家族是否可用（框架安装或系统自带）"""
        self._ensure_loaded()
        if family in self.installed_families():
            return True
        return family in QFontDatabase.families()

    def resolve_family(
            self, requested: str, fallbacks: Optional[List[str]] = None) -> str:
        """按回退链解析字体家族名

        回退顺序：请求字体 → 调用方指定的回退列表 → 系统默认字体。
        保证返回值始终是一个当前可用的字体家族名。

        Args:
            requested: 期望使用的字体家族名
            fallbacks: 可选的回退家族名列表（按优先级排列）

        Returns:
            实际可用的字体家族名
        """
        candidates = [requested, *(fallbacks or [])]
        for candidate in candidates:
            if self.is_available(candidate):
                return candidate
        default_family = QFont().defaultFamily()
        self._logger.debug(
            get_name(), f"字体 {requested} 不可用，回退系统默认字体: {default_family}")
        return default_family

    def get_font(
            self,
            family: str,
            point_size: int = 0,
            weight: QFont.Weight = QFont.Weight.Normal,
            fallbacks: Optional[List[str]] = None) -> QFont:
        """构造带回退机制的 QFont

        Args:
            family: 期望的字体家族名（不可用时自动回退）
            point_size: 字号（磅值，<=0 时保持默认）
            weight: 字重
            fallbacks: 可选的回退家族名列表

        Returns:
            QFont 实例（家族名为 resolve_family 的实际解析结果）
        """
        font = QFont(self.resolve_family(family, fallbacks))
        if point_size > 0:
            font.setPointSize(point_size)
        font.setWeight(weight)
        return font


def get_font_manager() -> FontManager:
    """获取字体管理器单例实例"""
    return FontManager()
