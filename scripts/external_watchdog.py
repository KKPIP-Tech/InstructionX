"""独立 watchdog 手动入口；只执行 JSON 配置中明确声明的动作。"""

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.external_watchdog import Watchdog, WatchdogAction, WatchdogConfig, WatchdogStatus


MIN_CHECK_INTERVAL = 0.1
WATCHDOG_OK_STATUSES = frozenset({
    WatchdogStatus.HEALTHY, WatchdogStatus.STALE,
    WatchdogStatus.PROCESS_EXITED, WatchdogStatus.ACTION_COMPLETED,
})


def _load_config(path: Path) -> WatchdogConfig:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        command = payload.get("restart_command")
        return WatchdogConfig(
            heartbeat_path=Path(payload["heartbeat_path"]),
            target_pid=payload["target_pid"],
            stale_after=payload.get("stale_after", 10.0),
            action=WatchdogAction(payload.get("action", "none")),
            restart_command=tuple(command) if command else None,
            termination_timeout=payload.get("termination_timeout", 3.0),
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"watchdog 配置无效: {exc}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="InstructionX 独立外部 watchdog")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--once", action="store_true", help="只检查一次后退出")
    parser.add_argument("--interval", type=float, default=1.0, help="周期检查间隔秒数")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """按用户命令执行一次或周期检查，结果以 JSON 行输出。"""
    args = _parser().parse_args(argv)
    if args.interval < MIN_CHECK_INTERVAL:
        raise ValueError("检查间隔不能小于 0.1 秒")
    watchdog = Watchdog(_load_config(args.config))
    while True:
        report = watchdog.check_once()
        print(json.dumps(asdict(report), ensure_ascii=False), flush=True)
        if args.once:
            return 0 if report.status in WATCHDOG_OK_STATUSES else 1
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
