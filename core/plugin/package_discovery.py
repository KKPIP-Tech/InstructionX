# -*- coding: utf-8 -*-
"""插件包识别：从解压后的目录树中识别「单插件 / 插件集」（纯文件系统，不做解压与安装）。

**职责边界**（单一职责）：

- 只读文件系统，不导入 zipfile / PluginManager / 注册表 / UI，因此可独立测试；
- 只输出「发现了哪些插件、哪些不可安装、为什么」，安装动作由
  :class:`core.plugin.github_plugin_installer.GitHubPluginInstaller` 负责。

**识别顺序**（见 :func:`discover_plugins`）：

1. 穿过「包装层」：当前目录既无描述文件也无索引、且只有一个非噪声子目录时下潜
   （覆盖 GitHub 的 ``repo-<branch>/``、用户二次打包、macOS 的 ``__MACOSX`` 干扰等）；
2. 包根存在 ``IXRepo.json`` → **索引驱动**：索引项优先且按索引顺序排列；
3. 无索引 → **递归扫描**含 ``IXPlugin.json`` 的目录（限深、跳过噪声目录）；
4. 有索引时，扫描发现但索引未声明的插件**也纳入候选**并标注
   ``declared_in_index=False``——避免索引过期导致插件被无声忽略。

典型用法::

    inspection = inspect_package(extracted_root)
    if inspection.kind == PACKAGE_KIND_SINGLE:
        install(inspection.candidates[0])
"""

import json
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple, Union

__all__ = [
    "PLUGIN_DESCRIPTOR_FILE",
    "REPO_INDEX_FILE",
    "PACKAGE_KIND_SINGLE",
    "PACKAGE_KIND_MULTI",
    "PACKAGE_KIND_INVALID",
    "MAX_DISCOVERY_DEPTH",
    "MAX_SCAN_DIRS",
    "MAX_WRAPPER_DEPTH",
    "PluginCandidate",
    "PackageInspection",
    "validate_descriptor",
    "unwrap_package_root",
    "discover_plugins",
    "inspect_package",
]

# ===== 文件与分类常量 =====
PLUGIN_DESCRIPTOR_FILE = "IXPlugin.json"
REPO_INDEX_FILE = "IXRepo.json"

PACKAGE_KIND_SINGLE = "single"
PACKAGE_KIND_MULTI = "multi"
PACKAGE_KIND_INVALID = "invalid"

# ===== 扫描上限（防病态压缩包导致长时间遍历） =====
#: 包根之下允许的递归深度（层）
MAX_DISCOVERY_DEPTH = 6
#: 单次识别允许遍历的目录数上限
MAX_SCAN_DIRS = 20000
#: 穿过包装层目录的最大层数
MAX_WRAPPER_DEPTH = 6

#: 不参与识别的目录名（构建产物 / 版本控制 / 编辑器 / 系统噪声）
IGNORED_DIR_NAMES = frozenset({
    ".git", ".github", ".idea", ".vscode", ".venv", "venv", "env",
    "__MACOSX", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", "dist", "build",
})

#: 描述文件必填字段（与安装器既有校验规则保持一致）
REQUIRED_DESCRIPTOR_FIELDS = ("id", "name", "version", "main")
#: 版本号格式（<类型>.<大>.<小>.<补丁>）
_VERSION_PATTERN = re.compile(r"^(release|pre-release|beta|alpha|internal)\.\d+\.\d+\.\d+$")
#: 插件 ID 允许的字符
_PLUGIN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

#: 可多语言字段：纯字符串或 {语言代码: 文案}
I18nFieldValue = Union[str, Dict[str, str]]


