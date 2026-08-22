"""i18n 子系统（core/i18n）冒烟验证脚本。

验证链路：XML 解析容错 → 语言代码解析（区域子标签回退）→ 框架取词
（命中/键级回退/组级回退/ERROR_TEXT/占位符）→ 语言切换与持久化 →
插件语言包注册、有效语言三级优先级、覆盖持久化、热卸载注销 →
插件取词门面（PluginI18nFacade）与声明默认语言登记 →
损坏配置备份重建。

运行：.venv\\Scripts\\python.exe scripts/smoke_i18n.py
"""

import shutil
import sys
from pathlib import Path

# 保证项目根目录在 sys.path（scripts/ 下直接运行时）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QCoreApplication

from core.i18n import (
    ERROR_TEXT,
    CatalogCache,
    I18nSettingsStore,
    load_catalog,
    resolve_language_code,
)
from core.i18n.facade import PluginI18nFacade
from core.i18n.language_manager import LanguageManager
from core.interfaces.i_localization import ILocalizationFacade

# 冒烟临时目录（temp/ 下，用完清理）
_SMOKE_DIR = Path(__file__).resolve().parent.parent / "temp" / "i18n_smoke"

# ===== 语言文件内容常量 =====
_ZH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<texts language="zh">
  <group name="common">
    <text key="ok">确定</text>
    <text key="language.self_name">简体中文</text>
  </group>
  <group name="demo">
    <text key="hello">你好</text>
    <text key="welcome">欢迎，{name}！共 {count} 项</text>
  </group>
</texts>
"""
# en 缺整个 demo 分组，common 内缺 language.self_name 键
_EN_XML = """<?xml version="1.0" encoding="UTF-8"?>
<texts language="en">
  <group name="common">
    <text key="ok">OK</text>
  </group>
</texts>
"""
_PLUGIN_ZH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<texts language="zh">
  <group name="main">
    <text key="title">插件标题</text>
    <text key="greeting">你好，{name}</text>
  </group>
</texts>
"""
# 插件 en 缺 greeting 键
_PLUGIN_EN_XML = """<?xml version="1.0" encoding="UTF-8"?>
<texts language="en">
  <group name="main">
    <text key="title">Plugin Title</text>
  </group>
</texts>
"""
_BROKEN_XML = "<texts language=\"bad\"><group>"  # 故意不闭合

_failures = 0


def check(name: str, condition: bool) -> None:
    """记录并打印一项检查结果"""
    global _failures
    if not condition:
        _failures += 1
    print(f"[{'PASS' if condition else 'FAIL'}] {name}")


def _reset_singleton() -> None:
    """重置 LanguageManager 单例（测试约定）"""
    LanguageManager._instance = None


def _make_manager(text_dir: Path, config_dir: Path) -> LanguageManager:
    """以注入路径构造全新的 LanguageManager"""
    _reset_singleton()
    return LanguageManager(text_dir=text_dir, settings_store=I18nSettingsStore(config_dir))


