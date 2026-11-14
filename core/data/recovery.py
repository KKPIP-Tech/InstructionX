"""SQLite 启动前分类、备份、损坏隔离与恢复点校验。"""

import datetime as dt
import hashlib
import os
import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Dict, Optional


CLASSIFY_TIMEOUT_SECONDS = 0.05
CHECKSUM_CHUNK_BYTES = 1024 * 1024
INTEGRITY_CHECK_SQL = "PRAGMA integrity_check"
INTEGRITY_OK = "ok"
BACKUP_PREFIX = "backup"
QUARANTINE_PREFIX = "quarantine"
RESTORE_PREFIX = "restore"
SIDECAR_SUFFIXES = ("", "-wal", "-shm")


class DatabaseState(Enum):
    """启动前数据库物理状态，区分可初始化与必须停止的情况。"""

    MISSING = "missing"
    EMPTY = "empty"
    VALID = "valid"
    CORRUPT = "corrupt"
    LOCKED = "locked"
    IO_ERROR = "io_error"


class DatabaseRecoveryError(Exception):
    """备份、隔离或恢复点校验失败，调用方应停止数据库初始化。"""


@dataclass(frozen=True)
class RecoveryReport:
    """描述一个同目录恢复点及其逐文件 SHA-256 校验和。"""

    source_path: Path
    recovery_path: Path
    reason: str
    created_at: str
    checksums: Dict[str, str]
    integrity: str