@dataclass(frozen=True)
class PluginCandidate:
    """候选插件（识别阶段的产物，尚未安装）

    Attributes:
        descriptor_id: 描述文件中的 ``id``（目录名与它无关，安装后目录名取该值）
        name: 插件名，保留描述文件原始形式（可能是多语言字典）
        version: 版本号（如 ``release.1.0.0``）
        main: 入口文件名（如 ``entrance.py``）
        description: 描述，保留原始形式（可能为 None 或多语言字典）
        author / homepage: 作者与主页
        keywords / dependencies: 关键词与 Python 依赖声明
        rel_path: 相对**传入的根目录**的 posix 路径（含包装层，如 ``repo-main/plugin-a``）；
            ``""`` 表示插件就在根目录本身。调用方用 ``根目录 / rel_path`` 即可定位
        valid: 是否可安装（描述文件缺失/字段非法/重复 ID 时为 False）
        error: ``valid`` 为 False 时的中文原因
        declared_in_index: 是否由 ``IXRepo.json`` 索引声明
    """

    descriptor_id: str = ""
    name: I18nFieldValue = ""
    version: str = ""
    main: str = ""
    description: Optional[I18nFieldValue] = None
    author: Optional[str] = None
    homepage: Optional[str] = None
    keywords: Tuple[str, ...] = ()
    dependencies: Dict[str, str] = field(default_factory=dict)
    rel_path: str = ""
    valid: bool = True
    error: str = ""
    declared_in_index: bool = False


@dataclass(frozen=True)
class PackageInspection:
    """插件包识别结果

    Attributes:
        kind: ``single`` / ``multi`` / ``invalid``
        candidates: 候选插件（含不可安装项，顺序：索引声明项在前）
        warnings: 非致命提示（未声明插件、重复 ID、扫描截断等）
        error: ``kind`` 为 ``invalid`` 时的中文诊断信息
        has_index: 包内是否存在 ``IXRepo.json``（决定安装对话框的默认勾选策略）
    """

    kind: str
    candidates: Tuple[PluginCandidate, ...] = ()
    warnings: Tuple[str, ...] = ()
    error: str = ""
    has_index: bool = False


@dataclass
class _ScanStats:
    """扫描统计（仅用于诊断信息）"""

    dirs_scanned: int = 0
    ignored_dirs: int = 0
    max_depth: int = 0
    truncated: bool = False
    unreadable: int = 0


# ===================================================================
# 描述文件校验（与 GitHubPluginInstaller.validate_descriptor 规则一致）
# ===================================================================

def validate_descriptor(descriptor: Dict[str, Any]) -> Tuple[bool, str]:
    """校验插件描述文件

    Args:
        descriptor: 已解析的 ``IXPlugin.json`` 内容

    Returns:
        Tuple[bool, str]: (是否合法, 中文错误原因)；合法时原因为空串
    """
    for field_name in REQUIRED_DESCRIPTOR_FIELDS:
        if field_name not in descriptor:
            return False, f"缺少必需字段: {field_name}"

    version = descriptor.get("version", "")
    if not _VERSION_PATTERN.match(str(version)):
        return False, f"版本号格式无效: {version}，期望格式: <类型>.<大>.<小>.<补丁>"

    plugin_id = descriptor.get("id", "")
    if not _PLUGIN_ID_PATTERN.match(str(plugin_id)):
        return False, f"插件 ID 格式无效: {plugin_id}"

    return True, ""


# ===================================================================
# 目录遍历基础工具
# ===================================================================

def _is_ignored_dir(name: str) -> bool:
    """目录是否应跳过（噪声目录，或 ``_`` / ``.`` 前缀）"""
    return (name in IGNORED_DIR_NAMES
            or name.startswith("_")
            or name.startswith("."))


def _has_descriptor(directory: Path) -> bool:
    """目录内是否有插件描述文件"""
    return (directory / PLUGIN_DESCRIPTOR_FILE).is_file()


def _has_index(directory: Path) -> bool:
    """目录内是否有插件集索引文件"""
    return (directory / REPO_INDEX_FILE).is_file()


def _visible_subdirs(directory: Path) -> List[Path]:
    """列出目录下的非噪声子目录（按名称排序，保证结果确定）"""
    try:
        entries = sorted(directory.iterdir(), key=lambda p: p.name)
    except OSError:
        return []
    return [entry for entry in entries
            if entry.is_dir() and not _is_ignored_dir(entry.name)]


def _subdirs(directory: Path, stats: _ScanStats) -> List[Path]:
    """同 :func:`_visible_subdirs`，并累计「跳过 / 不可读」统计（供诊断信息使用）"""
    try:
        entries = sorted(directory.iterdir(), key=lambda p: p.name)
    except OSError:
        stats.unreadable += 1
        return []
    subdirs = []
    for entry in entries:
        if not entry.is_dir():
            continue
        if _is_ignored_dir(entry.name):
            stats.ignored_dirs += 1
            continue
        subdirs.append(entry)
    return subdirs


