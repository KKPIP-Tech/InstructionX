"""故障注入与恢复验证入口，快速门禁和完整 100 次恢复共用。"""

import argparse
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Iterable

import httpx

from core.data.recovery import DatabaseRecovery
from core.data.sqlite_backend import SQLiteBackend
from core.observability.sanitize import sanitize_text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = Path("temp/fault-inject-foundation.json")
COMMAND_TIMEOUT_SECONDS = 300
RECOVERY_RTO_SECONDS = 60.0
NETWORK_TIMEOUT_SECONDS = 0.03
NETWORK_STATUS_TIMEOUT_SECONDS = 1.0


def _command(name: str, arguments: Iterable[str]) -> Dict:
    """执行本地命令并保留有限脱敏输出。"""
    completed = subprocess.run(
        list(arguments), cwd=PROJECT_ROOT,
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        capture_output=True, encoding="utf-8", errors="replace", timeout=COMMAND_TIMEOUT_SECONDS,
    )
    return {
        "name": name,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "returncode": completed.returncode,
        "output": sanitize_text(((completed.stdout or "") + (completed.stderr or ""))[-4000:]),
    }


def run_recovery_cycles(count: int) -> Dict:
    """执行真实恢复点替换和启动，100 次总 RTO 不得超过 60 秒。"""
    started = time.perf_counter()
    recovered = 0
    error = ""
    with tempfile.TemporaryDirectory(prefix="fault-recovery-", dir=PROJECT_ROOT / "temp") as root:
        try:
            for index in range(count):
                _recover_one(Path(root) / str(index))
                recovered += 1
        except Exception as caught:
            error = sanitize_text(caught)
    elapsed = time.perf_counter() - started
    passed = recovered == count and elapsed <= RECOVERY_RTO_SECONDS and not error
    return {
        "name": "startup_recovery_cycles",
        "status": "PASS" if passed else "FAIL",
        "requested": count,
        "recovered": recovered,
        "elapsed_seconds": round(elapsed, 6),
        "rto_limit_seconds": RECOVERY_RTO_SECONDS,
        "error": error,
    }


def _recover_one(directory: Path) -> None:
    """制造损坏后恢复已验证备份，并重新完成真实 SQLite 启动。"""
    directory.mkdir(parents=True)
    database = directory / "data.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE foundation_commit (id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO foundation_commit VALUES (1)")
        connection.commit()
    finally:
        connection.close()
    recovery = DatabaseRecovery()
    report = recovery.create_backup(database, "100 次异常启动恢复")
    database.write_bytes(b"controlled-corruption")
    recovery.restore_recovery_point(report)
    backend = SQLiteBackend(str(directory), "data.json")
    try:
        backend.ensure_database()
        rows = backend._connect().execute("SELECT COUNT(*) FROM foundation_commit").fetchone()[0]
        if rows != 1:
            raise RuntimeError(f"恢复后提交行数异常: {rows}")
    finally:
        backend.close()


class _NetworkHandler(BaseHTTPRequestHandler):
    """回环 HTTP 故障端点，不访问外部网络。"""

    def do_GET(self):
        if self.path == "/429":
            self.send_response(429)
        elif self.path == "/500":
            self.send_response(500)
        elif self.path == "/timeout":
            time.sleep(NETWORK_TIMEOUT_SECONDS * 3)
            self.send_response(200)
        elif self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Length", "100")
            self.end_headers()
            self.wfile.write(b"partial")
            self.wfile.flush()
            self.close_connection = True
            return
        else:
            self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        return


def run_network_checks() -> list[Dict]:
    """验证 DNS、429、5xx、读超时和流中断均显式失败。"""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _NetworkHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    checks = []
    try:
        checks.extend((
            _http_status_check(base, "/429", 429),
            _http_status_check(base, "/500", 500),
            _timeout_check(base),
            _stream_check(base),
            _dns_check(),
        ))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=NETWORK_STATUS_TIMEOUT_SECONDS)
    return checks


def _http_status_check(base: str, path: str, expected: int) -> Dict:
    response = httpx.get(base + path, timeout=NETWORK_STATUS_TIMEOUT_SECONDS)
    return {
        "name": f"http_{expected}", "status": "PASS" if response.status_code == expected else "FAIL",
        "expected": expected, "actual": response.status_code, "scope": "REAL_LOOPBACK_HTTP",
    }


