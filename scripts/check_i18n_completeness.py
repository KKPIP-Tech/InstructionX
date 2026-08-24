"""语言文件完整性校验脚本。

校验不变量：
1. 默认语言文件必须覆盖源码中全部 ``tr(group, key)`` 调用——
   「默认语言必须完整」的机器保证（缺失 = 校验失败，exit 1）；
2. 其他语言相对默认语言缺分组/缺键 → 警告（运行时可回退，exit 0）；
3. 各语言文件 ``language`` 属性与文件名一致性；
4. 官方插件（plugin/）与第三方插件（custom_plugin/）的语言文件：
   以各自 zh.xml（或首个语言文件）为参照，报告其余语言的缺失。

运行：.venv\\Scripts\\python.exe scripts/check_i18n_completeness.py
测试可用 --text-dir / --src-dir / --plugin-root 指向临时目录。
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

# 保证项目根目录在 sys.path（scripts/ 下直接运行时）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.i18n import DEFAULT_LANGUAGE, load_catalog

# 项目根目录
_ROOT = Path(__file__).resolve().parent.parent

# 源码中 tr("group", "key") 调用的提取正则（仅匹配字面量双参数形式）
_TR_CALL_PATTERN = re.compile(
    r"""[^\w.]tr\(\s*['"]([\w-]+)['"]\s*,\s*['"]([\w.]+)['"]""")

# 框架文案源码扫描时排除的目录（同步的第三方组件库，不在 i18n 范围）
_EXCLUDED_SRC_PARTS = ("InstructionX_UIKit",)

# 键引用形式：(group, key)
KeyRef = Tuple[str, str]


def scan_source_keys(src_dir: Path) -> Dict[KeyRef, List[str]]:
    """静态扫描源码中的 tr(group, key) 字面量调用

    Args:
        src_dir: 源码目录（框架为 ui/）

    Returns:
        ``{(group, key): [出现位置...]}``
    """
    found: Dict[KeyRef, List[str]] = {}
    if not src_dir.is_dir():
        return found
    for py_file in sorted(src_dir.rglob("*.py")):
        if any(part in _EXCLUDED_SRC_PARTS for part in py_file.parts):
            continue
        _scan_file(py_file, found)
    return found


def _scan_file(py_file: Path, found: Dict[KeyRef, List[str]]) -> None:
    """扫描单个源文件，累计 tr() 键引用"""
    try:
        content = py_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    for lineno, line in enumerate(content.splitlines(), start=1):
        for match in _TR_CALL_PATTERN.finditer(line):
            ref = (match.group(1), match.group(2))
            found.setdefault(ref, []).append(f"{py_file.name}:{lineno}")


def _check_default_covers_source(text_dir: Path, src_dir: Path) -> int:
    """校验默认语言覆盖源码全部 tr() 调用，返回失败数"""
    required = scan_source_keys(src_dir)
    if not required:
        print("源码中未发现 tr() 调用，跳过默认语言覆盖校验")
        return 0
    default_file = text_dir / f"{DEFAULT_LANGUAGE}.xml"
    catalog = load_catalog(default_file)
    if catalog is None:
        print(f"[FAIL] 默认语言文件缺失或损坏: {default_file}（源码引用 {len(required)} 个键）")
        return len(required)
    failures = 0
    for (group, key), locations in sorted(required.items()):
        if not catalog.has(group, key):
            failures += 1
            print(f"[FAIL] 默认语言缺失 [{group}.{key}]，引用于 {', '.join(locations[:3])}")
    if failures == 0:
        print(f"[OK] 默认语言 {DEFAULT_LANGUAGE}.xml 覆盖源码全部 {len(required)} 个键")
    return failures


def _check_language_consistency(text_dir: Path, owner: str) -> None:
    """对比各语言与默认语言的分组/键集合，打印缺失与孤立键警告

    Args:
        text_dir: 语言文件目录
        owner: 归属描述（用于报告标题，如 "框架" / 插件目录名）
    """
    catalog = load_catalog(text_dir / f"{DEFAULT_LANGUAGE}.xml")
    if catalog is None:
        # 无默认语言文件：以排序首个语言为参照（插件可能声明了其他默认语言）
        files = sorted(text_dir.glob("*.xml"))
        if not files:
            return
        catalog = load_catalog(files[0])
        if catalog is None:
            print(f"[WARN] {owner}: 参照语言文件损坏: {files[0].name}")
            return
    reference = {f"{g}.{k}" for g in catalog.group_names() for k in catalog.groups[g]}
    for xml_file in sorted(text_dir.glob("*.xml")):
        if xml_file.stem == catalog.language:
            continue
        _diff_language(xml_file, reference, owner)


def _diff_language(xml_file: Path, reference: Set[str], owner: str) -> None:
    """对比单个语言文件与参照键集合"""
    other = load_catalog(xml_file)
    if other is None:
        print(f"[WARN] {owner}: 语言文件损坏: {xml_file.name}")
        return
    keys = {f"{g}.{k}" for g in other.group_names() for k in other.groups[g]}
    missing = sorted(reference - keys)
    orphan = sorted(keys - reference)
    if missing:
        print(f"[WARN] {owner}: {xml_file.name} 缺 {len(missing)} 键（运行时将回退）: "
              + ", ".join(missing[:5]) + (" ..." if len(missing) > 5 else ""))
    if orphan:
        print(f"[WARN] {owner}: {xml_file.name} 含 {len(orphan)} 个孤立键: "
              + ", ".join(orphan[:5]) + (" ..." if len(orphan) > 5 else ""))
    if not missing and not orphan:
        print(f"[OK] {owner}: {xml_file.name} 与参照语言键集合一致")


def check_framework(text_dir: Path, src_dir: Path) -> int:
    """框架侧校验：默认语言覆盖源码 + 各语言一致性，返回失败数"""
    print(f"== 框架语言文件校验（{text_dir}）==")
    if not text_dir.is_dir():
        print("框架语言目录不存在，跳过（框架尚未迁移文案）")
        return 0
    failures = _check_default_covers_source(text_dir, src_dir)
    _check_language_consistency(text_dir, "框架")
    return failures


def check_plugins(plugin_root: Path) -> None:
    """插件侧校验：逐插件对比各语言与其参照语言的键集合（只警告）"""
    if not plugin_root.is_dir():
        return
    for plugin_dir in sorted(plugin_root.iterdir()):
        text_dir = plugin_dir / "text"
        if plugin_dir.is_dir() and not plugin_dir.name.startswith("_") and text_dir.is_dir():
            print(f"== 插件语言文件校验（{plugin_dir.name}）==")
            _check_language_consistency(text_dir, plugin_dir.name)


def main() -> int:
    parser = argparse.ArgumentParser(description="i18n 语言文件完整性校验")
    parser.add_argument("--text-dir", type=Path, default=_ROOT / "ui" / "text",
                        help="框架语言文件目录")
    parser.add_argument("--src-dir", type=Path, default=_ROOT / "ui",
                        help="框架文案源码扫描目录")
    parser.add_argument("--plugin-root", type=Path, default=None,
                        help="插件根目录（可多次指定；默认 plugin/ 与 custom_plugin/）",
                        action="append")
    args = parser.parse_args()

    failures = check_framework(args.text_dir, args.src_dir)
    plugin_roots = args.plugin_root or [_ROOT / "plugin", _ROOT / "custom_plugin"]
    for root in plugin_roots:
        check_plugins(root)

    print(f"\n{'校验通过' if failures == 0 else f'校验失败：默认语言缺 {failures} 键'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
