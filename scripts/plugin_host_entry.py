"""进程外单插件宿主入口；由 ``PluginHost`` 启动，不建议直接交互运行。"""

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.plugin_host.protocol import ErrorCode, write_message
from core.plugin_host.runtime import HostedPluginRuntime, ParentProcessMonitor


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="InstructionX 进程外插件宿主")
    parser.add_argument("--plugin-path", required=True, type=Path)
    parser.add_argument("--parent-pid", required=True, type=int)
    parser.add_argument("--heartbeat-interval", required=True, type=float)
    parser.add_argument("--max-message-size", required=True, type=int)
    parser.add_argument("--data-dir")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """启动宿主事件循环，并保证标准输出只用于协议帧。"""
    args = _parser().parse_args(argv)
    protocol_output = sys.stdout.buffer
    sys.stdout = sys.stderr
    ParentProcessMonitor(args.parent_pid).start()
    runtime = HostedPluginRuntime(
        args.plugin_path.resolve(), sys.stdin.buffer, protocol_output,
        args.heartbeat_interval, args.max_message_size, args.data_dir,
    )
    try:
        runtime.start()
    except Exception as exc:
        write_message(protocol_output, {
            "version": 1, "type": "error", "id": "startup",
            "code": ErrorCode.STARTUP_FAILED.value, "message": str(exc),
        }, args.max_message_size)
        return 1
    return runtime.serve()


if __name__ == "__main__":
    raise SystemExit(main())
