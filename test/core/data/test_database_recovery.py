"""数据库损坏隔离、启动备份、恢复点与关闭语义测试。"""

import datetime as dt
import hashlib
import importlib
import json
import os
import sqlite3
from dataclasses import replace as replace_dataclass
from pathlib import Path

import pytest

from core.data import DataProvider, DataNamespace, DataProviderError
from core.data.sqlite_backend import SQLiteBackend, SQLiteBackendError


CORE_TABLES = """
CREATE TABLE plugins (
    instance_id TEXT PRIMARY KEY,
    plugin_type TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE plugin_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instance_id TEXT NOT NULL,
    namespace TEXT NOT NULL,
    key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
    UNIQUE(instance_id, namespace, key)
);
CREATE TABLE active_instances (
    plugin_type TEXT PRIMARY KEY,
    instance_id TEXT NOT NULL
);
CREATE TABLE db_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
CORRUPT_BYTES = b"not-a-sqlite-database" * 8
WAL_BYTES = b"preexisting-wal"
SHM_BYTES = b"preexisting-shm"


@pytest.fixture(autouse=True)
def mock_sqlite_logger(mocker):
    """补齐根夹具未覆盖的 SQLite 日志引用，避免单例被 MagicMock 替换。"""
    return mocker.patch("core.data.sqlite_backend.LoggerManager").return_value


@pytest.fixture(autouse=True)
def reset_provider_singleton():
    """每个测试使用独立单例，并关闭真实 SQLite 连接。"""
    DataProvider._instance = None
    yield
    provider = DataProvider._instance
    backend = getattr(provider, "_backend", None)
    if backend is not None:
        backend.close()
    DataProvider._instance = None


@pytest.fixture
def recovery_module():
    """延迟导入待实现模块，使 RED 出现在测试而非收集阶段。"""
    return importlib.import_module("core.data.recovery")


def _provider(tmp_path: Path) -> DataProvider:
    """在指定临时目录创建 DataProvider。"""
    DataProvider._instance = None
    return DataProvider(data_dir=str(tmp_path), data_filename="test.json")


def _create_valid_database(tmp_path: Path) -> DataProvider:
    """创建含一条用户数据的有效数据库。"""
    provider = _provider(tmp_path)
    provider.register_plugin("p1", "TypeA")
    provider.set_plugin_data("p1", "key", {"value": 7})
    return provider


def _write_preexisting_sidecars(database: Path) -> None:
    """建立带可识别内容的启动前 WAL/SHM 文件。"""
    Path(f"{database}-wal").write_bytes(WAL_BYTES)
    Path(f"{database}-shm").write_bytes(SHM_BYTES)


def _assert_file_bytes(path: Path, expected: bytes) -> None:
    """断言文件仍存在且字节完全未变。"""
    assert path.exists()
    assert path.read_bytes() == expected


def _integrity(database: Path) -> str:
    """使用独立连接执行真实 integrity_check。"""
    connection = sqlite3.connect(database)
    try:
        return connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()


def test_existing_valid_database_reopens_with_data_backup_and_integrity(tmp_path: Path) -> None:
    """正常既有库重启保留数据，启动前恢复点有效且完整性为 ok。"""
    provider = _create_valid_database(tmp_path)
    provider._backend.close()

    reopened = _provider(tmp_path)

    assert reopened.get_plugin_data("p1", "key") == {"value": 7}
    backups = list(tmp_path.glob("test.db.backup-*"))
    assert len(backups) == 1
    assert _integrity(tmp_path / "test.db") == "ok"
    assert (backups[0] / "test.db").exists()


def test_classify_missing_empty_valid_and_corrupt(tmp_path: Path, recovery_module) -> None:
    """分类覆盖不存在、零字节、合法库和损坏库四种边界。"""
    database = tmp_path / "test.db"
    recovery = recovery_module.DatabaseRecovery()
    assert recovery.classify_existing_database(database) is recovery_module.DatabaseState.MISSING
    database.write_bytes(b"")
    assert recovery.classify_existing_database(database) is recovery_module.DatabaseState.EMPTY
    _create_valid_database(tmp_path)._backend.close()
    assert recovery.classify_existing_database(database) is recovery_module.DatabaseState.VALID
    database.write_bytes(CORRUPT_BYTES)
    assert recovery.classify_existing_database(database) is recovery_module.DatabaseState.CORRUPT


@pytest.mark.parametrize(
    ("error", "expected_state"),
    [
        (sqlite3.OperationalError("database is locked"), "LOCKED"),
        (PermissionError("permission denied"), "IO_ERROR"),
        (OSError("simulated I/O error"), "IO_ERROR"),
    ],
)
def test_classify_lock_permission_and_io_errors(
    tmp_path: Path, recovery_module, monkeypatch: pytest.MonkeyPatch, error, expected_state: str
) -> None:
    """锁定、权限与 I/O 错误必须明确分类，绝不能视为新库。"""
    database = tmp_path / "test.db"
    database.write_bytes(b"nonempty")
    monkeypatch.setattr(recovery_module.sqlite3, "connect", lambda *args, **kwargs: (_ for _ in ()).throw(error))
    recovery = recovery_module.DatabaseRecovery()
    assert recovery.classify_existing_database(database) is recovery_module.DatabaseState[expected_state]


def test_corrupt_existing_database_preserves_main_wal_shm_and_quarantines(tmp_path: Path) -> None:
    """损坏既有库初始化失败时原三文件不变，并留下同目录隔离副本。"""
    database = tmp_path / "test.db"
    database.write_bytes(CORRUPT_BYTES)
    _write_preexisting_sidecars(database)

    with pytest.raises(DataProviderError) as caught:
        _provider(tmp_path)

    assert not isinstance(caught.value, sqlite3.Error)
    _assert_file_bytes(database, CORRUPT_BYTES)
    _assert_file_bytes(Path(f"{database}-wal"), WAL_BYTES)
    _assert_file_bytes(Path(f"{database}-shm"), SHM_BYTES)
    quarantines = list(tmp_path.glob("test.db.quarantine-*"))
    assert len(quarantines) == 1
    _assert_file_bytes(quarantines[0] / database.name, CORRUPT_BYTES)
    _assert_file_bytes(quarantines[0] / f"{database.name}-wal", WAL_BYTES)
    _assert_file_bytes(quarantines[0] / f"{database.name}-shm", SHM_BYTES)
    assert "人工恢复" in str(caught.value)


@pytest.mark.parametrize(
    "error",
    [
        sqlite3.OperationalError("database is locked"),
        PermissionError("permission denied"),
        OSError("simulated I/O error"),
        sqlite3.DatabaseError("disk I/O error"),
    ],
)
def test_core_table_probe_errors_never_delete_existing_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    """核心表探测异常不得进入新建、空库替代或删除路径。"""
    provider = _create_valid_database(tmp_path)
    database = provider._backend.db_file
    provider._backend.close()
    original = database.read_bytes()
    monkeypatch.setattr(SQLiteBackend, "_has_core_tables", lambda self: (_ for _ in ()).throw(error))

    with pytest.raises(DataProviderError) as caught:
        _provider(tmp_path)

    assert not isinstance(caught.value, sqlite3.Error)
    _assert_file_bytes(database, original)


def test_quarantine_failure_stops_and_preserves_original(
    tmp_path: Path, recovery_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    """隔离副本无法创建时必须停止并提示人工恢复，不得清空原库。"""
    database = tmp_path / "test.db"
    database.write_bytes(CORRUPT_BYTES)
    monkeypatch.setattr(
        recovery_module.shutil, "copy2", lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("denied"))
    )

    with pytest.raises(DataProviderError, match="人工恢复"):
        _provider(tmp_path)

    _assert_file_bytes(database, CORRUPT_BYTES)
    assert not list(tmp_path.glob("test.db.quarantine-*"))


def test_new_database_migration_failure_cleans_only_new_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """本次新建且迁移失败的临时库可清理，原始 JSON 必须完整保留。"""
    source = {"plugins": {}, "active_instances": {}}
    json_file = tmp_path / "test.json"
    json_file.write_text(json.dumps(source), encoding="utf-8")

    def fail_migration(self, connection, data) -> None:
        raise RuntimeError("controlled migration failure")

    monkeypatch.setattr(SQLiteBackend, "_migrate_json_to_sqlite", fail_migration)
    with pytest.raises(DataProviderError):
        _provider(tmp_path)

    assert json.loads(json_file.read_text(encoding="utf-8")) == source
    assert not (tmp_path / "test.db").exists()
    assert not (tmp_path / "test.db-wal").exists()
    assert not (tmp_path / "test.db-shm").exists()


def test_new_database_with_committed_user_data_is_never_cleaned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """新库已提交用户数据后，后续初始化失败也只能保留而不能清理。"""
    source = {
        "plugins": {
            "p1": {"type": "TypeA", "active": False, "private": {"key": "user-data"}, "public": {}}
        },
        "active_instances": {},
    }
    json_file = tmp_path / "test.json"
    json_file.write_text(json.dumps(source), encoding="utf-8")
    monkeypatch.setattr(
        SQLiteBackend,
        "migrate_json_file_with_backup",
        lambda self: (_ for _ in ()).throw(OSError("controlled backup rename failure")),
    )

    with pytest.raises(DataProviderError):
        _provider(tmp_path)

    database = tmp_path / "test.db"
    assert database.exists()
    assert json.loads(json_file.read_text(encoding="utf-8")) == source
    connection = sqlite3.connect(database)
    try:
        value = connection.execute(
            "SELECT value_json FROM plugin_data WHERE instance_id='p1' AND key='key'"
        ).fetchone()[0]
    finally:
        connection.close()
    assert json.loads(value) == "user-data"


def test_preexisting_empty_database_is_not_cleaned_after_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """零字节也是启动前既有文件，初始化异常后不得删除。"""
    database = tmp_path / "test.db"
    database.write_bytes(b"")
    monkeypatch.setattr(
        SQLiteBackend, "_create_tables", lambda self, connection: (_ for _ in ()).throw(OSError("write failed"))
    )

    with pytest.raises(DataProviderError):
        _provider(tmp_path)

    assert database.exists()


def test_preexisting_sidecars_survive_failed_new_database_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """主库启动前不存在但 WAL/SHM 已存在时，不满足安全清理条件。"""
    database = tmp_path / "test.db"
    _write_preexisting_sidecars(database)
    monkeypatch.setattr(
        SQLiteBackend, "_create_tables", lambda self, connection: (_ for _ in ()).throw(OSError("write failed"))
    )

    with pytest.raises(DataProviderError):
        _provider(tmp_path)

    _assert_file_bytes(Path(f"{database}-wal"), WAL_BYTES)
    _assert_file_bytes(Path(f"{database}-shm"), SHM_BYTES)


def test_existing_schema_migration_failure_preserves_source_and_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """既有库迁移失败保留来源数据，备份仍是迁移前可恢复版本。"""
    provider = _create_valid_database(tmp_path)
    provider._backend.close()

    def fail_upgrade(self, connection) -> None:
        raise SQLiteBackendError("controlled schema migration failure")

    monkeypatch.setattr(importlib.import_module("core.data.sqlite_backend"), "TARGET_SCHEMA_VERSION", 2)
    monkeypatch.setattr(SQLiteBackend, "_upgrade_schema", fail_upgrade)
    with pytest.raises(DataProviderError):
        _provider(tmp_path)

    backups = list(tmp_path.glob("test.db.backup-*"))
    assert len(backups) == 1
    backup = backups[0] / "test.db"
    assert _integrity(backup) == "ok"
    connection = sqlite3.connect(backup)
    try:
        version = connection.execute("SELECT value FROM db_metadata WHERE key='schema_version'").fetchone()[0]
        value = connection.execute(
            "SELECT value_json FROM plugin_data WHERE instance_id='p1' AND key='key'"
        ).fetchone()[0]
    finally:
        connection.close()
    assert version == "1"
    assert json.loads(value) == {"value": 7}
    connection = sqlite3.connect(tmp_path / "test.db")
    try:
        original_version = connection.execute(
            "SELECT value FROM db_metadata WHERE key='schema_version'"
        ).fetchone()[0]
        original_value = connection.execute(
            "SELECT value_json FROM plugin_data WHERE instance_id='p1' AND key='key'"
        ).fetchone()[0]
    finally:
        connection.close()
    assert original_version == "1"
    assert json.loads(original_value) == {"value": 7}


def test_existing_high_version_database_is_preserved(tmp_path: Path) -> None:
    """高于代码目标版本的既有库明确报错，且来源与启动备份均保留。"""
    provider = _create_valid_database(tmp_path)
    connection = provider._backend._connect()
    connection.execute("UPDATE db_metadata SET value='99' WHERE key='schema_version'")
    provider._backend.close()

    with pytest.raises(DataProviderError, match="99"):
        _provider(tmp_path)

    assert _integrity(tmp_path / "test.db") == "ok"
    assert len(list(tmp_path.glob("test.db.backup-*"))) == 1
    connection = sqlite3.connect(tmp_path / "test.db")
    try:
        assert connection.execute("SELECT value FROM db_metadata WHERE key='schema_version'").fetchone()[0] == "99"
    finally:
        connection.close()


def test_valid_non_core_database_is_not_replaced(tmp_path: Path) -> None:
    """合法但无核心表的既有库可在保留原用户表的前提下补齐框架表。"""
    database = tmp_path / "test.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE user_table (value TEXT)")
    connection.execute("INSERT INTO user_table VALUES ('keep')")
    connection.commit()
    connection.close()

    _provider(tmp_path)

    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT value FROM user_table").fetchone()[0] == "keep"
    finally:
        connection.close()
    assert len(list(tmp_path.glob("test.db.backup-*"))) == 1


def test_backup_and_recovery_point_verify_checksum_and_integrity(
    tmp_path: Path, recovery_module
) -> None:
    """启动备份包含原文件校验和，恢复点可独立通过完整性验证。"""
    provider = _create_valid_database(tmp_path)
    provider._backend.close()
    recovery = recovery_module.DatabaseRecovery()

    report = recovery.create_backup(provider._backend.db_file, "测试启动备份")

    assert report.recovery_path.parent == tmp_path
    assert report.integrity == "ok"
    recovery.verify_recovery_point(report)
    copied = report.recovery_path / "test.db"
    assert hashlib.sha256(copied.read_bytes()).hexdigest() == report.checksums["test.db"]
    assert _integrity(copied) == "ok"


def test_recovery_point_tampering_is_rejected(tmp_path: Path, recovery_module) -> None:
    """恢复点任一文件被篡改时校验必须失败，不得用于静默恢复。"""
    provider = _create_valid_database(tmp_path)
    provider._backend.close()
    recovery = recovery_module.DatabaseRecovery()
    report = recovery.create_backup(provider._backend.db_file, "测试篡改")
    (report.recovery_path / "test.db").write_bytes(CORRUPT_BYTES)

    with pytest.raises(recovery_module.DatabaseRecoveryError, match="校验"):
        recovery.verify_recovery_point(report)


def test_close_is_idempotent_and_provider_can_reopen(tmp_path: Path) -> None:
    """统一 close 可重复调用，关闭后按既有惰性连接语义可重新打开。"""
    provider = _create_valid_database(tmp_path)

    provider.close()
    provider.close()

    assert provider._backend._conn is None
    assert provider.get_plugin_data("p1", "key") == {"value": 7}
    provider.close()
    assert provider._backend._conn is None


def test_json_backend_close_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """旧 JSON 应急后端同样支持幂等 close，不改变其持久化语义。"""
    monkeypatch.setenv("INSTRUCTIONX_DATAPROVIDER_BACKEND", "json")
    provider = _provider(tmp_path)
    provider.register_plugin("p1", "TypeA")

    provider.close()
    provider.close()

    assert provider.get_active_instance("TypeA") is None


# ---------------------------------------------------------------------------
# 评审回归：快照目录碰撞与分阶段恢复
# ---------------------------------------------------------------------------


def _write_current_files(database: Path) -> dict[str, bytes | None]:
    """写入一组可识别的故障前主库/WAL/SHM 状态并返回期望字节。"""
    expected = {
        "": b"current-main-version",
        "-wal": b"current-wal-version",
        "-shm": b"current-shm-version",
    }
    for suffix, content in expected.items():
        Path(f"{database}{suffix}").write_bytes(content)
    return expected


def _assert_database_state(database: Path, expected: dict[str, bytes | None]) -> None:
    """逐文件比较存在性和字节，缺失状态也必须完全一致。"""
    for suffix, content in expected.items():
        path = Path(f"{database}{suffix}")
        if content is None:
            assert not path.exists()
        else:
            _assert_file_bytes(path, content)


def _main_only_report(tmp_path: Path, recovery_module):
    """创建只有主库的合法恢复点，再布置另一组当前文件。"""
    provider = _create_valid_database(tmp_path)
    database = provider._backend.db_file
    provider._backend.close()
    recovery = recovery_module.DatabaseRecovery()
    report = recovery.create_backup(database, "故障注入恢复")
    for snapshot in report.recovery_path.iterdir():
        if snapshot.name != database.name:
            snapshot.unlink()
    report = replace_dataclass(report, checksums={database.name: report.checksums[database.name]})
    expected = _write_current_files(database)
    return recovery, database, report, expected


def _add_controlled_sidecars(report):
    """给恢复点加入受控伴生文件，覆盖多文件替换失败分支。"""
    checksums = dict(report.checksums)
    for suffix, content in (("-wal", WAL_BYTES), ("-shm", SHM_BYTES)):
        target = report.recovery_path / f"{report.source_path.name}{suffix}"
        target.write_bytes(content)
        checksums[target.name] = hashlib.sha256(content).hexdigest()
    return replace_dataclass(report, checksums=checksums)


@pytest.mark.parametrize(
    ("method_name", "prefix"),
    [("create_backup", "backup"), ("quarantine", "quarantine")],
)
def test_snapshot_directory_collision_never_deletes_existing_directory(
    tmp_path: Path, recovery_module, monkeypatch: pytest.MonkeyPatch, method_name: str, prefix: str
) -> None:
    """backup/quarantine 目标目录碰撞时，既有目录和标记文件必须原样保留。"""
    provider = _create_valid_database(tmp_path)
    database = provider._backend.db_file
    provider._backend.close()
    real_datetime = dt.datetime

    class FixedDateTime(real_datetime):
        @classmethod
        def now(cls, timezone=None):
            return real_datetime(2026, 1, 2, 3, 4, 5, 123456, tzinfo=dt.timezone.utc)

    monkeypatch.setattr(recovery_module.dt, "datetime", FixedDateTime)
    destination = tmp_path / f"test.db.{prefix}-20260102T030405.123456"
    destination.mkdir()
    marker = destination / "do-not-delete.marker"
    marker.write_bytes(b"existing-user-recovery-point")
    recovery = recovery_module.DatabaseRecovery()

    with pytest.raises(recovery_module.DatabaseRecoveryError):
        getattr(recovery, method_name)(database, "目录碰撞回归")

    _assert_file_bytes(marker, b"existing-user-recovery-point")
    assert destination.is_dir()


def test_restore_copy_failure_preserves_current_files_and_recovery_point(
    tmp_path: Path, recovery_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    """暂存复制中途失败不得截断当前主库，恢复点也必须保留。"""
    recovery, database, report, expected = _main_only_report(tmp_path, recovery_module)

    def fail_after_partial_copy(source, destination) -> None:
        Path(destination).write_bytes(b"partial-copy")
        raise OSError("controlled copy failure")

    monkeypatch.setattr(recovery_module.shutil, "copy2", fail_after_partial_copy)
    with pytest.raises(recovery_module.DatabaseRecoveryError, match="人工恢复"):
        recovery.restore_recovery_point(report)

    _assert_database_state(database, expected)
    recovery.verify_recovery_point(report)


def test_restore_replace_failure_rolls_back_mixed_generation(
    tmp_path: Path, recovery_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    """第二次 os.replace 失败后，已替换主库也必须回滚到故障前版本。"""
    recovery, database, report, expected = _main_only_report(tmp_path, recovery_module)
    report = _add_controlled_sidecars(report)
    original_replace = os.replace
    replace_calls = 0

    def fail_second_replace(source, destination) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("controlled replace failure")
        original_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_second_replace)
    with pytest.raises(recovery_module.DatabaseRecoveryError, match="人工恢复"):
        recovery.restore_recovery_point(report)

    assert replace_calls >= 2
    _assert_database_state(database, expected)
    recovery.verify_recovery_point(report)


def test_restore_delete_failure_rolls_back_all_files(
    tmp_path: Path, recovery_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    """删除新状态不需要的 WAL 失败时，主库和全部伴生状态均回滚。"""
    recovery, database, report, expected = _main_only_report(tmp_path, recovery_module)
    original_unlink = Path.unlink
    wal = Path(f"{database}-wal")
    failed = False

    def fail_wal_unlink_once(path, *args, **kwargs) -> None:
        nonlocal failed
        if path == wal and not failed:
            failed = True
            raise OSError("controlled delete failure")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_wal_unlink_once)
    with pytest.raises(recovery_module.DatabaseRecoveryError, match="人工恢复"):
        recovery.restore_recovery_point(report)

    assert failed is True
    _assert_database_state(database, expected)
    recovery.verify_recovery_point(report)


def test_restore_real_wal_recovers_committed_data(tmp_path: Path, recovery_module) -> None:
    """真实 WAL 中已提交但未 checkpoint 的数据随恢复点完整恢复。"""
    database = tmp_path / "test.db"
    writer = sqlite3.connect(database)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.executescript(CORE_TABLES)
    writer.execute("INSERT INTO db_metadata VALUES ('schema_version', '1')")
    writer.execute("INSERT INTO plugins VALUES ('p1', 'TypeA', 0)")
    writer.execute(
        "INSERT INTO plugin_data (instance_id, namespace, key, value_json) VALUES (?, ?, ?, ?)",
        ("p1", "private", "key", '"committed-in-wal"'),
    )
    writer.commit()
    reader = sqlite3.connect(database)
    reader.execute("BEGIN")
    assert reader.execute("SELECT value_json FROM plugin_data").fetchone()[0] == '"committed-in-wal"'
    writer.close()

    recovery = recovery_module.DatabaseRecovery()
    report = recovery.create_backup(database, "真实 WAL 恢复")
    assert "test.db-wal" in report.checksums
    reader.close()
    _write_current_files(database)

    recovery.restore_recovery_point(report)

    connection = sqlite3.connect(database)
    try:
        value = connection.execute("SELECT value_json FROM plugin_data").fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
    assert json.loads(value) == "committed-in-wal"
    assert integrity == "ok"


def test_backup_copy_failure_preserves_source_and_removes_only_new_snapshot(
    tmp_path: Path, recovery_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    """备份复制失败保留原库，仅清理本次新建的不完整备份目录。"""
    provider = _create_valid_database(tmp_path)
    database = provider._backend.db_file
    provider._backend.close()
    original = database.read_bytes()

    def fail_after_partial_copy(source, destination) -> None:
        Path(destination).write_bytes(b"partial-backup")
        raise OSError("controlled backup copy failure")

    monkeypatch.setattr(recovery_module.shutil, "copy2", fail_after_partial_copy)
    recovery = recovery_module.DatabaseRecovery()
    with pytest.raises(recovery_module.DatabaseRecoveryError, match="人工恢复"):
        recovery.create_backup(database, "备份失败回归")

    _assert_file_bytes(database, original)
    assert not list(tmp_path.glob("test.db.backup-*"))


def test_final_integrity_failure_restores_original_version_and_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """最终 integrity_check 失败时，原库版本、用户值和主库字节全部恢复。"""
    provider = _create_valid_database(tmp_path)
    database = provider._backend.db_file
    provider._backend.close()
    original = database.read_bytes()

    def fail_integrity(self) -> None:
        raise SQLiteBackendError("controlled final integrity failure")

    monkeypatch.setattr(SQLiteBackend, "_validate_integrity", fail_integrity)
    with pytest.raises(DataProviderError, match="controlled final integrity failure"):
        _provider(tmp_path)

    _assert_file_bytes(database, original)
    connection = sqlite3.connect(database)
    try:
        version = connection.execute("SELECT value FROM db_metadata WHERE key='schema_version'").fetchone()[0]
        value = connection.execute("SELECT value_json FROM plugin_data").fetchone()[0]
    finally:
        connection.close()
    assert version == "1"
    assert json.loads(value) == {"value": 7}


def test_sqlite_close_exception_still_releases_connection(tmp_path: Path) -> None:
    """SQLite close 异常被记录后仍释放连接，后续 close 幂等。"""
    provider = _create_valid_database(tmp_path)

    class FailingCloseConnection:
        def __init__(self) -> None:
            self.calls = 0

        def close(self) -> None:
            self.calls += 1
            raise sqlite3.OperationalError("controlled close failure")

    connection = FailingCloseConnection()
    provider._backend._conn = connection
    provider.close()
    provider.close()

    assert connection.calls == 1
    assert provider._backend._conn is None
