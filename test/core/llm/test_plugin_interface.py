"""ILLMService 接口契约测试（core/interfaces/i_llm_service.py + plugin_service.py）

重构核心保障：接口即契约（显式继承、签名一致）、消除底层泄漏、
ProviderInfo 字段来自真实配置、默认解析、配置变更定价热更新。
"""

import base64
import inspect

import pytest

from core.interfaces.i_llm_service import ILLMService
from core.interfaces.plugin_services import PluginServices
from core.llm.config import get_llm_config
from core.llm.llm_provider import get_llm_provider
from core.llm.plugin_service import LLMPluginService
from core.llm.provider_interface import ModelInfo
from core.llm.types import DEFAULT_PROVIDER


def _make_service() -> LLMPluginService:
    """构造独立 LLMPluginService 实例（不走模块级单例）"""
    return LLMPluginService()


class TestInterfaceContract:
    """接口即契约"""

    def test_service_is_illm_service_instance(self):
        """LLMPluginService 显式继承 ILLMService（isinstance 成立）"""
        assert isinstance(_make_service(), ILLMService)

    def test_abstract_methods_signatures_match(self):
        """全部抽象方法已实现且参数签名与接口一致（名称/默认值/种类比对）"""
        for name in dir(ILLMService):
            member = inspect.getattr_static(ILLMService, name)
            if not getattr(member, "__isabstractmethod__", False):
                continue
            impl_fn = inspect.getattr_static(LLMPluginService, name, None)
            assert impl_fn is not None, f"抽象方法未实现: {name}"
            # property 直接比对类型，普通方法比对参数（不含注解，
            # 因接口层注解为 TYPE_CHECKING 字符串、实现层为求值对象）
            if isinstance(member, property):
                assert isinstance(impl_fn, property)
                continue
            interface_params = [
                (p.name, p.default, p.kind)
                for p in inspect.signature(member).parameters.values()
            ]
            impl_params = [
                (p.name, p.default, p.kind)
                for p in inspect.signature(impl_fn).parameters.values()
            ]
            assert impl_params == interface_params, (
                f"签名不一致: {name}\n接口: {interface_params}\n实现: {impl_params}")

    def test_plugin_services_annotation_is_interface(self):
        """PluginServices.llm_facade 类型标注为 ILLMService 接口"""
        field = PluginServices.__dataclass_fields__["llm_facade"]
        assert field.type == "ILLMService"

    def test_leaky_methods_removed(self):
        """底层泄漏方法已从插件面移除（get_raw_provider 等）"""
        service = _make_service()
        for name in ("get_raw_provider", "get_provider", "get_all_providers",
                     "get_cached_models", "load_image_as_base64",
                     "get_available_providers"):
            assert not hasattr(service, name), f"泄漏方法仍存在: {name}"
        assert not hasattr(ILLMService, "get_raw_provider")


class TestProviderInfoFromRealConfig:
    """ProviderInfo 字段来自真实配置"""

    def _setup_instances(self, mock_config_factory):
        config = get_llm_config()
        config.add_provider("mock-1", mock_config_factory(
            name="实例一", enabled_chat=True, order=0))
        # 第二实例关联 glm 预设（adapter 仍为 mock，避免真实网络）
        second = mock_config_factory(
            name="实例二", enabled_chat=False, enabled_embedding=True, order=1)
        second.preset_id = "glm"
        config.add_provider("mock-2", second)
        return config

    def test_list_providers_fields(self, mock_config_factory):
        """list_providers：启用状态/适配器/预设关联/名称与配置一致，按 order 排序"""
        self._setup_instances(mock_config_factory)
        infos = _make_service().list_providers()
        assert [i.instance_id for i in infos] == ["mock-1", "mock-2"]
        first, second = infos
        assert first.name == "实例一"
        assert first.enabled_chat is True
        assert first.enabled_embedding is False
        assert first.adapter == "mock-adapter"
        assert first.preset_id is None
        # base_url 取实例覆写（不含密钥）
        assert first.base_url == "http://mock.local/v1"
        assert second.preset_id == "glm"
        assert second.enabled_chat is False
        assert second.enabled_embedding is True

    def test_provider_info_has_no_api_key(self, mock_config_factory):
        """ProviderInfo 不携带 api_key 等敏感字段"""
        self._setup_instances(mock_config_factory)
        info = _make_service().list_providers()[0]
        assert not hasattr(info, "api_key")
        dump = repr(info)
        assert "mock-key" not in dump


class TestQueryApis:
    """实例与模型查询"""

    def test_get_models_by_instance_and_default(self, mock_config_factory):
        """get_models 按实例 id 工作；DEFAULT_PROVIDER 解析为默认实例"""
        get_llm_config().add_provider("mock-1", mock_config_factory())
        ok, _, _ = get_llm_provider().check_provider("mock-1")
        assert ok
        service = _make_service()
        models = service.get_models("mock-1")
        assert all(isinstance(m, ModelInfo) for m in models)
        default_models = service.get_models(DEFAULT_PROVIDER)
        assert [m.id for m in default_models] == [m.id for m in models]

    def test_resolve_provider_id(self, mock_config_factory):
        """resolve_provider_id：非默认引用原样返回；默认引用解析为实例 id"""
        get_llm_config().add_provider("mock-1", mock_config_factory())
        service = _make_service()
        assert service.resolve_provider_id("mock-1") == "mock-1"
        assert service.resolve_provider_id(DEFAULT_PROVIDER) == "mock-1"

    def test_get_default_provider_id_none_when_empty(self):
        """无可用实例时 get_default_provider_id 返回 None（不抛异常）"""
        assert _make_service().get_default_provider_id() is None


class TestPricingHotReload:
    """配置变更订阅驱动的定价热更新"""

    def test_pricing_refreshed_on_config_change(self, mock_config_factory):
        """custom_models 定价修改后，定价表自动重建并热注入 ConversationManager"""
        service = _make_service()
        priced = mock_config_factory(custom_models=[{
            "id": "priced-model",
            "input_price_per_1m": 2.5,
            "output_price_per_1m": 7.5,
        }])
        # add_provider 落盘并触发变更通知 → 服务订阅回调重建定价表
        get_llm_config().add_provider("mock-1", priced)
        pricing = service._conversation_mgr._pricing
        model_price = pricing["mock-1"]["models"]["priced-model"]
        assert model_price == {"input": 2.5, "output": 7.5}


class TestImageUtils:
    """load_image_as_base64 新位置"""

    def test_load_image_as_base64(self, tmp_path):
        """utils.image_utils.load_image_as_base64 行为与原门面方法一致"""
        from utils.image_utils import load_image_as_base64
        image = tmp_path / "pixel.png"
        raw = b"\x89PNG\r\n\x1a\n"
        image.write_bytes(raw)
        assert load_image_as_base64(str(image)) == base64.b64encode(raw).decode()

    def test_load_image_missing_file_raises(self, tmp_path):
        """文件不存在抛出 OSError（异常路径）"""
        from utils.image_utils import load_image_as_base64
        with pytest.raises(OSError):
            load_image_as_base64(str(tmp_path / "not-exist.png"))
