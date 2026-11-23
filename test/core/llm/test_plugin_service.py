"""
test_plugin_service.py — LLMPluginService 单元测试

测试 core/llm/plugin_service.py 中的 LLMPluginService 类。
"""
import pytest


class TestSingleton:
    """测试单例模式"""

    def test_get_llm_plugin_service_returns_same_instance(self, mocker, mock_logger):
        """多次调用 get_llm_plugin_service() 返回同一实例"""
        from core.llm.plugin_service import get_llm_plugin_service

        # Mock 底层依赖，避免真实初始化
        # （v2 构造期会基于 get_all_providers 构建定价表，需返回空字典）
        mocker.patch("core.llm.plugin_service.get_llm_provider")
        mock_config = mocker.patch("core.llm.plugin_service.get_llm_config").return_value
        mock_config.get_all_providers.return_value = {}
        mocker.patch("core.llm.plugin_service.ConversationManager")
        mocker.patch("core.llm.plugin_service.ToolCallExecutor")
        mocker.patch("core.llm.plugin_service.ToolRegistry")

        svc1 = get_llm_plugin_service()
        svc2 = get_llm_plugin_service()
        assert svc1 is svc2


class TestChatDelegation:
    """测试 chat / stream_chat 委托"""

    def test_chat_converts_dict_messages_to_message_objects(self, mocker):
        """chat() 将字典消息转换为 Message 对象后委托"""
        from core.llm.plugin_service import LLMPluginService
        from core.llm.provider_interface import Message

        mock_llm = mocker.MagicMock()
        mock_llm.chat.return_value = mocker.MagicMock(content="ok")
        mocker.patch("core.llm.plugin_service.get_llm_provider", return_value=mock_llm)
        mocker.patch("core.llm.plugin_service.get_llm_config")
        mocker.patch("core.llm.plugin_service.ConversationManager")
        mocker.patch("core.llm.plugin_service.ToolCallExecutor")
        mocker.patch("core.llm.plugin_service.ToolRegistry")

        svc = LLMPluginService.__new__(LLMPluginService)
        svc._llm = mock_llm

        messages = [{"role": "user", "content": "hello"}]
        svc.chat(messages)

        # 验证转换为 Message 对象
        call_args = mock_llm.chat.call_args
        msg_objs = call_args.kwargs["messages"]
        assert all(isinstance(m, Message) for m in msg_objs)

    def test_stream_chat_converts_dict_messages(self, mocker):
        """stream_chat() 将字典消息转换为 Message 对象"""
        from core.llm.plugin_service import LLMPluginService
        from core.llm.provider_interface import Message

        mock_llm = mocker.MagicMock()
        mocker.patch("core.llm.plugin_service.get_llm_provider", return_value=mock_llm)
        mocker.patch("core.llm.plugin_service.get_llm_config")
        mocker.patch("core.llm.plugin_service.ConversationManager")
        mocker.patch("core.llm.plugin_service.ToolCallExecutor")
        mocker.patch("core.llm.plugin_service.ToolRegistry")

        svc = LLMPluginService.__new__(LLMPluginService)
        svc._llm = mock_llm

        messages = [{"role": "user", "content": "hello"}]
        svc.stream_chat(messages, callback=mocker.MagicMock())

        call_args = mock_llm.stream_chat.call_args
        msg_objs = call_args.kwargs["messages"]
        assert all(isinstance(m, Message) for m in msg_objs)


class TestToolExecutor:
    """测试工具执行器访问"""

    def test_get_tool_executor_returns_tool_executor_instance(self, mocker):
        """get_tool_executor() 返回 ToolCallExecutor 实例"""
        from core.llm.plugin_service import LLMPluginService
        from core.llm.tool_call_executor import ToolCallExecutor, ToolRegistry

        mock_llm = mocker.MagicMock()
        mocker.patch("core.llm.plugin_service.get_llm_provider", return_value=mock_llm)
        mocker.patch("core.llm.plugin_service.get_llm_config")
        mocker.patch("core.llm.plugin_service.ConversationManager")
        mocker.patch("core.llm.plugin_service.ToolCallExecutor")
        mocker.patch("core.llm.plugin_service.ToolRegistry")

        svc = LLMPluginService.__new__(LLMPluginService)
        svc._llm = mock_llm
        svc._tool_executor = mocker.MagicMock(spec=ToolCallExecutor)

        result = svc.get_tool_executor()
        assert result is svc._tool_executor

    def test_get_shared_tool_registry_returns_registry(self, mocker):
        """get_shared_tool_registry() 返回共享的 ToolRegistry"""
        from core.llm.plugin_service import LLMPluginService
        from core.llm.tool_call_executor import ToolRegistry

        mock_llm = mocker.MagicMock()
        mocker.patch("core.llm.plugin_service.get_llm_provider", return_value=mock_llm)
        mocker.patch("core.llm.plugin_service.get_llm_config")
        mocker.patch("core.llm.plugin_service.ConversationManager")
        mocker.patch("core.llm.plugin_service.ToolCallExecutor")
        mocker.patch("core.llm.plugin_service.ToolRegistry")

        svc = LLMPluginService.__new__(LLMPluginService)
        svc._llm = mock_llm
        svc._shared_tool_registry = mocker.MagicMock(spec=ToolRegistry)

        result = svc.get_shared_tool_registry()
        assert result is svc._shared_tool_registry


