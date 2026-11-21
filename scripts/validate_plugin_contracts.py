"""插件公开契约与既有生命周期/旧格式兼容验证。"""

import argparse
import inspect
import json
import os
import subprocess
import sys
from dataclasses import MISSING, fields
from pathlib import Path
from typing import Any, Dict, Iterable

from core.data import DataProvider
from core.interfaces import IPlugin
from core.interfaces.i_data_provider import DataNamespace
from core.interfaces.plugin_services import PluginServices
from core.llm.llm_provider import LLMProvider
from core.mcp.manager import MCPManager
from core.observability.sanitize import sanitize_text
from core.task import BackgroundTaskManager

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED = object()
DEFAULT_OUTPUT = Path("temp/plugin-contracts.json")
COMMAND_TIMEOUT_SECONDS = 300


def _contracts():
    """返回旧参数及默认值，新增可选参数允许、新增必填参数拒绝。"""
    return (
        ("IPlugin.on_plugin_loaded", IPlugin.on_plugin_loaded, {"plugin_id": None}),
        ("IPlugin.on_plugin_unloaded", IPlugin.on_plugin_unloaded, {}),
        ("DataProvider.set_plugin_data", DataProvider.set_plugin_data, {
            "instance_id": REQUIRED, "key": REQUIRED, "value": REQUIRED,
            "namespace": DataNamespace.PRIVATE, "notify": True,
        }),
        ("DataProvider.get_plugin_data", DataProvider.get_plugin_data, {
            "instance_id": REQUIRED, "key": REQUIRED,
            "namespace": DataNamespace.PRIVATE, "default": None,
        }),
        ("DataProvider.subscribe", DataProvider.subscribe, {
            "subscriber_id": REQUIRED, "target_plugin_id": REQUIRED,
            "target_key": REQUIRED, "callback": REQUIRED,
        }),
        ("BackgroundTaskManager.register_async_task", BackgroundTaskManager.register_async_task, {
            "plugin_id": REQUIRED, "name": REQUIRED, "func": REQUIRED,
            "callback": None, "args": (), "kwargs": None,
        }),
        ("BackgroundTaskManager.request_task_cancellation", BackgroundTaskManager.request_task_cancellation, {
            "task_id": REQUIRED, "timeout": None,
        }),
        ("MCPManager.connect", MCPManager.connect, {
            "config": REQUIRED, "tool_registry": None,
        }),
        ("LLMProvider.refresh_all_models", LLMProvider.refresh_all_models, {
            "force": False,
        }),
    )


def evaluate_signature(name: str, method, expected: Dict[str, Any]) -> Dict[str, Any]:
    """检查旧参数是否存在且默认值未破坏，并分类新增可选/必填参数。"""
    parameters = inspect.signature(method).parameters
    missing = [name for name in expected if name not in parameters]
    changed_defaults = []
    for parameter_name, default in expected.items():
        parameter = parameters.get(parameter_name)
        if parameter is None or default is REQUIRED:
            continue
        if parameter.default != default:
            changed_defaults.append(parameter_name)
    new_required = [
        parameter.name for parameter in parameters.values()
        if parameter.name not in expected and parameter.name not in {"self", "cls"}
        and parameter.default is inspect.Parameter.empty
        and parameter.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    ]
    new_optional = [
        parameter.name for parameter in parameters.values()
        if parameter.name not in expected and parameter.name not in {"self", "cls"}
        and parameter not in new_required
    ]
    return {
        "name": name,
        "status": "PASS" if not missing and not changed_defaults and not new_required else "FAIL",
        "missing": missing,
        "changed_defaults": changed_defaults,
        "new_required": new_required,
        "new_optional": new_optional,
    }


def evaluate_plugin_services() -> Dict[str, Any]:
    """检查依赖注入容器新增字段均可选，旧必填字段不被改成可选。"""
    expected_required = {"llm_facade", "data_provider", "task_manager", "logger"}
    current = {field.name: field for field in fields(PluginServices)}
    missing = sorted(expected_required - current.keys())
    weakened = sorted(
        name for name in expected_required & current.keys()
        if current[name].default is not MISSING
    )
    new_required = [
        field.name for field in current.values()
        if field.name not in expected_required
        and field.default is MISSING and field.default_factory is MISSING
    ]
    return {
        "name": "PluginServices.fields",
        "status": "PASS" if not missing and not weakened and not new_required else "FAIL",
        "missing": missing,
        "changed_defaults": weakened,
        "new_required": new_required,
        "new_optional": [],
    }


def run_contract_checks() -> list[Dict[str, Any]]:
    """执行源码公开契约检查，不启动插件或访问外部服务。"""
    checks = [evaluate_signature(name, method, expected) for name, method, expected in _contracts()]
    checks.append(evaluate_plugin_services())
    return checks


def _run_command(name: str, arguments: Iterable[str]) -> Dict[str, Any]:
    """执行本地验证命令并保留有限脱敏输出。"""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    completed = subprocess.run(
        list(arguments), cwd=PROJECT_ROOT, env=env,
        capture_output=True, encoding="utf-8", errors="replace", timeout=COMMAND_TIMEOUT_SECONDS,
    )
    output = sanitize_text(((completed.stdout or "") + (completed.stderr or ""))[-4000:])
    return {
        "name": name,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "returncode": completed.returncode,
        "output": output,
    }


def run_lifecycle_checks() -> list[Dict[str, Any]]:
    """运行真实插件管理、旧存储与 MCP 配置测试；缺失测试明确 NOT_RUN。"""
    checks = [_run_command(
        "plugin_management_smoke",
        [sys.executable, str(PROJECT_ROOT / "scripts" / "smoke_plugin_management.py")],
    )]
    test_targets = [
        "test/core/plugin", "test/core/data/test_data_provider.py",
        "test/core/task/test_task_storage.py", "test/core/llm/test_conversation_store_recovery.py",
        "test/core/llm/test_usage_store_recovery.py", "test/core/mcp/test_config.py",
    ]
    missing = [target for target in test_targets if not (PROJECT_ROOT / target).exists()]
    if missing:
        checks.append({"name": "legacy_pytest", "status": "NOT_RUN", "missing": missing})
        return checks
    checks.append(_run_command(
        "legacy_pytest",
        [sys.executable, "-m", "pytest", *test_targets, "-q", "--tb=short", "-p", "no:cacheprovider"],
    ))
    return checks


def _output_path(value: Path) -> Path:
    resolved = (PROJECT_ROOT / value).resolve() if not value.is_absolute() else value.resolve()
    if not resolved.is_relative_to((PROJECT_ROOT / "temp").resolve()):
        raise ValueError("报告路径必须位于项目 temp 内")
    return resolved


def main() -> int:
    """执行契约验证并输出 JSON；FAIL 返回 1，NOT_RUN 返回 2。"""
    parser = argparse.ArgumentParser(description="验证插件公开契约和既有生命周期兼容性")
    parser.add_argument("--quick", action="store_true", help="仅执行源码契约检查")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    checks = run_contract_checks()
    if not args.quick:
        checks.extend(run_lifecycle_checks())
    status = "FAIL" if any(item["status"] == "FAIL" for item in checks) else (
        "NOT_RUN" if any(item["status"] == "NOT_RUN" for item in checks) else "PASS"
    )
    report = {"status": status, "checks": checks}
    output = _output_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"插件契约验证：{status}；报告：{output}")
    for item in checks:
        print(f"[{item['status']}] {item['name']}")
    return 1 if status == "FAIL" else 2 if status == "NOT_RUN" else 0


if __name__ == "__main__":
    sys.exit(main())
