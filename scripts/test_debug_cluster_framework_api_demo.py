#!/usr/bin/env python3
r"""
使用 InstructionX 自带的 GitHubPluginInstaller 拉取测试插件集
https://github.com/KKPIP-Tech/instructionx-debug-plugin-cluster，
并验证 Framework API Demo 插件的所有服务方法可正常调用。

运行:
    .venv\Scripts\python.exe scripts\test_debug_cluster_framework_api_demo.py
"""
import os
import sys
import time
import traceback
from pathlib import Path

# 清除可能指向未运行本地代理的环境变量，避免 requests 连接失败
for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(key, None)

project_root = Path(__file__).parent.parent
os.chdir(project_root)
sys.path.insert(0, str(project_root))

# 强制标准输出使用 UTF-8，避免 Windows 终端 GBK 编码导致 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from core.plugin.github_plugin_installer import GitHubPluginInstaller
from core.plugin.manager import PluginManager
from utils.logging_tools import LoggerManager, get_name

logger = LoggerManager()
URL = "https://github.com/KKPIP-Tech/instructionx-debug-plugin-cluster"
TARGET_TYPE_ID = "framework-api-demo"
SAMPLE_TARGET_TYPE_ID = "string-tools"


def log(msg: str):
    print(msg)
    logger.info(get_name(), msg)


def install_cluster(max_retries: int = 3) -> tuple:
    """尝试使用 InstructionX 安装器拉取插件集，返回 (results, any_success)。"""
    installer = GitHubPluginInstaller()
    last_results = []
    for attempt in range(1, max_retries + 1):
        log(f"  第 {attempt}/{max_retries} 次尝试从 GitHub 拉取...")
        results = installer.install_from_url(URL)
        last_results = results
        any_success = any(r.success for r in results)
        if any_success:
            return results, True
        time.sleep(2)
    return last_results, False


