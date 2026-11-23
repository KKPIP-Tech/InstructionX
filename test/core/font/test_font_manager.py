"""core/font 字体管理子系统测试。

覆盖：FontRecord 序列化、注册表持久化与损坏重建、install_font 正常/重复/
非法格式/文件缺失路径、uninstall_font、resolve_family 回退链、is_available、
PluginServices.font_manager 注入字段。

注意：测试通过 monkeypatch 将 data/fonts 重定向到 tmp_path，
不污染真实运行数据；每个用例重置 FontManager 单例。
"""

import json
import shutil
from pathlib import Path

import pytest

from core.font import FontInstallError, FontManager, FontRecord, get_font_manager
from core.font import manager as font_manager_module
from core.interfaces.plugin_services import PluginServices

# Windows 系统字体作为安装来源（CI 为 windows-latest）
_SOURCE_FONT_CANDIDATES = (
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
)


def _find_source_font() -> str:
    """挑选一个真实存在的系统字体文件作为安装源"""
    for candidate in _SOURCE_FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    pytest.skip("未找到可用的系统字体文件")


@pytest.fixture()
def fresh_manager(tmp_path, monkeypatch, qapp):
    """构造隔离的 FontManager：存储目录指向 tmp_path，单例已重置"""
    monkeypatch.setattr(font_manager_module, "_FONTS_DIR", tmp_path / "fonts")
    monkeypatch.setattr(
        font_manager_module, "_REGISTRY_FILE", tmp_path / "fonts" / "fonts.json")
    FontManager._instance = None
    manager = get_font_manager()
    yield manager
    # 用例结束后重置单例，避免跨用例状态泄漏
    FontManager._instance = None


class TestFontRecord:
    """FontRecord 数据模型"""

    def test_to_dict_from_dict_roundtrip(self):
        """序列化与反序列化往返后字段一致"""
        record = FontRecord(
            font_id="demo-font", family="Demo Font", style="Regular",
            filename="demo-font.ttf", source="user",
            installed_at="2026-08-02T12:00:00",
        )
        assert FontRecord.from_dict(record.to_dict()) == record

    def test_from_dict_missing_key_raises(self):
        """必需字段缺失时抛 KeyError"""
        with pytest.raises(KeyError):
            FontRecord.from_dict({"font_id": "x"})


class TestInstallFont:
    """install_font 安装路径"""

    def test_install_success(self, fresh_manager, tmp_path):
        """正常安装：返回记录、文件复制到位、注册表写入"""
        record = fresh_manager.install_font(_find_source_font(), source="test")
        assert record.family
        assert record.font_id
        fonts_dir = tmp_path / "fonts"
        assert (fonts_dir / record.filename).is_file()
        registry = json.loads(
            (fonts_dir / "fonts.json").read_text(encoding="utf-8"))
        assert registry["version"] == 1
        assert len(registry["fonts"]) == 1
        assert fresh_manager.is_available(record.family)

    def test_install_duplicate_returns_existing(self, fresh_manager):
        """重复安装同名字体返回既有记录，注册表不膨胀"""
        source = _find_source_font()
        first = fresh_manager.install_font(source)
        second = fresh_manager.install_font(source)
        assert first.font_id == second.font_id
        assert len(fresh_manager.list_fonts()) == 1

    def test_install_unsupported_suffix(self, fresh_manager, tmp_path):
        """非字体扩展名抛 FontInstallError"""
        fake = tmp_path / "not_a_font.txt"
        fake.write_text("x", encoding="utf-8")
        with pytest.raises(FontInstallError):
            fresh_manager.install_font(str(fake))

    def test_install_missing_file(self, fresh_manager, tmp_path):
        """文件不存在抛 FontInstallError"""
        with pytest.raises(FontInstallError):
            fresh_manager.install_font(str(tmp_path / "不存在.ttf"))


class TestUninstallFont:
    """uninstall_font 卸载路径"""

    def test_uninstall_success(self, fresh_manager, tmp_path):
        """卸载成功：返回 True、文件删除、注册表清空"""
        record = fresh_manager.install_font(_find_source_font())
        assert fresh_manager.uninstall_font(record.font_id) is True
        assert fresh_manager.list_fonts() == []
        assert not (tmp_path / "fonts" / record.filename).exists()

    def test_uninstall_unknown_returns_false(self, fresh_manager):
        """卸载不存在的字体返回 False"""
        assert fresh_manager.uninstall_font("不存在的字体") is False


class TestFallback:
    """resolve_family / get_font 回退机制"""

    def test_resolve_requested_available(self, fresh_manager):
        """请求字体可用时原样返回"""
        record = fresh_manager.install_font(_find_source_font())
        assert fresh_manager.resolve_family(record.family) == record.family

    def test_resolve_fallback_chain(self, fresh_manager):
        """请求不可用时依次走回退列表"""
        record = fresh_manager.install_font(_find_source_font())
        resolved = fresh_manager.resolve_family(
            "绝对不存在的字体XYZ", fallbacks=[record.family])
        assert resolved == record.family

    def test_resolve_system_default(self, fresh_manager):
        """全部不可用时回退系统默认字体"""
        resolved = fresh_manager.resolve_family("绝对不存在的字体XYZ")
        assert resolved != "绝对不存在的字体XYZ"
        assert fresh_manager.is_available(resolved)

    def test_get_font_fallback(self, fresh_manager):
        """get_font 对不可用家族返回回退后的可用字体"""
        font = fresh_manager.get_font("绝对不存在的字体XYZ", point_size=12)
        assert font.pointSize() == 12
        assert fresh_manager.is_available(font.family())


class TestRegistry:
    """注册表持久化与损坏恢复"""

    def test_persistence_across_instances(self, fresh_manager, tmp_path):
        """重置单例后新实例从注册表恢复记录"""
        record = fresh_manager.install_font(_find_source_font())
        FontManager._instance = None
        reloaded = get_font_manager()
        try:
            assert any(
                r.font_id == record.font_id for r in reloaded.list_fonts())
        finally:
            FontManager._instance = None

    def test_missing_font_file_pruned(self, fresh_manager, tmp_path):
        """字体文件被外部删除后，重启加载时剔除该记录"""
        record = fresh_manager.install_font(_find_source_font())
        (tmp_path / "fonts" / record.filename).unlink()
        FontManager._instance = None
        reloaded = get_font_manager()
        try:
            assert reloaded.list_fonts() == []
        finally:
            FontManager._instance = None

    def test_corrupt_registry_recovered(self, fresh_manager, tmp_path):
        """注册表损坏时按空表运行而不抛异常"""
        fonts_dir = tmp_path / "fonts"
        fonts_dir.mkdir(parents=True)
        (fonts_dir / "fonts.json").write_text("{损坏的JSON", encoding="utf-8")
        FontManager._instance = None
        reloaded = get_font_manager()
        try:
            assert reloaded.list_fonts() == []
        finally:
            FontManager._instance = None


class TestPluginServices:
    """插件服务容器注入"""

    def test_font_manager_field_defaults_none(self):
        """font_manager 字段默认 None（向后兼容既有构造）"""
        services = PluginServices(
            llm_facade=None, data_provider=None, task_manager=None, logger=None)
        assert services.font_manager is None