def _timeout_check(base: str) -> Dict:
    try:
        httpx.get(base + "/timeout", timeout=NETWORK_TIMEOUT_SECONDS)
    except httpx.TimeoutException as error:
        return {"name": "read_timeout", "status": "PASS", "error": type(error).__name__}
    return {"name": "read_timeout", "status": "FAIL", "error": "未发生读超时"}


def _stream_check(base: str) -> Dict:
    try:
        with httpx.stream("GET", base + "/stream", timeout=NETWORK_STATUS_TIMEOUT_SECONDS) as response:
            response.read()
    except httpx.HTTPError as error:
        return {"name": "stream_interrupted", "status": "PASS", "error": type(error).__name__}
    return {"name": "stream_interrupted", "status": "FAIL", "error": "未发生流中断"}


def _dns_check() -> Dict:
    try:
        socket.getaddrinfo("does-not-exist.invalid", 80)
    except socket.gaierror as error:
        return {"name": "dns_failure", "status": "PASS", "error": type(error).__name__}
    return {
        "name": "dns_failure", "status": "NOT_RUN",
        "reason": "当前 DNS 环境对保留 .invalid 域名返回了地址，无法证明失败语义",
    }


def _pytest_targets() -> list[str]:
    return [
        "test/core/test_foundation_fault_matrix.py",
        "test/core/data/test_database_recovery.py",
        "test/core/task/test_cancellation.py",
        "test/core/task/test_background_task_shutdown.py",
        "test/core/test_plugin_contracts.py",
        "test/ui_tests/test_startup_offline.py",
    ]


def run_command_checks(quick: bool) -> list[Dict]:
    """运行快速故障矩阵、真实 GUI、调度与契约；完整模式增加全部生命周期。"""
    checks = [_command(
        "contract_quick", [sys.executable, "scripts/validate_plugin_contracts.py", "--quick"]
    )]
    targets = _pytest_targets()
    if all((PROJECT_ROOT / target).exists() for target in targets):
        checks.append(_command(
            "fault_gui_pytest",
            [sys.executable, "-m", "pytest", *targets, "-q", "--tb=short", "-p", "no:cacheprovider"],
        ))
    else:
        checks.append({"name": "fault_gui_pytest", "status": "NOT_RUN", "missing": targets})
    if quick:
        return checks
    checks.extend((
        _command("legacy_lifecycle", [sys.executable, "scripts/validate_plugin_contracts.py"]),
        _command("mcp_reconnect_100", [sys.executable, "scripts/_mcp_smoke.py"]),
    ))
    return checks


def _output_path(value: Path) -> Path:
    resolved = (PROJECT_ROOT / value).resolve() if not value.is_absolute() else value.resolve()
    if not resolved.is_relative_to((PROJECT_ROOT / "temp").resolve()):
        raise ValueError("报告路径必须位于项目 temp 内")
    return resolved


def main() -> int:
    """执行故障验证；FAIL 返回 1，NOT_RUN 返回 2。"""
    parser = argparse.ArgumentParser(description="执行故障注入、网络错误与启动恢复验证")
    parser.add_argument("--quick", action="store_true", help="快速子集，仅 5 次恢复")
    parser.add_argument("--recovery-count", type=int, default=None)
    parser.add_argument("--allow-not-run", action="store_true", help="环境相关 NOT_RUN 仅退出 0，报告不改状态")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    count = args.recovery_count if args.recovery_count is not None else (5 if args.quick else 100)
    if count <= 0:
        parser.error("recovery-count 必须大于 0")
    checks = run_command_checks(args.quick)
    checks.extend(run_network_checks())
    checks.append(run_recovery_cycles(count))
    status = "FAIL" if any(item["status"] == "FAIL" for item in checks) else (
        "NOT_RUN" if any(item["status"] == "NOT_RUN" for item in checks) else "PASS"
    )
    output = _output_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"status": status, "checks": checks}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"故障注入验证：{status}；报告：{output}")
    for item in checks:
        print(f"[{item['status']}] {item['name']}")
    if status == "NOT_RUN" and args.allow_not_run:
        return 0
    return 1 if status == "FAIL" else 2 if status == "NOT_RUN" else 0


if __name__ == "__main__":
    sys.exit(main())