def main() -> int:
    log("=" * 70)
    log("1. 使用 InstructionX GitHub 插件安装器拉取测试插件集")
    log("=" * 70)
    install_results, install_ok = install_cluster()
    ok_count = sum(1 for r in install_results if r.success)
    for r in install_results:
        status = "OK" if r.success else "FAIL"
        log(f"  [{status}] {r.plugin_id or 'unknown'} ({r.plugin_name or 'unknown'}): {r.message}")
    log(f"安装结果: {ok_count}/{len(install_results)} 成功")
    if not install_ok:
        # 网络抖动可能导致本次失败；如果本地已经存在测试插件集，仍可继续验证
        plugin_dir = project_root / "plugin" / TARGET_TYPE_ID
        if plugin_dir.exists():
            log("  注意：安装器本次未成功，但本地已存在该插件集，继续验证...")
        else:
            log("  错误：本地未找到插件且拉取失败，无法继续")
            return 1

    log("=" * 70)
    log("2. 加载所有插件")
    log("=" * 70)
    pm = PluginManager()
    pm.load_plugins()
    pm.apply_custom_order()
    plugins = pm.get_all_plugins()
    log(f"已加载插件数: {len(plugins)}")
    for p in plugins:
        log(f"  - {p.plugin_id}: {p.plugin_name}")

    log("=" * 70)
    log(f"3. 定位 Framework API Demo 插件 (type_id={TARGET_TYPE_ID})")
    log("=" * 70)
    plugin = pm.get_plugin_by_type_id(TARGET_TYPE_ID)
    if plugin is None:
        log(f"✗ 未找到 type_id={TARGET_TYPE_ID} 的插件")
        return 1
    log(f"✓ 找到插件: plugin_id={plugin.plugin_id}, name={plugin.plugin_name}")
    try:
        plugin.on_plugin_loaded()
        log("✓ on_plugin_loaded 调用成功")
    except Exception as e:
        log(f"✗ on_plugin_loaded 调用失败: {e}")
        traceback.print_exc()
        return 1

    outcomes = []

    def check(label: str, fn, *args, expect_success: bool = True, **kwargs):
        """调用服务方法并记录结果。expect_success=False 用于 LLM 等可能因未配置而失败的接口。"""
        try:
            res = fn(*args, **kwargs)
            has_success = isinstance(res, dict) and "success" in res
            if expect_success:
                ok = res.get("success") if has_success else True
            else:
                ok = True  # 只要没抛异常就算通过
            outcomes.append((label, ok, res))
            icon = "OK" if ok else "WARN"
            log(f"  [{icon}] {label}: {res}")
            return res
        except Exception as e:
            outcomes.append((label, False, str(e)))
            log(f"  [FAIL] {label}: {e}")
            traceback.print_exc()
            return None

    log("=" * 70)
    log("4. DataProvider API Demo")
    log("=" * 70)
    ds = plugin.data_service
    check("register_demo_plugin", ds.register_demo_plugin)
    check("write_private_data", ds.write_private_data, "test_key", "test_value")
    check("read_private_data", ds.read_private_data, "test_key")
    check("write_public_data", ds.write_public_data, "shared_key", "shared_value")
    check("read_public_data", ds.read_public_data, "shared_key")
    check("get_all_data", ds.get_all_data)
    check("save_demo_asset", ds.save_demo_asset)
    check("load_demo_asset", ds.load_demo_asset)
    check("unregister_demo_plugin", ds.unregister_demo_plugin)

    log("=" * 70)
    log("5. BackgroundTaskManager API Demo")
    log("=" * 70)
    ts = plugin.task_service
    check("create_sync_task", ts.create_sync_task, "sync_demo")
    time.sleep(1.5)
    check("create_async_task", ts.create_async_task, "async_demo")
    time.sleep(2.5)
    check("create_scheduled_task", ts.create_scheduled_task, "scheduled_demo", 3600)
    check("query_tasks", ts.query_tasks)
    check("clear_completed", ts.clear_completed)
    try:
        ts.task_manager.shutdown()
        log("OK task_manager.shutdown")
    except Exception as e:
        log(f"FAIL task_manager.shutdown: {e}")
        outcomes.append(("task_manager.shutdown", False, str(e)))

    log("=" * 70)
    log("6. LLMProvider API Demo（chat/embed 依赖真实密钥，允许返回错误字典）")
    log("=" * 70)
    ls = plugin.llm_service
    check("get_providers", ls.get_providers)
    check("get_models", ls.get_models)
    # 未配置 API key 时预计返回 {"success": False, "error": ...}，不应抛异常
    check("send_chat", ls.send_chat, "你好", expect_success=False)
    check("send_embedding", ls.send_embedding, "Hello world", expect_success=False)

    log("=" * 70)
    log("7. PluginManager API Demo")
    log("=" * 70)
    apis = plugin.api_service
    check("get_all_plugins", apis.get_all_plugins)
    check("get_plugin_by_id", apis.get_plugin_by_id, plugin.plugin_id)
    check("get_all_apis", apis.get_all_apis)
    check("get_all_function_tools", apis.get_all_function_tools)

    sample_uuid = pm.get_plugin_id_by_type_id(SAMPLE_TARGET_TYPE_ID)
    if sample_uuid:
        check("get_api_description", apis.get_api_description, sample_uuid, "to_uppercase")
        check("call_plugin_method", apis.call_plugin_method, sample_uuid, "to_uppercase", text="hello")
    else:
        log(f"  [SKIP] get_api_description / call_plugin_method: 未找到 {SAMPLE_TARGET_TYPE_ID}")

    log("=" * 70)
    log("8. Framework Info")
    log("=" * 70)
    try:
        info = plugin.info_service.get_framework_info()
        log(f"OK get_framework_info: {info}")
        outcomes.append(("get_framework_info", bool(info), info))
    except Exception as e:
        log(f"FAIL get_framework_info: {e}")
        outcomes.append(("get_framework_info", False, str(e)))
        traceback.print_exc()

    log("=" * 70)
    log("汇总")
    log("=" * 70)
    passed = sum(1 for _, ok, _ in outcomes if ok)
    total = len(outcomes)
    for label, ok, _ in outcomes:
        log(f"  {'OK' if ok else 'FAIL'} {label}")
    log(f"通过 {passed}/{total}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