def _rel_posix(directory: Path, root: Path) -> str:
    """目录相对包根的 posix 路径（包根本身返回空串）"""
    if directory == root:
        return ""
    try:
        return directory.relative_to(root).as_posix()
    except ValueError:
        return directory.as_posix()


def unwrap_package_root(root: Path) -> Path:
    """穿过包装层目录，返回真正承载插件（或索引）的目录

    当前目录既无 ``IXPlugin.json`` 也无 ``IXRepo.json``、且只有一个非噪声子目录时
    向下穿透，最多 :data:`MAX_WRAPPER_DEPTH` 层；其余情况原样返回。

    Args:
        root: 解压后的顶层目录

    Returns:
        Path: 归一化后的包根（可能等于入参）
    """
    current = root
    for _ in range(MAX_WRAPPER_DEPTH):
        if _has_descriptor(current) or _has_index(current):
            return current
        subdirs = _visible_subdirs(current)
        if len(subdirs) != 1:
            return current
        current = subdirs[0]
    return current


# ===================================================================
# 扫描与候选构造
# ===================================================================

def _scan_plugin_dirs(root: Path) -> Tuple[List[Path], List[str], _ScanStats]:
    """递归查找含描述文件的插件目录（广度优先、限深、限目录数）

    命中描述文件的目录**不再下潜**——插件内部子目录（``function/``、``ui/`` 等）
    不应被继续扫描，既省时间也避免误判嵌套的示例插件。

    Returns:
        Tuple[List[Path], List[str], _ScanStats]: (插件目录列表, 警告, 统计)
    """
    stats = _ScanStats()
    found: List[Path] = []
    warnings: List[str] = []
    depth_limited = False
    queue: Deque[Tuple[Path, int]] = deque([(root, 0)])

    while queue:
        directory, depth = queue.popleft()
        if _has_descriptor(directory):
            found.append(directory)
            continue
        stats.dirs_scanned += 1
        stats.max_depth = max(stats.max_depth, depth)
        if stats.dirs_scanned > MAX_SCAN_DIRS:
            stats.truncated = True
            warnings.append(f"目录数量超过上限（{MAX_SCAN_DIRS}），已停止扫描")
            break
        subdirs = _subdirs(directory, stats)
        if depth >= MAX_DISCOVERY_DEPTH:
            depth_limited = depth_limited or bool(subdirs)
            continue
        queue.extend((sub, depth + 1) for sub in subdirs)

    if depth_limited:
        stats.truncated = True
        warnings.append(f"目录层级超过上限（{MAX_DISCOVERY_DEPTH} 层），更深层未扫描")
    return found, warnings, stats


def _read_descriptor(plugin_dir: Path) -> Tuple[Optional[Dict[str, Any]], str]:
    """读取并解析描述文件

    Returns:
        Tuple[Optional[Dict], str]: (描述内容, 失败原因)；成功时原因为空串
    """
    path = plugin_dir / PLUGIN_DESCRIPTOR_FILE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return None, f"读取 {PLUGIN_DESCRIPTOR_FILE} 失败: {e}"
    if not isinstance(raw, dict):
        return None, f"{PLUGIN_DESCRIPTOR_FILE} 内容不是 JSON 对象"
    return raw, ""


def _candidate_from_dir(plugin_dir: Path, root: Path,
                        declared_in_index: bool = False) -> PluginCandidate:
    """由插件目录构造候选（描述文件缺失或非法时返回不可安装候选）"""
    rel_path = _rel_posix(plugin_dir, root)
    descriptor, error = _read_descriptor(plugin_dir)
    if descriptor is None:
        return PluginCandidate(rel_path=rel_path, valid=False, error=error,
                               declared_in_index=declared_in_index)

    is_valid, error_msg = validate_descriptor(descriptor)
    return PluginCandidate(
        descriptor_id=str(descriptor.get("id", "")),
        name=descriptor.get("name", ""),
        version=str(descriptor.get("version", "")),
        main=str(descriptor.get("main", "")),
        description=descriptor.get("description"),
        author=descriptor.get("author"),
        homepage=descriptor.get("homepage"),
        keywords=tuple(descriptor.get("keywords", []) or ()),
        dependencies=dict(descriptor.get("dependencies", {}) or {}),
        rel_path=rel_path,
        valid=is_valid,
        error=error_msg,
        declared_in_index=declared_in_index,
    )


