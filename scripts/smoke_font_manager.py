"""字体管理器（core/font）冒烟验证脚本。

验证链路：安装（含非法格式/文件缺失/重复安装）→ 查询 → 回退解析 →
注册表持久化（单例重置后恢复）→ 卸载清理。

运行：.venv\\Scripts\\python.exe scripts/smoke_font_manager.py
"""

import sys
from pathlib import Path

# 保证项目根目录在 sys.path（scripts/ 下直接运行时）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

from core.font import FontInstallError, FontManager, get_font_manager
from core.interfaces.plugin_services import PluginServices

# Windows 系统字体（冒烟测试的安装来源，仅复制不修改）
_SYSTEM_FONT_CANDIDATES = (
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
)


def _pick_system_font() -> str:
    for candidate in _SYSTEM_FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    raise RuntimeError("未找到可用的 Windows 系统字体作为测试源")


def main() -> int:
    app = QApplication([])  # noqa: F841（QFontDatabase 需要 QGuiApplication 实例）
    manager = get_font_manager()
    assert isinstance(manager, FontManager)

    failures = 0

    def check(name: str, condition: bool) -> None:
        nonlocal failures
        status = "PASS" if condition else "FAIL"
        if not condition:
            failures += 1
        print(f"[{status}] {name}")

    # 0. 初始状态
    check("初始字体列表为列表类型", isinstance(manager.list_fonts(), list))

    # 1. 非法格式与文件缺失
    try:
        manager.install_font("not_a_font.txt")
        check("非法格式抛 FontInstallError", False)
    except FontInstallError:
        check("非法格式抛 FontInstallError", True)
    try:
        manager.install_font("C:/不存在的字体.ttf")
        check("文件缺失抛 FontInstallError", False)
    except FontInstallError:
        check("文件缺失抛 FontInstallError", True)

    # 2. 正常安装 + 重复安装
    source_font = _pick_system_font()
    record = manager.install_font(source_font, source="smoke-test")
    check("安装返回 FontRecord 且 family 非空", bool(record.family))
    check("is_available(已安装家族)", manager.is_available(record.family))
    duplicate = manager.install_font(source_font)
    check("重复安装返回既有记录", duplicate.font_id == record.font_id)

    # 3. 回退机制
    fallback_family = manager.resolve_family("绝对不存在的字体XYZ")
    check("不存在字体回退系统默认", fallback_family != "绝对不存在的字体XYZ")
    font = manager.get_font("绝对不存在的字体XYZ", point_size=12)
    check("get_font 回退后家族名有效", manager.is_available(font.family()))
    hit = manager.get_font(record.family, point_size=12)
    check("get_font 命中已安装家族", hit.family() == record.family)

    # 4. 注册表持久化：重置单例后记录恢复
    FontManager._instance = None
    reloaded = get_font_manager()
    check(
        "单例重置后注册表恢复记录",
        any(r.font_id == record.font_id for r in reloaded.list_fonts()),
    )

    # 5. 卸载
    check("卸载返回 True", reloaded.uninstall_font(record.font_id))
    check("卸载后列表无记录",
          all(r.font_id != record.font_id for r in reloaded.list_fonts()))
    check("重复卸载返回 False", not reloaded.uninstall_font(record.font_id))

    # 6. PluginServices 注入字段存在
    check(
        "PluginServices 含 font_manager 字段",
        "font_manager" in PluginServices.__dataclass_fields__,
    )

    print(f"\n冒烟结果: {'全部通过' if failures == 0 else f'{failures} 项失败'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
