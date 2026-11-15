"""插件公开签名、依赖注入与向后兼容契约测试。"""

from core.interfaces.i_data_provider import IDataProvider
from scripts.fault_inject_foundation import run_recovery_cycles
from scripts.validate_plugin_contracts import (
    evaluate_plugin_services,
    evaluate_signature,
    run_contract_checks,
)


def test_current_public_contracts_have_no_breaking_changes():
    """既有公开参数不得丢失或新增必填项。"""
    checks = run_contract_checks()
    assert checks
    assert all(item["status"] == "PASS" for item in checks)
    assert all(not item["new_required"] for item in checks)


def test_optional_extensions_are_allowed_not_required():
    """refresh_all_models 的 timeout 是兼容可选扩展，不属于破坏。"""
    check = next(item for item in run_contract_checks() if item["name"] == "LLMProvider.refresh_all_models")
    assert "timeout" in check["new_optional"]
    assert check["status"] == "PASS"


def test_contract_validator_rejects_new_required_parameter():
    """负例：新增必填参数必须被识别为破坏性变更。"""
    def breaking_change(instance_id, key, value, namespace, notify, required_new):
        return None

    expected = {
        "instance_id": object(), "key": object(), "value": object(),
        "namespace": None, "notify": True,
    }
    result = evaluate_signature("breaking", breaking_change, expected)
    assert result["status"] == "FAIL"
    assert result["new_required"] == ["required_new"]


def test_plugin_services_new_fields_are_optional():
    """依赖注入新增 observability 等字段不得成为必填构造参数。"""
    result = evaluate_plugin_services()
    assert result["status"] == "PASS"
    assert result["new_required"] == []


def test_batch_extensions_do_not_expand_abstract_interface():
    """批量与分页是具体实现扩展，不强迫第三方 IDataProvider 实现。"""
    assert not hasattr(IDataProvider, "set_plugin_data_batch")
    assert not hasattr(IDataProvider, "get_plugin_data_page")
    assert not hasattr(IDataProvider, "count_plugin_data")



def test_recovery_cycles_restore_committed_data_and_startup():
    """真实恢复点替换后提交行不丢失，重新启动成功且满足 RTO。"""
    result = run_recovery_cycles(2)
    assert result["status"] == "PASS"
    assert result["recovered"] == 2
    assert result["elapsed_seconds"] <= 60