class DatabaseRecovery:
    """负责不破坏原始文件的数据库恢复准备与恢复点验证。"""

    def classify_existing_database(self, path: Path) -> DatabaseState:
        """分类既有数据库；锁定和 I/O 故障绝不映射为新库。

        Args:
            path: 待检查的主数据库路径。

        Returns:
            不存在、空库、完整、损坏、锁定或 I/O 错误状态。
        """
        path = Path(path)
        initial_state = self._classify_file_presence(path)
        if initial_state is not None:
            return initial_state
        try:
            rows = self._read_integrity_rows(path)
        except sqlite3.Error as error:
            return self._classify_sqlite_error(error)
        except OSError:
            return DatabaseState.IO_ERROR
        if rows == [INTEGRITY_OK]:
            return DatabaseState.VALID
        return DatabaseState.CORRUPT

    def create_backup(self, path: Path, reason: str) -> RecoveryReport:
        """在修改前创建恢复点，并验证校验和与 SQLite 完整性。

        Args:
            path: 启动前已存在的主数据库路径。
            reason: 备份用途，写入返回报告。

        Returns:
            可用于人工恢复及后续校验的报告。

        Raises:
            DatabaseRecoveryError: 复制、校验或完整性验证失败。
        """
        report = self._copy_snapshot(Path(path), BACKUP_PREFIX, reason)
        self.verify_recovery_point(report)
        database = report.recovery_path / report.source_path.name
        try:
            rows = self._read_integrity_rows(database, immutable=False)
            if rows != [INTEGRITY_OK]:
                raise DatabaseRecoveryError("启动备份未通过 integrity_check，请人工恢复")
            checksums = self._snapshot_checksums(report.recovery_path)
        except (sqlite3.Error, OSError) as error:
            raise DatabaseRecoveryError(f"启动备份完整性校验失败：{error}；请人工恢复") from error
        return replace(report, checksums=checksums, integrity=INTEGRITY_OK)

    def quarantine(self, path: Path, reason: str) -> RecoveryReport:
        """复制损坏主库及伴生文件到同目录时间戳隔离区，原文件保持不动。

        Args:
            path: 损坏的主数据库路径。
            reason: 隔离原因。

        Returns:
            包含隔离目录与逐文件校验和的报告。

        Raises:
            DatabaseRecoveryError: 隔离失败；消息包含人工恢复指引。
        """
        report = self._copy_snapshot(Path(path), QUARANTINE_PREFIX, reason)
        self.verify_recovery_point(report)
        return replace(report, integrity=DatabaseState.CORRUPT.value)

    def verify_recovery_point(self, report: RecoveryReport) -> None:
        """验证恢复点文件存在、SHA-256 一致，并按报告复核完整性。

        Args:
            report: 备份或隔离操作生成的报告。

        Raises:
            DatabaseRecoveryError: 文件缺失、内容变化或完整性不符。
        """
        try:
            for filename, expected in report.checksums.items():
                copied = report.recovery_path / filename
                actual = self._checksum(copied)
                if actual != expected:
                    raise DatabaseRecoveryError(f"恢复点校验失败：{filename} 的 SHA-256 不匹配")
        except OSError as error:
            raise DatabaseRecoveryError(f"恢复点校验失败：{error}") from error
        if report.integrity != INTEGRITY_OK:
            return
        database = report.recovery_path / report.source_path.name
        if self.classify_existing_database(database) is not DatabaseState.VALID:
            raise DatabaseRecoveryError("恢复点校验失败：SQLite integrity_check 未通过")

    def restore_recovery_point(self, report: RecoveryReport) -> None:
        """分阶段替换恢复文件，替换阶段失败时回滚到一致旧状态。

        多文件替换并非一次物理原子操作；本方法以当前文件暂存副本处理
        复制、替换和删除异常，进程异常退出不在此异常回滚范围内。

        Args:
            report: 已通过校验的启动前备份报告。

        Raises:
            DatabaseRecoveryError: 备份被篡改、恢复或回滚失败，需要人工恢复。
        """
        self.verify_recovery_point(report)
        staging = self._restore_staging_path(report.source_path)
        staging_created = False
        current_files: Dict[str, Optional[Path]] = {}
        replacement_started = False
        try:
            staging.mkdir(parents=False, exist_ok=False)
            staging_created = True
            staged_recovery = self._stage_recovery_files(report, staging)
            current_files = self._stage_current_files(report.source_path, staging)
            replacement_started = True
            self._apply_staged_recovery(report.source_path, staged_recovery)
        except (OSError, sqlite3.Error) as error:
            self._handle_restore_failure(
                staging, staging_created, current_files, replacement_started, error
            )
        cleanup_error = self._cleanup_created_directory(staging, staging_created)
        if cleanup_error is not None:
            raise DatabaseRecoveryError(
                f"恢复文件已应用，但暂存目录清理失败：{cleanup_error}；请人工检查并恢复"
            ) from cleanup_error

    def _restore_staging_path(self, source: Path) -> Path:
        """生成与目标同文件系统的唯一恢复暂存目录路径。"""
        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%f")
        return source.parent / f"{source.name}.{RESTORE_PREFIX}-{timestamp}"

    def _stage_recovery_files(self, report: RecoveryReport, staging: Path) -> Dict[str, Path]:
        """将全部恢复文件复制到暂存目录并逐文件复核 SHA-256。"""
        staged: Dict[str, Path] = {}
        for filename, expected in report.checksums.items():
            target = staging / f"new-{filename}"
            shutil.copy2(report.recovery_path / filename, target)
            if self._checksum(target) != expected:
                raise OSError(f"暂存恢复文件校验失败：{filename}")
            staged[filename] = target
        return staged

    def _stage_current_files(self, source: Path, staging: Path) -> Dict[str, Optional[Path]]:
        """在替换前备份当前主库和伴生状态，缺失状态也显式记录。"""
        current: Dict[str, Optional[Path]] = {}
        for suffix in SIDECAR_SUFFIXES:
            target = Path(f"{source}{suffix}")
            if not target.exists():
                current[target.name] = None
                continue
            staged = staging / f"current-{target.name}"
            shutil.copy2(target, staged)
            if self._checksum(staged) != self._checksum(target):
                raise OSError(f"当前文件回滚副本校验失败：{target.name}")
            current[target.name] = staged
        return current

    @staticmethod
    def _apply_staged_recovery(source: Path, staged: Dict[str, Path]) -> None:
        """逐文件原子替换新状态，并删除恢复点中不存在的伴生文件。"""
        for suffix in SIDECAR_SUFFIXES:
            target = Path(f"{source}{suffix}")
            staged_file = staged.get(target.name)
            if staged_file is not None:
                os.replace(staged_file, target)
            elif target.exists():
                target.unlink()

    def _handle_restore_failure(
        self,
        staging: Path,
        staging_created: bool,
        current_files: Dict[str, Optional[Path]],
        replacement_started: bool,
        original_error: Exception,
    ) -> None:
        """替换失败后回滚全部旧状态，保留诊断与人工恢复上下文。"""
        rollback_error: Optional[DatabaseRecoveryError] = None
        if replacement_started:
            try:
                self._rollback_current_files(staging.parent, current_files)
            except DatabaseRecoveryError as error:
                rollback_error = error
        rollback_message = self._rollback_message(replacement_started, rollback_error)
        cleanup_error = None
        if rollback_error is None:
            cleanup_error = self._cleanup_created_directory(staging, staging_created)
        cleanup_message = f"；暂存目录清理失败：{cleanup_error}" if cleanup_error else ""
        raise DatabaseRecoveryError(
            f"数据库恢复失败：{original_error}；{rollback_message}{cleanup_message}；请人工恢复"
        ) from original_error

    @staticmethod
    def _rollback_message(replacement_started: bool, error: Optional[Exception]) -> str:
        """生成未替换、回滚成功或回滚失败的明确状态说明。"""
        if not replacement_started:
            return "替换尚未开始，当前文件未改动"
        if error is None:
            return "全部原始文件与伴生状态已回滚"
        return f"回滚未完成：{error}；暂存旧文件已保留"

    def _rollback_current_files(
        self, target_directory: Path, current_files: Dict[str, Optional[Path]]
    ) -> None:
        """以暂存旧文件恢复所有目标，尽量执行完整并汇总回滚错误。"""
        errors = []
        for filename, staged in current_files.items():
            try:
                self._rollback_file(target_directory, filename, staged)
            except OSError as error:
                errors.append(f"{filename}: {error}")
        if errors:
            raise DatabaseRecoveryError("；".join(errors))

    @staticmethod
    def _rollback_file(target_directory: Path, filename: str, staged: Optional[Path]) -> None:
        """恢复单个旧文件，或删除故障前本就不存在的目标。"""
        target = target_directory / filename
        if staged is not None:
            os.replace(staged, target)
        elif target.exists():
            target.unlink()

    @staticmethod
    def _cleanup_created_directory(path: Path, created: bool) -> Optional[OSError]:
        """只清理本次创建的暂存目录，失败返回错误且不触碰其他目录。"""
        if not created:
            return None
        try:
            shutil.rmtree(path)
        except OSError as error:
            return error
        return None

    def _classify_file_presence(self, path: Path) -> Optional[DatabaseState]:
        """分类路径不存在、空文件和可继续读取的文件。"""
        try:
            if not path.exists():
                return DatabaseState.MISSING
            if path.stat().st_size == 0:
                return DatabaseState.EMPTY
        except OSError:
            return DatabaseState.IO_ERROR
        return None

    def _read_integrity_rows(self, path: Path, immutable: bool = True) -> list[str]:
        """只读执行 integrity_check；原库默认 immutable，避免 SQLite 改写 SHM。"""
        immutable_option = "&immutable=1" if immutable else ""
        uri = f"{path.resolve().as_uri()}?mode=ro{immutable_option}"
        with closing(sqlite3.connect(uri, uri=True, timeout=CLASSIFY_TIMEOUT_SECONDS)) as connection:
            rows = connection.execute(INTEGRITY_CHECK_SQL).fetchall()
        return [str(row[0]) for row in rows]

    @staticmethod
    def _classify_sqlite_error(error: sqlite3.Error) -> DatabaseState:
        """按 SQLite 错误文本区分锁、访问/I/O 故障与物理损坏。"""
        message = str(error).lower()
        if "locked" in message or "busy" in message:
            return DatabaseState.LOCKED
        if isinstance(error, sqlite3.OperationalError):
            return DatabaseState.IO_ERROR
        if "permission" in message or "i/o" in message or "readonly" in message:
            return DatabaseState.IO_ERROR
        return DatabaseState.CORRUPT

    def _copy_snapshot(self, path: Path, prefix: str, reason: str) -> RecoveryReport:
        """复制主库和现存伴生文件，仅清理本次成功创建的目录。"""
        timestamp = dt.datetime.now(dt.timezone.utc)
        suffix = timestamp.strftime("%Y%m%dT%H%M%S.%f")
        destination = path.parent / f"{path.name}.{prefix}-{suffix}"
        destination_created = False
        try:
            destination.mkdir(parents=False, exist_ok=False)
            destination_created = True
            self._copy_database_files(path, destination)
            checksums = self._snapshot_checksums(destination)
        except (OSError, sqlite3.Error) as error:
            if destination_created:
                self._cleanup_incomplete_snapshot(destination, error)
            raise DatabaseRecoveryError(
                f"数据库{prefix}副本创建失败：{error}；原始文件未改动，请人工恢复"
            ) from error
        return RecoveryReport(path, destination, reason, timestamp.isoformat(), checksums, "unchecked")

    @staticmethod
    def _copy_database_files(path: Path, destination: Path) -> None:
        """以原文件名复制主库、WAL 和 SHM，保留 SQLite 文件对应关系。"""
        if not path.is_file():
            raise OSError(f"主数据库不存在或不是普通文件：{path}")
        for suffix in SIDECAR_SUFFIXES:
            source = Path(f"{path}{suffix}")
            if source.exists():
                shutil.copy2(source, destination / source.name)

    def _snapshot_checksums(self, destination: Path) -> Dict[str, str]:
        """计算快照内全部复制文件的 SHA-256。"""
        return {path.name: self._checksum(path) for path in destination.iterdir() if path.is_file()}

    @staticmethod
    def _checksum(path: Path) -> str:
        """流式计算单个文件 SHA-256，避免大库一次性读入内存。"""
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(CHECKSUM_CHUNK_BYTES), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _cleanup_incomplete_snapshot(destination: Path, original_error: Exception) -> None:
        """仅删除本次未完成的快照目录，清理失败时保留明确错误上下文。"""
        if not destination.exists():
            return
        try:
            shutil.rmtree(destination)
        except OSError as cleanup_error:
            raise DatabaseRecoveryError(
                f"不完整隔离目录清理失败：{cleanup_error}；原始错误：{original_error}；请人工恢复"
            ) from cleanup_error
