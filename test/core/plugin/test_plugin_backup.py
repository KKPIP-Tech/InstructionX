# -*- coding: utf-8 -*-
"""插件目录包外文件检测与快照（core/plugin/plugin_backup.py）测试

测试目标: 覆盖安装前对插件目录内「包外文件」的检测、快照与份数裁剪
测试范围:

- ``collect_extra_files``：只报新包中没有的文件；排除 ``.plugin_info.json``、
  ``__pycache__``、``*.pyc/.pyo``；结果按 posix 相对路径排序；旧目录不存在时返回空
- ``snapshot_plugin_dir``：整目录快照（保留 ``.plugin_info.json`` 便于追溯数据归属、
  忽略字节码）、目录名带时间戳与版本、旧目录不存在时返回 None、版本号含分隔符时被消毒
- 快照份数上限：超出 ``MAX_BACKUPS_PER_PLUGIN`` 时淘汰最旧
"""

from pathlib import Path

from core.plugin.plugin_backup import (
    MAX_BACKUPS_PER_PLUGIN,
    collect_extra_files,
    snapshot_plugin_dir,
)

#: 新包内容（作为对照基准）
_PACKAGE_FILES = {"IXPlugin.json": "{}", "entrance.py": "# fake\n"}


def make_dir(base: Path, files: dict) -> Path:
    """按 {相对路径: 内容} 创建目录树并返回根目录"""
    base.mkdir(parents=True, exist_ok=True)
    for rel_path, content in files.items():
        target = base / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return base


class TestCollectExtraFiles:
    """包外文件检测"""

    def test_detects_files_missing_from_package(self, tmp_path):
        """旧目录中包内没有的文件被识别出来（按相对路径排序）"""
        old = make_dir(tmp_path / "old", {**_PACKAGE_FILES, "runtime.dat": "x",
                                          "config/user.json": "{}"})
        new = make_dir(tmp_path / "new", _PACKAGE_FILES)

        assert collect_extra_files(old, new) == ["config/user.json", "runtime.dat"]

    def test_ignores_plugin_info_and_bytecode(self, tmp_path):
        """UUID 文件与字节码缓存不算包外文件"""
        old = make_dir(tmp_path / "old", {**_PACKAGE_FILES, ".plugin_info.json": "{}",
                                          "__pycache__/x.pyc": "\x00", "y.pyo": "\x00"})
        new = make_dir(tmp_path / "new", _PACKAGE_FILES)

        assert collect_extra_files(old, new) == []

    def test_identical_dirs_have_no_extra(self, tmp_path):
        """新旧目录内容一致时无包外文件"""
        old = make_dir(tmp_path / "old", _PACKAGE_FILES)
        new = make_dir(tmp_path / "new", _PACKAGE_FILES)

        assert collect_extra_files(old, new) == []

    def test_missing_old_dir_returns_empty(self, tmp_path):
        """旧目录不存在时返回空列表（全新安装场景）"""
        new = make_dir(tmp_path / "new", _PACKAGE_FILES)

        assert collect_extra_files(tmp_path / "not-exists", new) == []


class TestSnapshotPluginDir:
    """目录快照"""

    def test_snapshot_copies_content_with_timestamp_and_version(self, tmp_path):
        """快照包含旧目录内容，目录名带时间戳与版本号"""
        old = make_dir(tmp_path / "old", {**_PACKAGE_FILES, "runtime.dat": "x"})

        snapshot = snapshot_plugin_dir(old, tmp_path / "backup", "demo-plugin",
                                       "release.1.0.0")

        assert snapshot is not None and snapshot.is_dir()
        assert snapshot.parent == tmp_path / "backup" / "demo-plugin"
        assert snapshot.name.endswith("_release.1.0.0")
        assert (snapshot / "runtime.dat").read_text(encoding="utf-8") == "x"

    def test_snapshot_keeps_plugin_info_and_skips_bytecode(self, tmp_path):
        """快照保留 .plugin_info.json（追溯数据归属），忽略 __pycache__/pyc"""
        old = make_dir(tmp_path / "old", {**_PACKAGE_FILES, ".plugin_info.json": '{"id":"x"}',
                                          "__pycache__/x.pyc": "\x00"})

        snapshot = snapshot_plugin_dir(old, tmp_path / "backup", "demo-plugin")

        assert snapshot is not None
        assert (snapshot / ".plugin_info.json").is_file()
        assert not (snapshot / "__pycache__").exists()
        assert snapshot.name.endswith("_unknown")

    def test_missing_dir_returns_none(self, tmp_path):
        """旧目录不存在时不产生快照"""
        assert snapshot_plugin_dir(tmp_path / "not-exists", tmp_path / "backup",
                                   "demo-plugin") is None

    def test_version_separators_sanitized(self, tmp_path):
        """版本号中的路径分隔符被消毒，不产生额外目录层级"""
        old = make_dir(tmp_path / "old", _PACKAGE_FILES)

        snapshot = snapshot_plugin_dir(old, tmp_path / "backup", "demo-plugin",
                                       "release/1.0.0")

        assert snapshot is not None
        assert snapshot.parent == tmp_path / "backup" / "demo-plugin"

    def test_prunes_old_snapshots(self, tmp_path):
        """快照份数超过上限时淘汰最旧的，只保留最近 MAX_BACKUPS_PER_PLUGIN 份"""
        old = make_dir(tmp_path / "old", _PACKAGE_FILES)
        backup_root = tmp_path / "backup"

        for index in range(MAX_BACKUPS_PER_PLUGIN + 2):
            snapshot_plugin_dir(old, backup_root, "demo-plugin", f"release.{index}.0.0")

        snapshots = sorted((backup_root / "demo-plugin").iterdir())
        assert len(snapshots) == MAX_BACKUPS_PER_PLUGIN
        assert snapshots[-1].name.endswith(
            f"_release.{MAX_BACKUPS_PER_PLUGIN + 1}.0.0")