def _prepare_dirs() -> dict:
    """重建冒烟目录骨架，返回各子目录路径"""
    if _SMOKE_DIR.exists():
        shutil.rmtree(_SMOKE_DIR)
    dirs = {
        "text": _SMOKE_DIR / "text",
        "config": _SMOKE_DIR / "config",
        "plugin_a": _SMOKE_DIR / "plugin-a" / "text",
        "plugin_c": _SMOKE_DIR / "plugin-c" / "text",
        "plugin_b": _SMOKE_DIR / "plugin-b",  # 无 text/ 目录的插件
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def scenario_loader() -> None:
    """场景 1：XML 解析与容错"""
    print("\n== 场景 1：XML 解析与容错 ==")
    weird_dir = _SMOKE_DIR / "loader_case"
    weird_dir.mkdir(parents=True, exist_ok=True)
    (weird_dir / "zh.xml").write_text(_ZH_XML, encoding="utf-8")
    (weird_dir / "bad.xml").write_text(_BROKEN_XML, encoding="utf-8")
    # language 属性（zh）与文件名（fr）不一致
    (weird_dir / "fr.xml").write_text(_ZH_XML, encoding="utf-8")

    catalog = load_catalog(weird_dir / "zh.xml")
    check("正常文件解析成功", catalog is not None and catalog.language == "zh")
    check("分组解析完整", catalog.group_names() == ["common", "demo"])
    check("键值解析正确", catalog.get("common", "ok") == "确定")
    check("缺失键返回 None", catalog.get("common", "nope") is None)
    check("键总数统计正确", catalog.key_count() == 4)
    check("损坏文件返回 None", load_catalog(weird_dir / "bad.xml") is None)
    check("不存在文件返回 None", load_catalog(weird_dir / "xx.xml") is None)
    check("属性不一致仍以文件名为准", load_catalog(weird_dir / "fr.xml").language == "fr")

    cache = CatalogCache(weird_dir)
    check("扫描可用语言", cache.available_languages() == ["bad", "fr", "zh"])
    check("缓存命中同一对象", cache.get("zh") is cache.get("zh"))
    check("负缓存返回 None", cache.get("bad") is None)
    cache.invalidate("zh")
    check("失效后重新加载", cache.get("zh") is not None)

    check("区域子标签回退 zh-TW→zh", resolve_language_code("zh-TW", ["en", "zh"]) == "zh")
    check("精确匹配优先", resolve_language_code("en", ["en", "zh"]) == "en")
    check("不可用返回 None", resolve_language_code("ja", ["en", "zh"]) is None)


def scenario_framework_tr(dirs: dict) -> None:
    """场景 2：框架取词回退链与占位符"""
    print("\n== 场景 2：框架取词回退链 ==")
    (dirs["text"] / "zh.xml").write_text(_ZH_XML, encoding="utf-8")
    (dirs["text"] / "en.xml").write_text(_EN_XML, encoding="utf-8")
    manager = _make_manager(dirs["text"], dirs["config"])

    check("默认语言为 zh", manager.default_language() == "zh")
    check("初始当前语言为 zh", manager.current_language() == "zh")
    check("默认语言取词命中", manager.tr("common", "ok") == "确定")
    check("占位符注入", manager.tr("demo", "welcome", name="小明", count=3) == "欢迎，小明！共 3 项")
    check("占位符缺参容错返回模板",
          manager.tr("demo", "welcome") == "欢迎，{name}！共 {count} 项")
    check("默认语言缺键显示 ERROR_TEXT", manager.tr("demo", "missing") == ERROR_TEXT)

    check("切换到 en", manager.set_language("en"))
    check("en 命中", manager.tr("common", "ok") == "OK")
    check("en 缺键回退 zh", manager.tr("common", "language.self_name") == "简体中文")
    check("en 缺整个分组回退 zh", manager.tr("demo", "hello") == "你好")
    check("双语都缺键仍 ERROR_TEXT", manager.tr("demo", "missing") == ERROR_TEXT)

    check("拒绝不可用语言", not manager.set_language("ja"))
    check("区域子标签切换 zh-TW", manager.set_language("zh-TW"))
    check("zh-TW 经回退取到 zh 文案", manager.tr("demo", "hello") == "你好")


def scenario_language_signal_and_persist(dirs: dict) -> None:
    """场景 3：语言切换信号与持久化"""
    print("\n== 场景 3：切换信号与持久化 ==")
    manager = _make_manager(dirs["text"], dirs["config"])
    fired = []
    manager.language_changed.connect(fired.append)
    check("切换语言发射信号", manager.set_language("en") and fired == ["en"])
    check("同名切换不重复发射", manager.set_language("en") and fired == ["en"])

    persisted = (dirs["config"] / "i18n.json").read_text(encoding="utf-8")
    check("i18n.json 含 schema 版本", '"version": 1' in persisted)
    check("i18n.json 记录当前语言", '"current_language": "en"' in persisted)

    restored = _make_manager(dirs["text"], dirs["config"])
    check("重置单例后恢复当前语言", restored.current_language() == "en")
    check("默认语言不受切换影响", restored.default_language() == "zh")


def scenario_plugins(dirs: dict) -> None:
    """场景 4：插件语言包注册、有效语言与覆盖"""
    print("\n== 场景 4：插件语言包 ==")
    (dirs["plugin_a"] / "zh.xml").write_text(_PLUGIN_ZH_XML, encoding="utf-8")
    (dirs["plugin_a"] / "en.xml").write_text(_PLUGIN_EN_XML, encoding="utf-8")
    (dirs["plugin_c"] / "zh.xml").write_text(_PLUGIN_ZH_XML, encoding="utf-8")
    manager = _make_manager(dirs["text"], dirs["config"])

    check("注册含语言包插件", manager.register_plugin_texts(
        "uuid-a", dirs["plugin_a"].parent, declared_default="zh"))
    check("注册无 text/ 目录插件返回 False",
          not manager.register_plugin_texts("uuid-b", dirs["plugin_b"]))
    check("插件 A 可用语言", manager.plugin_available_languages("uuid-a") == ["en", "zh"])
    check("插件 B 无语言包", manager.plugin_available_languages("uuid-b") == [])

    manager.set_language("en")
    check("框架 en 时插件 A 有效语言 en", manager.effective_plugin_language("uuid-a") == "en")
    check("插件 C 仅 zh，有效语言回退 zh", manager.register_plugin_texts(
        "uuid-c", dirs["plugin_c"].parent) and manager.effective_plugin_language("uuid-c") == "zh")

    check("插件取词命中 en", manager.plugin_tr("uuid-a", "main", "title") == "Plugin Title")
    check("插件缺键回退其默认语言",
          manager.plugin_tr("uuid-a", "main", "greeting", name="小明") == "你好，小明")
    check("插件默认语言缺键显示 ERROR_TEXT",
          manager.plugin_tr("uuid-a", "main", "missing") == ERROR_TEXT)
    check("无语言包插件优雅降级返回键名",
          manager.plugin_tr("uuid-b", "main", "title") == "title")

    check("覆盖为 zh 生效", manager.set_plugin_language("uuid-a", "zh"))
    check("覆盖后有效语言 zh", manager.effective_plugin_language("uuid-a") == "zh")
    check("覆盖后取词走 zh", manager.plugin_tr("uuid-a", "main", "title") == "插件标题")
    check("拒绝插件未提供的语言", not manager.set_plugin_language("uuid-a", "fr"))
    fired = []
    manager.plugin_language_changed.connect(lambda pid, lang: fired.append((pid, lang)))
    check("清除覆盖发射信号", manager.set_plugin_language("uuid-a", None)
          and fired == [("uuid-a", "en")])
    check("清除覆盖后跟随框架", manager.effective_plugin_language("uuid-a") == "en")

    # 插件侧取词门面（PluginI18nFacade 绑定 plugin_id，全部委托 manager）
    facade_a = PluginI18nFacade("uuid-a", manager)
    check("门面取词与 plugin_tr 一致",
          facade_a.tr("main", "title") == manager.plugin_tr("uuid-a", "main", "title"))
    check("门面 has_catalog 为 True", facade_a.has_catalog())
    check("门面可用语言正确", facade_a.available_languages() == ["en", "zh"])
    check("门面有效语言正确", facade_a.current_language() == "en")
    facade_b = PluginI18nFacade("uuid-b", manager)
    check("无语言包插件门面取词优雅降级返回键名",
          facade_b.tr("main", "title") == "title" and not facade_b.has_catalog())

    # ILocalizationFacade 为抽象接口，不能直接实例化
    try:
        ILocalizationFacade()  # type: ignore[abstract]
        instantiable = True
    except TypeError:
        instantiable = False
    check("ILocalizationFacade 不可直接实例化", not instantiable)

    # 插件声明的默认语言登记（PluginManager 读取 IPluginInfo.default_language 后调用）
    manager.set_plugin_declared_default("uuid-a", "ja")
    check("声明默认语言登记生效", manager._registry.declared_default_of("uuid-a") == "ja")

    manager.unregister_plugin_texts("uuid-a")
    check("热卸载注销注册表", manager.plugin_available_languages("uuid-a") == [])


def scenario_corrupt_config(dirs: dict) -> None:
    """场景 5：损坏配置备份重建"""
    print("\n== 场景 5：损坏配置容错 ==")
    config_file = dirs["config"] / "i18n.json"
    config_file.write_text("{ 不是合法 JSON", encoding="utf-8")
    store = I18nSettingsStore(dirs["config"])
    settings = store.load_framework_settings()
    check("损坏配置按默认语言运行", settings["current_language"] == "zh")
    check("损坏文件已备份", (dirs["config"] / "i18n.json.corrupt.bak").exists())


def main() -> int:
    app = QCoreApplication([])  # noqa: F841（QObject 信号需要 QCoreApplication 实例）
    dirs = _prepare_dirs()

    scenario_loader()
    scenario_framework_tr(dirs)
    scenario_language_signal_and_persist(dirs)
    scenario_plugins(dirs)
    scenario_corrupt_config(dirs)

    shutil.rmtree(_SMOKE_DIR, ignore_errors=True)
    print(f"\n{'全部通过' if _failures == 0 else f'失败 {_failures} 项'}")
    return 0 if _failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