class TestEmbed:
    """测试 embed 委托"""

    def test_embed_delegates_to_llm_provider(self, mocker):
        """embed() 正确委托给底层 LLM"""
        from core.llm.plugin_service import LLMPluginService

        mock_llm = mocker.MagicMock()
        mock_llm.embed.return_value = [[0.1, 0.2, 0.3]]
        mocker.patch("core.llm.plugin_service.get_llm_provider", return_value=mock_llm)
        mocker.patch("core.llm.plugin_service.get_llm_config")
        mocker.patch("core.llm.plugin_service.ConversationManager")
        mocker.patch("core.llm.plugin_service.ToolCallExecutor")
        mocker.patch("core.llm.plugin_service.ToolRegistry")

        svc = LLMPluginService.__new__(LLMPluginService)
        svc._llm = mock_llm

        result = svc.embed("hello world")
        mock_llm.embed.assert_called_once()
        assert result == [[0.1, 0.2, 0.3]]

    def test_embed_with_list_of_texts(self, mocker):
        """embed() 支持文本列表"""
        from core.llm.plugin_service import LLMPluginService

        mock_llm = mocker.MagicMock()
        mock_llm.embed.return_value = [[0.1], [0.2]]
        mocker.patch("core.llm.plugin_service.get_llm_provider", return_value=mock_llm)
        mocker.patch("core.llm.plugin_service.get_llm_config")
        mocker.patch("core.llm.plugin_service.ConversationManager")
        mocker.patch("core.llm.plugin_service.ToolCallExecutor")
        mocker.patch("core.llm.plugin_service.ToolRegistry")

        svc = LLMPluginService.__new__(LLMPluginService)
        svc._llm = mock_llm

        result = svc.embed(["hello", "world"])
        mock_llm.embed.assert_called_once()


class TestConversationManagement:
    """测试对话管理委托"""

    def test_create_conversation_delegates_to_conversation_manager(self, mocker):
        """create_conversation() 委托给 ConversationManager"""
        from core.llm.plugin_service import LLMPluginService

        mock_conv_mgr = mocker.MagicMock()
        mock_conv_mgr.create_conversation.return_value = "conv-123"
        mocker.patch("core.llm.plugin_service.get_llm_provider")
        mocker.patch("core.llm.plugin_service.get_llm_config")
        mocker.patch("core.llm.plugin_service.ToolCallExecutor")
        mocker.patch("core.llm.plugin_service.ToolRegistry")

        svc = LLMPluginService.__new__(LLMPluginService)
        svc._conversation_mgr = mock_conv_mgr

        conv_id = svc.create_conversation(system_prompt="你是一个助手")
        assert conv_id == "conv-123"
        mock_conv_mgr.create_conversation.assert_called_once()

    def test_get_conversation_delegates(self, mocker):
        """get_conversation() 委托给 ConversationManager"""
        from core.llm.plugin_service import LLMPluginService
        from core.llm.types import Conversation

        mock_conv_mgr = mocker.MagicMock()
        mock_conv = mocker.MagicMock(spec=Conversation)
        mock_conv_mgr.get_conversation.return_value = mock_conv
        mocker.patch("core.llm.plugin_service.get_llm_provider")
        mocker.patch("core.llm.plugin_service.get_llm_config")
        mocker.patch("core.llm.plugin_service.ToolCallExecutor")
        mocker.patch("core.llm.plugin_service.ToolRegistry")

        svc = LLMPluginService.__new__(LLMPluginService)
        svc._conversation_mgr = mock_conv_mgr

        result = svc.get_conversation("conv-123")
        assert result is mock_conv

    def test_delete_conversation_delegates(self, mocker):
        """delete_conversation() 委托给 ConversationManager"""
        from core.llm.plugin_service import LLMPluginService

        mock_conv_mgr = mocker.MagicMock()
        mock_conv_mgr.delete_conversation.return_value = True
        mocker.patch("core.llm.plugin_service.get_llm_provider")
        mocker.patch("core.llm.plugin_service.get_llm_config")
        mocker.patch("core.llm.plugin_service.ToolCallExecutor")
        mocker.patch("core.llm.plugin_service.ToolRegistry")

        svc = LLMPluginService.__new__(LLMPluginService)
        svc._conversation_mgr = mock_conv_mgr

        result = svc.delete_conversation("conv-123")
        assert result is True


class TestUsageStats:
    """测试用量统计"""

    def test_get_usage_stats_delegates_to_conversation_manager(self, mocker):
        """get_usage_stats() 委托给 ConversationManager"""
        from core.llm.plugin_service import LLMPluginService
        from core.llm.types import UsageStats

        mock_conv_mgr = mocker.MagicMock()
        mock_stats = UsageStats(total_tokens=1000, total_cost=0.5)
        mock_conv_mgr.get_usage_stats.return_value = mock_stats
        mocker.patch("core.llm.plugin_service.get_llm_provider")
        mocker.patch("core.llm.plugin_service.get_llm_config")
        mocker.patch("core.llm.plugin_service.ToolCallExecutor")
        mocker.patch("core.llm.plugin_service.ToolRegistry")

        svc = LLMPluginService.__new__(LLMPluginService)
        svc._conversation_mgr = mock_conv_mgr

        result = svc.get_usage_stats()
        assert result.total_tokens == 1000
        assert result.total_cost == 0.5