# ===================================================================
# 索引（IXRepo.json）驱动
# ===================================================================

def _read_index(root: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    """读取索引文件的插件条目

    Returns:
        Tuple[List[Dict], List[str]]: (条目列表, 警告)；无索引或索引不可用时返回空列表
    """
    index_path = root / REPO_INDEX_FILE
    if not index_path.is_file():
        return [], []
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return [], [f"读取 {REPO_INDEX_FILE} 失败，改为扫描目录: {e}"]
    entries = raw.get("plugins") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        return [], [f"{REPO_INDEX_FILE} 缺少 plugins 数组，改为扫描目录"]
    return [e for e in entries if isinstance(e, dict)], []


def _resolve_index_entry(root: Path, entry: Dict[str, Any]) -> Optional[Path]:
    """索引条目的 ``path`` 解析为目录路径；路径越出包根时返回 None（拒绝越界）

    返回路径保持与 ``root`` 相同的书写形式（不作 resolve），以便与扫描得到的
    目录路径用同一个根计算相对路径。
    """
    rel = str(entry.get("path", "")).strip("/")
    if not rel:
        return root
    target = root / rel
    root_resolved = root.resolve()
    target_resolved = target.resolve()
    if target_resolved != root_resolved and root_resolved not in target_resolved.parents:
        return None
    return target


def _candidates_from_index(root: Path, base_root: Path, entries: List[Dict[str, Any]]
                           ) -> Tuple[List[PluginCandidate], List[str]]:
    """按索引构造候选：声明的目录缺失时给出不可安装候选而非静默丢弃

    Args:
        root: 索引所在目录（索引中的 ``path`` 相对它解析）
        base_root: 计算候选 ``rel_path`` 的基准目录（见 :func:`discover_plugins`）
        entries: 索引中的 ``plugins`` 条目
    """
    candidates: List[PluginCandidate] = []
    warnings: List[str] = []
    for entry in entries:
        rel = str(entry.get("path", "")).strip("/")
        declared_id = str(entry.get("id", "") or entry.get("name", ""))
        plugin_dir = _resolve_index_entry(root, entry)
        if plugin_dir is None:
            reason = f"索引声明的路径越出包根，已拒绝: {rel}"
        elif not plugin_dir.is_dir():
            reason = f"索引声明的目录不存在: {rel}"
        elif not _has_descriptor(plugin_dir):
            reason = f"索引声明的目录缺少 {PLUGIN_DESCRIPTOR_FILE}: {rel}"
        else:
            candidates.append(_candidate_from_dir(plugin_dir, base_root,
                                                  declared_in_index=True))
            continue
        candidates.append(PluginCandidate(
            descriptor_id=declared_id, name=entry.get("name", ""),
            rel_path=_rel_posix(plugin_dir or root, base_root), valid=False,
            error=reason, declared_in_index=True))
        warnings.append(reason)
    return candidates, warnings


# ===================================================================
# 去重与对外入口
# ===================================================================

def _dedupe_by_id(candidates: List[PluginCandidate]) -> Tuple[List[PluginCandidate], List[str]]:
    """按描述文件 id 去重：保留首个（索引项优先），其余标记为不可安装"""
    seen: Dict[str, str] = {}
    result: List[PluginCandidate] = []
    warnings: List[str] = []
    for candidate in candidates:
        key = candidate.descriptor_id or candidate.rel_path
        if key in seen:
            reason = f"插件 ID 与 {seen[key]} 重复，已忽略本目录"
            result.append(PluginCandidate(
                descriptor_id=candidate.descriptor_id, name=candidate.name,
                version=candidate.version, rel_path=candidate.rel_path,
                valid=False, error=reason,
                declared_in_index=candidate.declared_in_index))
            warnings.append(f"{candidate.rel_path or '.'}: {reason}")
            continue
        seen[key] = candidate.rel_path or "."
        result.append(candidate)
    return result, warnings


def discover_plugins(root: Path, base_root: Optional[Path] = None
                     ) -> Tuple[List[PluginCandidate], List[str]]:
    """识别包内的全部插件候选

    Args:
        root: 包根（通常为 :func:`unwrap_package_root` 处理后的目录）
        base_root: 计算候选 ``rel_path`` 的基准目录；默认等于 ``root``。
            传入**未穿透包装层的原始根**时，``rel_path`` 会带上包装层路径，
            调用方用 ``原始根 / rel_path`` 即可正确定位插件目录。

    Returns:
        Tuple[List[PluginCandidate], List[str]]: (候选列表, 警告列表)
    """
    base = base_root or root
    index_entries, index_warnings = _read_index(root)
    warnings = list(index_warnings)

    if index_entries:
        candidates, warn = _candidates_from_index(root, base, index_entries)
        warnings.extend(warn)
        declared = {c.rel_path for c in candidates}
        scanned, warn, _ = _scan_plugin_dirs(root)
        extra = [d for d in scanned if _rel_posix(d, base) not in declared]
        if extra:
            warnings.append(
                f"发现 {len(extra)} 个未在 {REPO_INDEX_FILE} 中声明的插件目录，"
                f"默认不勾选：{', '.join(_rel_posix(d, base) for d in extra[:5])}")
        candidates.extend(_candidate_from_dir(d, base) for d in extra)
    else:
        scanned, warn, _ = _scan_plugin_dirs(root)
        warnings.extend(warn)
        candidates = [_candidate_from_dir(d, base) for d in scanned]

    deduped, dedupe_warnings = _dedupe_by_id(candidates)
    warnings.extend(dedupe_warnings)
    return deduped, warnings


def _diagnose_empty(root: Path, stats: _ScanStats) -> str:
    """构造「未识别到插件」的中文诊断信息"""
    parts = [
        f"未在压缩包中识别到插件（已扫描到 {stats.dirs_scanned} 个目录，"
        f"最深 {stats.max_depth} 层，跳过噪声目录 {stats.ignored_dirs} 个）",
        f"扫描根目录: {root.name or root}",
    ]
    if _has_index(root):
        parts.append(f"{REPO_INDEX_FILE} 中没有任何有效的插件条目")
    else:
        parts.append(f"未发现 {REPO_INDEX_FILE}（插件集索引）与 {PLUGIN_DESCRIPTOR_FILE}"
                     f"（插件描述文件）")
    parts.append(f"请确认压缩包内包含 {PLUGIN_DESCRIPTOR_FILE}；"
                 f"若为插件集，建议在仓库根提供 {REPO_INDEX_FILE}")
    if stats.truncated:
        parts.append("注意：扫描因超过层数/目录数上限而提前结束，可能存在未扫描到的插件")
    return "；".join(parts)


def inspect_package(root: Path) -> PackageInspection:
    """识别解压目录：单插件 / 插件集 / 无效

    候选的 ``rel_path`` 相对**传入的 root** 计算（含包装层路径），
    因此调用方用 ``root / candidate.rel_path`` 即可定位插件目录。

    Args:
        root: 解压后的顶层目录

    Returns:
        PackageInspection: 分类结果；``invalid`` 时 ``error`` 含可诊断的具体原因
    """
    if not root.is_dir():
        return PackageInspection(kind=PACKAGE_KIND_INVALID,
                                 error=f"解压目录不存在: {root}")

    package_root = unwrap_package_root(root)
    has_index = _has_index(package_root)
    candidates, warnings = discover_plugins(package_root, base_root=root)
    if not candidates:
        _, _, stats = _scan_plugin_dirs(package_root)
        return PackageInspection(kind=PACKAGE_KIND_INVALID, warnings=tuple(warnings),
                                 error=_diagnose_empty(package_root, stats),
                                 has_index=has_index)

    kind = PACKAGE_KIND_SINGLE if len(candidates) == 1 else PACKAGE_KIND_MULTI
    return PackageInspection(kind=kind, candidates=tuple(candidates),
                             warnings=tuple(warnings), has_index=has_index)
