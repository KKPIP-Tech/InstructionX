# -*- coding: utf-8 -*-
"""插件目录「包外文件」检测与快照（安装前的兜底保护）。

**背景**：框架把插件目录视为**程序包**——安装 / 升级 / 降级 / 重装都会用包内容
整目录替换，仅保留 ``.plugin_info.json``（保证 UUID 稳定）。若有插件把运行时数据
写在自己目录内，替换后这些文件会丢失。

本模块在替换前检测「包内没有、旧目录里有」的文件，并把**整个旧目录**快照到
``data/plugin_backup/{插件ID}/{时间戳}_{版本}/``，供用户事后自行取回。
快照保留 ``.plugin_info.json``（便于追溯数据归属），仅忽略 ``__pycache__`` 与字节码。

**刻意不自动恢复**：旧文件可能属于已废弃的代码或旧版配置，自动合并会污染新版本；
插件应改用 ``DataProvider`` 的 ``set_plugin_data``（结构化数据）或
``save_asset`` / ``get_asset_path``（文件数据）存放运行时数据。
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set

__all__ = [
    "PLUGIN_INFO_FILE",
    "IGNORED_DIR_NAMES",
    "IGNORED_SUFFIXES",
    "MAX_BACKUPS_PER_PLUGIN",
    "collect_extra_files",
    "snapshot_plugin_dir",
]

#: 插件 UUID 文件（升级时必须保留，故不计入「包外文件」）
PLUGIN_INFO_FILE = ".plugin_info.json"
#: 快照时忽略的目录
IGNORED_DIR_NAMES: Set[str] = {"__pycache__"}
#: 快照时忽略的文件后缀
IGNORED_SUFFIXES: Set[str] = {".pyc", ".pyo"}
#: 每个插件保留的历史快照份数（超出后删除最旧的）
MAX_BACKUPS_PER_PLUGIN = 3

#: 快照目录名的时间戳格式（同时用于排序，保证按时间淘汰最旧）
_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
#: 版本号未知时的占位（避免目录名出现空段）
_UNKNOWN_VERSION = "unknown"


def _is_ignored_dir(directory: Path) -> bool:
    """目录是否属于快照忽略项"""
    return directory.name in IGNORED_DIR_NAMES


def _is_ignored_file(path: Path) -> bool:
    """文件是否属于快照忽略项（UUID 文件与字节码）"""
    return path.name == PLUGIN_INFO_FILE or path.suffix.lower() in IGNORED_SUFFIXES


def collect_extra_files(old_dir: Path, new_dir: Path) -> List[str]:
    """列出旧插件目录中「新包内不存在」的文件

    Args:
        old_dir: 已安装的插件目录
        new_dir: 待安装的新包目录

    Returns:
        List[str]: 包外文件的相对 posix 路径（已排序）；无则为空列表
    """
    if not old_dir.is_dir():
        return []

    extra: List[str] = []
    for path in old_dir.rglob("*"):
        if path.is_dir():
            continue
        if _is_ignored_file(path) or any(_is_ignored_dir(parent)
                                         for parent in path.parents):
            continue
        relative = path.relative_to(old_dir)
        if not (new_dir / relative).exists():
            extra.append(relative.as_posix())
    return sorted(extra)


def _prune_backups(plugin_backup_dir: Path) -> None:
    """只保留最近 MAX_BACKUPS_PER_PLUGIN 份快照（按时间戳目录名排序）"""
    if not plugin_backup_dir.is_dir():
        return
    snapshots = sorted((p for p in plugin_backup_dir.iterdir() if p.is_dir()),
                       key=lambda p: p.name)
    for stale in snapshots[:-MAX_BACKUPS_PER_PLUGIN]:
        shutil.rmtree(stale, ignore_errors=True)


def snapshot_plugin_dir(old_dir: Path, backup_root: Path, plugin_id: str,
                        version: str = "") -> Optional[Path]:
    """把旧插件目录快照到备份根目录下

    Args:
        old_dir: 待快照的插件目录
        backup_root: 备份根目录（如 ``<项目>/data/plugin_backup``）
        plugin_id: 插件 ID（作为二级目录名）
        version: 插件版本（写入快照目录名，便于辨识）

    Returns:
        Optional[Path]: 快照目录路径；``old_dir`` 不存在时返回 None
    """
    if not old_dir.is_dir():
        return None

    stamp = datetime.now().strftime(_TIMESTAMP_FORMAT)
    safe_version = (version or _UNKNOWN_VERSION).replace("/", "_").replace("\\", "_")
    target = backup_root / plugin_id / f"{stamp}_{safe_version}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(old_dir, target, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(*IGNORED_DIR_NAMES,
                                                  *(f"*{s}" for s in IGNORED_SUFFIXES)))
    _prune_backups(target.parent)
    return target
