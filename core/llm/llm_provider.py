"""LLM 提供商管理器模块

该模块提供对多种大语言模型提供商的统一访问接口。采用单例模式管理全局 LLM 提供商实例，
支持聊天、嵌入、流式对话等功能，并自动管理模型列表缓存。

主要功能:
    - 单例模式全局访问
    - 多提供商配置和动态切换
    - 聊天Completion和流式输出
    - 嵌入（Embedding）向量生成
    - 模型列表自动缓存和刷新
    - 同步/异步 API 支持

Classes:
    LLMProvider: LLM 提供商管理器（单例模式）

Functions:
    get_llm_provider: 获取全局 LLM 提供商实例

使用示例:
    >>> from core.llm import LLMProvider, get_llm_provider, Message
    >>> # 获取单例实例
    >>> provider = get_llm_provider()
    >>> # 发送聊天请求
    >>> response = provider.chat([Message("user", "你好")])
    >>> # 流式输出（回调契约为 (chunk_text: str, done: bool)，返回完整文本）
    >>> full = provider.stream_chat([Message("user", "你好")],
    ...                             callback=lambda text, done: print(text, end=""))
"""

import json
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple, Union, Callable, AsyncIterator, TYPE_CHECKING

from .config import LLMConfig, ProviderConfig
from .provider_interface import (
    ILLM, Message, ChatResponse, EmbeddingResponse, ModelInfo, UsageInfo,
    ModelCheckResult, ToolCall,
    DEFAULT_TEMPERATURE,
)
from .providers import get_adapter_class, PROVIDER_REGISTRY
from .exceptions import ConfigurationError
from .model_schema import CAPABILITY_EMBEDDING
from .usage_record_store import get_usage_record_store
from .types import UsageRecord, DEFAULT_PROVIDER
# 说明：LLMProvider 是 core 层统一入口，面向插件的契约由
# LLMPluginService（实现 core.interfaces.ILLMService）承担，
# 插件不应直接依赖本类。

if TYPE_CHECKING:
    from .provider_interface import ChatResponse

from utils.logging_tools import LoggerManager, get_name


# ==================== 探测相关常量 ====================

# check_model 的默认探测超时（秒）
MODEL_CHECK_DEFAULT_TIMEOUT: float = 15.0
# 连通性探测使用的最小化请求文本
MODEL_PROBE_TEXT = "hi"
# 聊天探测的最大生成 token 数（尽量压低探测成本）
MODEL_PROBE_MAX_TOKENS = 1
# 聊天探测温度（固定为 0，保证探测行为稳定）
MODEL_PROBE_TEMPERATURE = 0.0
# 秒 → 毫秒换算系数
_MILLIS_PER_SECOND: float = 1000.0


class LLMProvider:
    """大语言模型提供商管理器（单例模式）

    统一管理多个 LLM 提供商的配置和调用，是应用程序访问 LLM 能力的入口点。

    主要特性:
        - 单例模式：全局只有一个实例，避免重复初始化
        - 多提供商支持：同时管理多个 LLM 提供商（GLM、MiniMax、SiliconFlow、Ollama）
        - 自动模型获取：启动时自动拉取所有提供商的模型列表
        - 缓存管理：本地缓存模型列表，支持强制刷新
        - 灵活配置：支持启用/禁用特定提供商的特定功能

    Class Attributes:
        _instance: 类变量，存储单例实例
        _lock: 类变量，线程锁，用于线程安全单例创建

    Attributes:
        _config: LLM 配置管理器
        _providers: 提供商实例字典 {name: ILLM 实例}
        _models_cache: 模型列表缓存 {provider_name: [ModelInfo]}
        _logger: 日志管理器

    使用方式:
        >>> from core.llm import get_llm_provider, Message
        >>> provider = get_llm_provider()
        >>> # 聊天
        >>> response = provider.chat([Message("user", "你好")])
        >>> # 嵌入
        >>> embeddings = provider.embed("要嵌入的文本")
        >>> # 获取模型
        >>> models = provider.get_models()
    """

    _instance: Optional['LLMProvider'] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """单例模式：确保全局只有一个实例

        使用双重检查锁定（Double-Checked Locking）实现线程安全的单例模式。
        第一次检查无需加锁，后续检查和创建需要加锁保护。

        Returns:
            LLMProvider: 单例实例
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """初始化 LLM 提供商管理器

        初始化配置管理器、创建所有已配置的提供商实例、并自动获取模型列表。
        使用 _initialized 标志防止重复初始化。
        """
        if hasattr(self, '_initialized') and self._initialized:
            return

        self._initialized = True
        self._config = LLMConfig()
        self._providers: Dict[str, ILLM] = {}
        self._models_cache: Dict[str, List[ModelInfo]] = {}  # 模型缓存
        self._logger = LoggerManager()
        self._usage_store = get_usage_record_store()
        # 轻量健康跟踪：{provider_name: (是否健康, 最近错误信息)}
        self._health: Dict[str, Tuple[bool, Optional[str]]] = {}
        # "default" 粘性缓存：首次自动选择后记住，避免同一进程内漂移
        self._default_chat_provider: Optional[str] = None
        self._default_embedding_provider: Optional[str] = None
        # 最近一次流式请求的聚合响应存储（按线程隔离，见 last_stream_response property）
        self._stream_local = threading.local()
        # 已加载配置的版本号占位（_init_providers 后同步，供惰性刷新比对）
        self._loaded_config_version = 0
        self._init_providers()
        self._sync_config_version()
        self._fetch_all_models()  # 启动时自动拉取模型列表

    @property
    def last_stream_response(self) -> Optional[ChatResponse]:
        """最近一次流式请求的聚合响应（按线程隔离）

        存储在 threading.local 中：并发流式请求各自读写本线程的副本，
        互不覆盖；同一线程内的读写语义与旧的普通实例属性完全一致。

        Returns:
            Optional[ChatResponse]: 本线程最近一次流式请求的聚合响应
        """
        return getattr(self._stream_local, "last_stream_response", None)

    @last_stream_response.setter
    def last_stream_response(self, value: Optional[ChatResponse]) -> None:
        """设置本线程最近一次流式请求的聚合响应（按线程隔离）

        Args:
            value: 聚合响应对象，None 表示清空本线程的记录
        """
        self._stream_local.last_stream_response = value

    def _init_providers(self) -> None:
        """初始化所有已配置的 LLM 提供商

        从配置中读取所有已配置的提供商，创建对应的实例。
        如果某个提供商创建失败，记录错误日志并继续初始化其他提供商。
        """
        provider_configs = self._config.get_all_providers()

        for name, config_data in provider_configs.items():
            try:
                self._create_provider(name, config_data.to_dict())
            except Exception as e:
                self._logger.error(get_name(), f'Failed to initialize provider {name}: {e}')

    def _fetch_all_models(self) -> None:
        """启动时加载所有提供商的模型列表

        流程：
        1. 先从本地缓存文件加载，确保插件立即可用
        2. 再尝试从远程 API 刷新（静默失败，不覆盖已有缓存）
        3. 刷新成功时同步更新本地缓存文件

        这样插件在启动后即可获取本地缓存的模型列表，无需等待网络请求。
        """
        for name, provider in self._providers.items():
            # 1. 加载本地缓存（兼容 providers/base.py 写入的 TTL 时间戳信封）
            cached = self._config.load_models_cache(name)
            if cached:
                if isinstance(cached, dict):
                    models_data = cached.get("models", [])
                else:
                    models_data = cached
                models = [ModelInfo.from_dict(m) for m in models_data if isinstance(m, dict)]
                self._models_cache[name] = models
                self._logger.info(get_name(), f'Loaded {len(models)} models for {name} from cache')

            # 2. 尝试从远程刷新（静默，不覆盖已有缓存）
            try:
                models = provider.refresh_models(force=True)
                self._models_cache[name] = models
                # 同步写回本地缓存文件
                self._config.save_models_cache(
                    name,
                    [m.to_dict() for m in models]
                )
                self._logger.info(get_name(), f'Refreshed {len(models)} models for {name}')
            except Exception as e:
                # 刷新失败但已有本地缓存，不覆盖
                if name not in self._models_cache or not self._models_cache[name]:
                    self._models_cache[name] = []
                    self._logger.warning(get_name(), f'No cache for {name}, network unavailable')
                else:
                    self._logger.info(get_name(), f'Using cached models for {name}, remote fetch failed: {e}')

    # ==================== 惰性配置刷新 ====================

    def _sync_config_version(self) -> None:
        """同步已加载配置的版本号

        防御性读取：部分冒烟脚本以 mock 形态替换 LLMConfig（无 version
        属性），此时回退为 0。
        """
        self._loaded_config_version = getattr(self._config, "version", 0)

    def _refresh_config_if_needed(self) -> None:
        """惰性配置刷新：配置版本不一致时自动 reload_config

        公开入口（chat/stream_chat/embed/get_models 等）在入口处调用，
        调用方无需再手动 reload_config()。幂等；并发下通过类级锁双重
        检查，保证同一次变更只刷新一次。
        """
        current_version = getattr(self._config, "version", None)
        if current_version is None or current_version == self._loaded_config_version:
            return
        with self._lock:
            if self._loaded_config_version == getattr(self._config, "version", None):
                return
            self.reload_config()

    def refresh_provider_models(self, provider_name: str, force: bool = False) -> List[ModelInfo]:
        """刷新指定提供商的模型列表

        强制或非强制刷新指定提供商的模型列表，并更新缓存。

        Args:
            provider_name: 提供商名称
            force: 是否强制从 API 刷新，忽略缓存

        Returns:
            List[ModelInfo]: 模型信息列表，如果失败返回空列表
        """
        self._refresh_config_if_needed()
        provider = self._providers.get(provider_name)
        if not provider:
            return []

        try:
            models = provider.refresh_models(force=force)
            self._models_cache[provider_name] = models
            # 同步保存到本地缓存文件
            self._config.save_models_cache(
                provider_name,
                [m.to_dict() for m in models]
            )
            return models
        except Exception as e:
            self._logger.error(get_name(), f'Failed to refresh models for {provider_name}: {e}')
            return []

    def refresh_all_models(self, force: bool = False) -> Dict[str, List[ModelInfo]]:
        """刷新所有提供商的模型列表

        遍历调用所有提供商的模型刷新方法。

        Args:
            force: 是否强制从 API 刷新

        Returns:
            Dict[str, List[ModelInfo]]: 提供商名称到模型列表的映射字典
        """
        for name in self._providers.keys():
            self.refresh_provider_models(name, force=force)
        return self._models_cache

    def get_cached_models(self, provider_name: str) -> List[ModelInfo]:
        """获取指定提供商的缓存模型列表

        Args:
            provider_name: 提供商名称

        Returns:
            List[ModelInfo]: 模型信息列表，如果提供商不存在返回空列表
        """
        self._refresh_config_if_needed()
        return self._models_cache.get(provider_name, [])

    def _create_provider(self, name: str, config: Dict[str, Any]) -> Optional[ILLM]:
        """创建 LLM 提供商实例（按适配器家族分发）

        按配置中的 ``adapter`` 键查询适配器注册表创建实例；缺省时回退为
        实例 id（预设默认实例 id == 适配器家族键）。未知适配器记 ERROR
        日志并跳过该实例（返回 None、不注册），不影响其余实例的创建。

        Args:
            name: 提供商实例 id（键名）
            config: 提供商配置字典，包含 api_key、base_url、adapter 等

        Returns:
            Optional[ILLM]: 创建的提供商实例；未知适配器时返回 None
        """
        adapter_key = config.get("adapter") or name
        provider_class = get_adapter_class(adapter_key)

        if not provider_class:
            self._logger.error(
                get_name(),
                f'实例 {name} 的适配器 "{adapter_key}" 未注册，已跳过该实例'
            )
            return None

        # 创建实例，传递 provider_name 用于模型缓存标识
        provider = provider_class(config, provider_name=name)
        self._providers[name] = provider
        return provider

    def get_provider(self, name: str) -> Optional[ILLM]:
        """获取指定名称的提供商实例

        Args:
            name: 提供商名称

        Returns:
            Optional[ILLM]: 提供商实例，如果不存在返回 None
        """
        return self._providers.get(name)

    def get_all_providers(self) -> Dict[str, ILLM]:
        """获取所有已创建的提供商实例

        Returns:
            Dict[str, ILLM]: 提供商名称到实例的映射字典
        """
        return self._providers.copy()

    def get_enabled_providers(self, feature: str = "chat") -> Dict[str, ILLM]:
        """获取已启用的提供商（按功能类型筛选）

        根据功能类型（chat 或 embedding）筛选已启用的提供商。

        Args:
            feature: 功能类型，"chat" 表示聊天功能，"embedding" 表示嵌入功能

        Returns:
            Dict[str, ILLM]: 符合条件的提供商实例字典
        """
        result = {}
        enabled_configs = self._config.get_enabled_providers(feature)

        for name in enabled_configs.keys():
            provider = self._providers.get(name)
            if provider:
                result[name] = provider

        return result

    def add_provider(self, name: str, config: ProviderConfig) -> None:
        """添加或更新 LLM 提供商配置

        同时更新配置文件和内存中的实例。

        Args:
            name: 提供商名称
            config: 提供商配置对象
        """
        self._config.add_provider(name, config)
        self._health.pop(name, None)  # 重建实例，清除旧健康状态
        self._create_provider(name, config.to_dict())
        # 本次变更已即时生效，同步版本号避免后续入口触发冗余全量刷新
        self._sync_config_version()

    def remove_provider(self, name: str) -> bool:
        """移除 LLM 提供商

        关闭连接并从配置中删除。

        Args:
            name: 提供商名称

        Returns:
            bool: 操作是否成功（返回配置删除结果）
        """
        if name in self._providers:
            provider = self._providers[name]
            provider.close()
            del self._providers[name]

        # 清除健康状态与 "default" 粘性缓存（下次 default 调用重新选择）
        self._health.pop(name, None)
        if self._default_chat_provider == name:
            self._default_chat_provider = None
        if self._default_embedding_provider == name:
            self._default_embedding_provider = None

        removed = self._config.remove_provider(name)
        # 与 add_provider 同理：变更已即时生效，同步版本号
        self._sync_config_version()
        return removed

    def _record_usage(
        self,
        response: ChatResponse,
        provider: str,
        model: str,
        is_stream: bool,
        duration_ms: float,
        conversation_id: str = "",
    ) -> None:
        """记录 API 用量到持久化存储

        Args:
            response: 聊天响应对象（需携带真实的 UsageInfo 才记录）
            provider: 实际解析出的提供商名称（不会是 "default"）
            model: 实际使用的模型名称
            is_stream: 是否为流式请求
            duration_ms: 请求耗时（毫秒）
            conversation_id: 关联的对话 ID，无对话上下文时为 ""
        """
        usage = getattr(response, "usage", None)
        # 仅记录真实的 UsageInfo（防御 mock / 非标准响应造成的垃圾数据）
        if usage is None or not isinstance(usage, UsageInfo):
            return
        cached_tokens = getattr(usage, "cache_read_tokens", 0) or 0
        record = UsageRecord(
            id="",
            timestamp=datetime.now(timezone.utc),  # UsageRecord 契约：UTC 时间戳
            conversation_id=conversation_id,
            provider=provider,
            model=model,
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
            total_tokens=usage.total_tokens or 0,
            cached_tokens=cached_tokens,
            cache_hit=cached_tokens > 0,
            is_stream=is_stream,
            duration_ms=round(duration_ms, 2),
        )
        self._usage_store.record(record)

    def reload_config(self) -> None:
        """重新加载 LLM 提供商配置

        关闭所有现有连接，清空实例缓存，重新从配置文件初始化。
        用于热重载配置的场景。
        """
        # 关闭现有连接
        for provider in self._providers.values():
            provider.close()

        self._providers.clear()
        # 同步清理模型缓存、健康状态与 "default" 粘性缓存，避免脏数据残留
        self._models_cache.clear()
        self._health.clear()
        self._default_chat_provider = None
        self._default_embedding_provider = None
        self.last_stream_response = None
        self._config = LLMConfig()
        self._init_providers()
        self._sync_config_version()

    # ==================== 内部辅助方法 ====================

    @staticmethod
    def _filter_none_kwargs(params: Dict[str, Any]) -> Dict[str, Any]:
        """剔除值为 None 的可选参数

        None 表示"不指定"，不应写入 API payload（否则会变成 null 导致 400）。

        Args:
            params: 原始参数字典

        Returns:
            Dict[str, Any]: 仅包含非 None 值的参数字典
        """
        return {k: v for k, v in params.items() if v is not None}

    def _resolve_default_provider(self, feature: str) -> str:
        """解析 "default" 提供商名称（带粘性缓存）

        首次自动选择后记住结果，后续 default 调用使用同一提供商；
        该提供商被禁用或移除时自动重新选择。

        Args:
            feature: 功能类型，"chat" 或 "embedding"

        Returns:
            str: 实际提供商名称

        Raises:
            ConfigurationError: 没有启用的提供商时抛出
        """
        cache_attr = ("_default_chat_provider" if feature == "chat"
                      else "_default_embedding_provider")
        enabled = self.get_enabled_providers(feature)
        if not enabled:
            raise ConfigurationError(f"No enabled {feature} provider")
        cached = getattr(self, cache_attr, None)
        if cached and cached in enabled and cached in self._providers:
            return cached
        chosen = next(iter(enabled.keys()))
        setattr(self, cache_attr, chosen)
        return chosen

    def resolve_provider_name(self, name: str, feature: str = "chat") -> str:
        """解析提供商名称：DEFAULT_PROVIDER 时按功能自动选择（带粘性缓存）

        Args:
            name: 提供商名称或 DEFAULT_PROVIDER（"default"）
            feature: 功能类型，"chat" 或 "embedding"

        Returns:
            str: 实际提供商名称（非默认引用时原样返回）
        """
        if name == DEFAULT_PROVIDER:
            return self._resolve_default_provider(feature)
        return name

    def get_default_provider_id(self, feature: str = "chat") -> Optional[str]:
        """获取默认实例解析结果（不抛异常）

        复用 _resolve_default_provider 的粘性缓存逻辑；无任何可用实例时
        记 WARNING 日志并返回 None（供 UI/插件感知「默认实例未配置」状态）。

        Args:
            feature: 功能类型，"chat" 或 "embedding"

        Returns:
            Optional[str]: 默认实例 id；无可用实例时为 None
        """
        try:
            return self._resolve_default_provider(feature)
        except ConfigurationError:
            self._logger.warning(
                get_name(), f"没有可用的 {feature} 提供商实例，默认解析返回 None")
            return None

    def get_provider_health(
        self,
        name: Optional[str] = None,
    ) -> Union[Dict[str, Tuple[bool, Optional[str]]], Tuple[bool, Optional[str]]]:
        """获取提供商健康状态

        name 为 None 时返回所有实例的全量健康字典；传入实例 id 时返回
        单个实例的健康元组（签名向后兼容）。

        Args:
            name: 提供商实例 id；None 表示查询全部实例

        Returns:
            全量查询：Dict[str, Tuple[bool, Optional[str]]]；
            单个查询：Tuple[bool, Optional[str]]（是否健康, 最近错误信息）
        """
        if name is None:
            return {n: self._single_health(n) for n in self._providers}
        return self._single_health(name)

    def _single_health(self, name: str) -> Tuple[bool, Optional[str]]:
        """获取单个实例的健康状态

        未调用过的提供商默认健康；同时参考 provider 实例的 last_error 属性。

        Args:
            name: 提供商实例 id

        Returns:
            Tuple[bool, Optional[str]]: (是否健康, 最近错误信息)
        """
        if name in self._health:
            return self._health[name]
        provider = self._providers.get(name)
        err = getattr(provider, "last_error", None) if provider is not None else None
        if err:
            return False, str(err)
        return True, None

    def check_provider(self, name: str) -> Tuple[bool, Optional[str], int]:
        """连通性检查：强制刷新指定实例的模型列表

        成功时同步更新模型缓存与本地缓存文件，并记录健康状态。

        Args:
            name: 提供商实例 id

        Returns:
            Tuple[bool, Optional[str], int]:
                (是否成功, 错误信息, 模型数)；实例不存在时返回
                (False, 中文错误信息, 0)
        """
        self._refresh_config_if_needed()
        provider = self._providers.get(name)
        if provider is None:
            message = f"提供商实例不存在: {name}"
            self._logger.warning(get_name(), f"连通性检查跳过：{message}")
            return False, message, 0

        try:
            models = provider.refresh_models(force=True)
        except Exception as e:
            self._health[name] = (False, str(e))
            return False, str(e), 0

        self._models_cache[name] = models
        self._config.save_models_cache(name, [m.to_dict() for m in models])
        self._health[name] = (True, None)
        return True, None, len(models)

    def check_model(
        self,
        provider_name: str,
        model_id: str,
        timeout: float = MODEL_CHECK_DEFAULT_TIMEOUT,
    ) -> ModelCheckResult:
        """单个模型的连通性探测（最小化请求）

        探测方式按模型能力选择：声明了嵌入能力的模型走 embed 探测，
        其余走 chat 探测（"hi" + max_tokens=1 + temperature=0）。
        timeout 通过临时覆盖实例的读取超时生效（探测结束后恢复）。

        Args:
            provider_name: 提供商实例 id
            model_id: 待探测的模型 id
            timeout: 探测超时（秒），默认 MODEL_CHECK_DEFAULT_TIMEOUT

        Returns:
            ModelCheckResult: 探测结果；实例不存在时 skipped=True 并附中文原因
        """
        self._refresh_config_if_needed()
        provider = self._providers.get(provider_name)
        if provider is None:
            return ModelCheckResult(
                ok=False, latency_ms=None, error=None,
                skipped=True,
                skip_reason=f"提供商实例不存在: {provider_name}",
            )

        use_embedding = self._model_prefers_embedding(provider_name, model_id)
        previous_timeout = getattr(provider, "timeout", None)
        if previous_timeout is not None:
            provider.timeout = timeout

        started = time.perf_counter()
        try:
            if use_embedding:
                self.embed([MODEL_PROBE_TEXT], provider=provider_name, model=model_id)
            else:
                self.chat(
                    [Message(role="user", content=MODEL_PROBE_TEXT)],
                    provider=provider_name,
                    model=model_id,
                    max_tokens=MODEL_PROBE_MAX_TOKENS,
                    temperature=MODEL_PROBE_TEMPERATURE,
                )
        except Exception as e:
            return ModelCheckResult(
                ok=False, latency_ms=self._elapsed_ms(started), error=str(e))
        finally:
            if previous_timeout is not None:
                provider.timeout = previous_timeout

        return ModelCheckResult(ok=True, latency_ms=self._elapsed_ms(started), error=None)

    def _model_prefers_embedding(self, provider_name: str, model_id: str) -> bool:
        """判断指定模型条目是否声明了嵌入能力（决定探测走 embed 还是 chat）

        扫描实例缓存的模型列表（ModelInfo 形态）：优先看 support_embedding
        布尔位，其次看 extra 中统一 schema 的 capabilities 列表；条目未命中
        时按聊天模型处理（走 chat 探测）。

        Args:
            provider_name: 提供商实例 id
            model_id: 模型 id

        Returns:
            bool: True 表示应使用 embed 探测
        """
        for model in self.get_cached_models(provider_name):
            if getattr(model, "id", None) != model_id:
                continue
            if getattr(model, "support_embedding", False):
                return True
            extra = getattr(model, "extra", None)
            capabilities = extra.get("capabilities") if isinstance(extra, dict) else None
            if isinstance(capabilities, list) and CAPABILITY_EMBEDDING in capabilities:
                return True
        return False

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        """计算自 started（time.perf_counter）以来的毫秒数

        Args:
            started: time.perf_counter() 的起始读数

        Returns:
            float: 耗时毫秒数（保留两位小数）
        """
        return round((time.perf_counter() - started) * _MILLIS_PER_SECOND, 2)

    @property
    def last_errors(self) -> Dict[str, str]:
        """聚合各提供商的最近错误信息（供 UI 展示真实错误）

        合并 provider 实例的 last_error 属性与调用层健康跟踪中的错误。

        Returns:
            Dict[str, str]: {提供商名称: 错误信息}（仅包含有错误的提供商）
        """
        errors: Dict[str, str] = {}
        for name, provider in self._providers.items():
            err = getattr(provider, "last_error", None)
            if err:
                errors[name] = str(err)
        for name, (ok, err) in self._health.items():
            if not ok and err:
                errors[name] = err
        return errors

    @staticmethod
    def _extract_finish_reason(chunk: ChatResponse) -> Optional[str]:
        """从流式响应块中提取 finish_reason

        兼容两种位置：ChatResponse 自身属性 / extra 字典（含嵌套 extra）。

        Args:
            chunk: 流式响应块

        Returns:
            Optional[str]: finish_reason 字符串，未出现时为 None
        """
        fr = getattr(chunk, "finish_reason", None)
        if isinstance(fr, str) and fr:
            return fr
        extra = getattr(chunk, "extra", None)
        if isinstance(extra, dict):
            fr = extra.get("finish_reason")
            if isinstance(fr, str) and fr:
                return fr
            inner = extra.get("extra")
            if isinstance(inner, dict):
                fr = inner.get("finish_reason")
                if isinstance(fr, str) and fr:
                    return fr
        return None

    @staticmethod
    def _normalize_complete_tool_call(raw: Dict[str, Any]) -> Dict[str, Any]:
        """把完整的 tool_call 字典规范为 OpenAI 风格（arguments 为 JSON 字符串）

        Args:
            raw: 完整 tool_call 字典（OpenAI 风格或 ToolCall.to_dict 产出）

        Returns:
            Dict[str, Any]: {"id", "type", "function": {"name", "arguments"}}
        """
        function = raw.get("function")
        if not isinstance(function, dict):
            function = {}
        arguments = function.get("arguments", "")
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments, ensure_ascii=False)
        return {
            "id": raw.get("id") or "",
            "type": raw.get("type") or "function",
            "function": {"name": function.get("name") or "", "arguments": arguments},
        }

    @staticmethod
    def _merge_stream_tool_calls(agg: Dict[Any, Dict[str, Any]], tool_calls) -> None:
        """聚合流式响应块中的 tool_calls（OpenAI 风格）

        流式工具调用按 index 分片下发：id/name 通常只在首个分片出现，
        arguments 以字符串片段逐块追加，按 index 合并。块携带完整
        tool_calls（无 index 的 dict，或已为 ToolCall 对象）时按调用 id
        落槽（complete_{id}，无 id 时按块内位置），重复出现覆盖同槽，
        避免重复累计。

        Args:
            agg: 聚合结果字典 {槽位键: OpenAI 风格 tool_call}
            tool_calls: 当前响应块携带的 tool_calls 列表
        """
        if not tool_calls or not isinstance(tool_calls, (list, tuple)):
            return
        for pos, tc in enumerate(tool_calls):
            raw = tc.to_dict() if isinstance(tc, ToolCall) else tc
            if not isinstance(raw, dict):
                continue
            idx = raw.get("index")
            if not isinstance(idx, int):
                slot_key = f"complete_{raw.get('id') or pos}"
                agg[slot_key] = LLMProvider._normalize_complete_tool_call(raw)
                continue
            slot = agg.setdefault(idx, {
                "id": "",
                "type": "function",
                "function": {"name": "", "arguments": ""},
            })
            tc_id = raw.get("id")
            if tc_id:
                slot["id"] = tc_id
            fn = raw.get("function")
            if isinstance(fn, dict):
                name = fn.get("name")
                if name:
                    slot["function"]["name"] += name
                arguments = fn.get("arguments")
                if isinstance(arguments, str) and arguments:
                    slot["function"]["arguments"] += arguments
                elif isinstance(arguments, dict):
                    slot["function"]["arguments"] = json.dumps(arguments, ensure_ascii=False)

    # ==================== 便捷方法 ====================

    def chat(
        self,
        messages: List[Union[Message, Dict]],
        provider: str = DEFAULT_PROVIDER,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        conversation_id: str = "",
        **kwargs
    ) -> ChatResponse:
        """发送聊天请求（同步）

        向 LLM 发送聊天请求，获取完整的响应文本。
        如果 provider 参数为 "default"，会自动选择启用的提供商（带粘性缓存）。

        Args:
            messages: 消息列表，支持 Message 对象或字典格式
            provider: 提供商名称，"default" 自动选择启用的提供商
            model: 模型名称（可选，"default" 或 None 表示使用配置中的模型）
            temperature: 温度参数（可选，None 表示不指定，不写入 payload）
            max_tokens: 最大生成 token 数（可选，None 表示不指定）
            conversation_id: 关联的对话 ID（用于用量记录关联，可选）
            **kwargs: 其他提供商特定参数（为 None 的值会被剔除）

        Returns:
            ChatResponse: 聊天响应对象

        Raises:
            ConfigurationError: 当没有启用的提供商或提供商不存在时抛出
        """
        self._refresh_config_if_needed()
        if provider == DEFAULT_PROVIDER:
            provider = self._resolve_default_provider("chat")
        if model == "default":
            model = None

        provider_instance = self.get_provider(provider)
        if not provider_instance:
            raise ConfigurationError(f"Provider not found: {provider}")

        # 双保险：None 值不写入 payload（provider 层也会过滤）
        call_kwargs = self._filter_none_kwargs({
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        })

        t0 = time.perf_counter()
        try:
            response = provider_instance.chat(
                messages=messages,
                **call_kwargs,
            )
        except Exception as e:
            self._health[provider] = (False, str(e))
            raise
        duration_ms = (time.perf_counter() - t0) * 1000
        self._health[provider] = (True, None)

        # 记录用量：provider/model 使用实际解析值（ChatResponse 携带的 model 优先）
        actual_model = getattr(response, "model", None)
        if not isinstance(actual_model, str) or not actual_model:
            actual_model = model or getattr(provider_instance, "chat_model", "") or ""
        self._record_usage(
            response=response,
            provider=provider,
            model=actual_model,
            is_stream=False,
            duration_ms=duration_ms,
            conversation_id=conversation_id,
        )

        return response

    def stream_chat(
        self,
        messages: List[Union[Message, Dict]],
        provider: str = DEFAULT_PROVIDER,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        callback: Optional[Callable[[str, bool], None]] = None,
        conversation_id: str = "",
        **kwargs
    ) -> str:
        """发送流式聊天请求（同步执行，真实消费流）

        迭代底层 provider 的流式生成器，将每个 ChatResponse 块适配为对外回调
        契约 callback(chunk_text: str, done: bool)，并返回拼接的完整文本。
        聚合后的完整响应（含 tool_calls / usage）存放在 last_stream_response。

        Args:
            messages: 消息列表
            provider: 提供商名称，"default" 自动选择启用的提供商（带粘性缓存）
            model: 模型名称（可选，"default" 或 None 表示使用配置中的模型）
            temperature: 温度参数（可选，None 表示不指定）
            max_tokens: 最大 token 数（可选，None 表示不指定）
            callback: 流式回调 (chunk_text: str, done: bool)，每块调用一次；
                流正常结束但未出现 finish_reason 块时，补发一次 ("", True)
            conversation_id: 关联的对话 ID（用于用量记录关联，可选）
            **kwargs: 其他参数（为 None 的值会被剔除）

        Returns:
            str: 拼接后的完整响应文本

        Raises:
            ConfigurationError: 当提供商不存在时抛出
            NotImplementedError: 当提供商不支持流式输出时抛出
        """
        self._refresh_config_if_needed()
        if provider == DEFAULT_PROVIDER:
            provider = self._resolve_default_provider("chat")
        if model == "default":
            model = None

        provider_instance = self.get_provider(provider)
        if not provider_instance:
            raise ConfigurationError(f"Provider not found: {provider}")

        call_kwargs = self._filter_none_kwargs({
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        })

        t0 = time.perf_counter()
        try:
            # 不传底层 callback（其契约为 ChatResponse 块），在本层统一做适配
            response_gen = provider_instance.stream_chat(
                messages=messages,
                **call_kwargs,
            )
        except Exception as e:
            self._health[provider] = (False, str(e))
            raise

        content_parts: List[str] = []
        reasoning_parts: List[str] = []
        tool_calls_agg: Dict[Any, Dict[str, Any]] = {}
        last_usage: Optional[UsageInfo] = None
        agg_model = ""
        finished = False

        try:
            for chunk in response_gen:
                text = getattr(chunk, "content", "") or ""
                if not isinstance(text, str):
                    text = str(text)
                content_parts.append(text)

                # 思考过程增量聚合（末块回填到聚合响应）
                reasoning = getattr(chunk, "reasoning_content", "") or ""
                if isinstance(reasoning, str) and reasoning:
                    reasoning_parts.append(reasoning)

                # 结束标志：末块 finish_reason 有值
                done = self._extract_finish_reason(chunk) is not None
                # usage：部分 API 在流式末块返回 usage（契约：provider 层填充）
                chunk_usage = getattr(chunk, "usage", None)
                if isinstance(chunk_usage, UsageInfo):
                    last_usage = chunk_usage
                # model：取首个有效的字符串 model
                chunk_model = getattr(chunk, "model", None)
                if isinstance(chunk_model, str) and chunk_model:
                    agg_model = chunk_model
                # tool_calls 增量聚合（OpenAI 风格分片）
                self._merge_stream_tool_calls(
                    tool_calls_agg, getattr(chunk, "tool_calls", None))

                if callback:
                    try:
                        callback(text, done)
                    except Exception as cb_err:
                        self._logger.warning(
                            get_name(), f"stream_chat callback error: {cb_err}")
                if done:
                    finished = True
        except Exception as e:
            self._health[provider] = (False, str(e))
            raise

        duration_ms = (time.perf_counter() - t0) * 1000
        full_text = "".join(content_parts)

        if callback and not finished:
            # 流正常结束但未出现 finish_reason 块：补发结束标志
            try:
                callback("", True)
            except Exception as cb_err:
                self._logger.warning(
                    get_name(), f"stream_chat callback error: {cb_err}")

        aggregated = ChatResponse(
            content=full_text,
            model=(agg_model or model
                   or getattr(provider_instance, "chat_model", "") or ""),
            reasoning_content="".join(reasoning_parts),
            tool_calls=list(tool_calls_agg.values()),
            usage=last_usage,
        )
        self.last_stream_response = aggregated

        # 流式用量记录：仅当末块携带 usage 时记录；
        # 部分 API 流式不返回 usage，此时保持不记录（与既有行为一致）
        if last_usage is not None:
            self._record_usage(
                response=aggregated,
                provider=provider,
                model=aggregated.model,
                is_stream=True,
                duration_ms=duration_ms,
                conversation_id=conversation_id,
            )
        self._health[provider] = (True, None)
        return full_text

    def embed(
        self,
        texts: Union[str, List[str]],
        provider: str = DEFAULT_PROVIDER,
        model: Optional[str] = None,
        **kwargs
    ) -> List[EmbeddingResponse]:
        """发送文本嵌入请求（同步）

        将文本转换为向量嵌入。

        Args:
            texts: 单个文本或文本列表
            provider: 提供商名称
            model: 模型名称
            **kwargs: 其他参数

        Returns:
            List[EmbeddingResponse]: 嵌入响应列表

        Raises:
            ConfigurationError: 当没有启用的嵌入提供商或提供商不存在时抛出
        """
        self._refresh_config_if_needed()
        if provider == DEFAULT_PROVIDER:
            provider = self._resolve_default_provider("embedding")
        if model == "default":
            model = None

        provider_instance = self.get_provider(provider)
        if not provider_instance:
            raise ConfigurationError(f"Provider not found: {provider}")

        call_kwargs = self._filter_none_kwargs({"model": model, **kwargs})
        try:
            result = provider_instance.embed(
                texts=texts,
                **call_kwargs,
            )
        except Exception as e:
            self._health[provider] = (False, str(e))
            raise
        self._health[provider] = (True, None)
        return result

    def get_models(self, provider: Optional[str] = None) -> Dict[str, List[ModelInfo]]:
        """获取可用模型列表

        获取指定提供商或所有提供商的模型列表。

        Args:
            provider: 可选，指定提供商名称。None 表示获取所有提供商的模型

        Returns:
            Dict[str, List[ModelInfo]]: 提供商名称到模型列表的映射字典
        """
        self._refresh_config_if_needed()
        if provider:
            provider_instance = self.get_provider(provider)
            if provider_instance:
                return {provider: provider_instance.get_models()}
            return {}

        result = {}
        for name, provider_instance in self._providers.items():
            result[name] = provider_instance.get_models()
        return result

    # ==================== 异步方法 ====================

    async def async_chat(
        self,
        messages: List[Union[Message, Dict]],
        provider: str = DEFAULT_PROVIDER,
        model: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ChatResponse:
        """异步发送聊天请求

        异步版本的聊天接口，适用于需要高并发的场景。
        与同步 chat 一致：解析 "default" 走粘性缓存、记录用量并更新健康状态。

        Args:
            messages: 消息列表
            provider: 提供商名称，"default" 自动选择启用的提供商（带粘性缓存）
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数

        Returns:
            ChatResponse: 聊天响应对象

        Raises:
            ConfigurationError: 当没有启用的提供商或提供商不存在时抛出
        """
        if provider == DEFAULT_PROVIDER:
            provider = self._resolve_default_provider("chat")
        if model == "default":
            model = None

        provider_instance = self.get_provider(provider)
        if not provider_instance:
            raise ConfigurationError(f"Provider not found: {provider}")

        t0 = time.perf_counter()
        try:
            response = await provider_instance.async_chat(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
        except Exception as e:
            self._health[provider] = (False, str(e))
            raise
        duration_ms = (time.perf_counter() - t0) * 1000
        self._health[provider] = (True, None)

        # 记录用量：与同步 chat 一致的模型解析规则
        actual_model = getattr(response, "model", None)
        if not isinstance(actual_model, str) or not actual_model:
            actual_model = model or getattr(provider_instance, "chat_model", "") or ""
        self._record_usage(
            response=response,
            provider=provider,
            model=actual_model,
            is_stream=False,
            duration_ms=duration_ms,
        )

        return response

    async def async_stream_chat(
        self,
        messages: List[Union[Message, Dict]],
        provider: str = DEFAULT_PROVIDER,
        model: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Any:
        """异步发送流式聊天请求

        异步版本的流式聊天接口。返回异步生成器，迭代过程中收集末块
        usage，流正常结束时记录用量并更新健康状态（与同步 stream_chat
        对齐）；迭代中发生异常时标记不健康后向上抛出。

        Args:
            messages: 消息列表
            provider: 提供商名称，"default" 自动选择启用的提供商（带粘性缓存）
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数

        Returns:
            异步流式响应生成器（AsyncIterator[ChatResponse]）

        Raises:
            ConfigurationError: 当没有启用的提供商或提供商不存在时抛出
        """
        if provider == DEFAULT_PROVIDER:
            provider = self._resolve_default_provider("chat")
        if model == "default":
            model = None

        provider_instance = self.get_provider(provider)
        if not provider_instance:
            raise ConfigurationError(f"Provider not found: {provider}")

        stream = provider_instance.async_stream_chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        return self._track_async_stream(stream, provider, model, provider_instance)

    async def _track_async_stream(
        self,
        stream: AsyncIterator[ChatResponse],
        provider: str,
        model: Optional[str],
        provider_instance: ILLM,
    ) -> AsyncIterator[ChatResponse]:
        """包装异步流式生成器：迭代中收集 usage，结束时记录用量与健康状态

        不改变对外返回类型（仍是异步迭代器），逐块原样透传。

        Args:
            stream: 底层 provider 的异步流式响应迭代器
            provider: 实际解析出的提供商名称（不会是 "default"）
            model: 调用方传入的模型名称（可能为 None）
            provider_instance: 提供商实例（用于回退取默认模型名）

        Yields:
            ChatResponse: 原样透传的流式响应块
        """
        t0 = time.perf_counter()
        last_usage: Optional[UsageInfo] = None
        agg_model = ""
        try:
            async for chunk in stream:
                chunk_usage = getattr(chunk, "usage", None)
                if isinstance(chunk_usage, UsageInfo):
                    last_usage = chunk_usage
                chunk_model = getattr(chunk, "model", None)
                if isinstance(chunk_model, str) and chunk_model:
                    agg_model = chunk_model
                yield chunk
        except Exception as e:
            self._health[provider] = (False, str(e))
            raise

        duration_ms = (time.perf_counter() - t0) * 1000
        self._health[provider] = (True, None)
        # 与同步 stream_chat 一致：仅当末块携带 usage 时记录用量
        if last_usage is not None:
            actual_model = (agg_model or model
                            or getattr(provider_instance, "chat_model", "") or "")
            aggregated = ChatResponse(content="", model=actual_model, usage=last_usage)
            self._record_usage(
                response=aggregated,
                provider=provider,
                model=actual_model,
                is_stream=True,
                duration_ms=duration_ms,
            )

    async def async_embed(
        self,
        texts: Union[str, List[str]],
        provider: str = DEFAULT_PROVIDER,
        model: Optional[str] = None,
        **kwargs
    ) -> List[EmbeddingResponse]:
        """异步发送文本嵌入请求

        异步版本的嵌入接口。与同步 embed 一致：解析 "default" 走粘性缓存，
        并更新健康状态（嵌入响应不含 token usage，与同步路径一样不记录用量）。

        Args:
            texts: 单个文本或文本列表
            provider: 提供商名称，"default" 自动选择启用的提供商（带粘性缓存）
            model: 模型名称
            **kwargs: 其他参数

        Returns:
            List[EmbeddingResponse]: 嵌入响应列表

        Raises:
            ConfigurationError: 当没有启用的嵌入提供商或提供商不存在时抛出
        """
        if provider == DEFAULT_PROVIDER:
            provider = self._resolve_default_provider("embedding")
        if model == "default":
            model = None

        provider_instance = self.get_provider(provider)
        if not provider_instance:
            raise ConfigurationError(f"Provider not found: {provider}")

        try:
            result = await provider_instance.async_embed(
                texts=texts,
                model=model,
                **kwargs
            )
        except Exception as e:
            self._health[provider] = (False, str(e))
            raise
        self._health[provider] = (True, None)
        return result

    # ==================== 配置相关 ====================

    @property
    def config(self) -> LLMConfig:
        """获取 LLM 配置管理器

        Returns:
            LLMConfig: 配置管理器实例
        """
        return self._config

    @property
    def available_providers(self) -> List[str]:
        """获取所有支持的提供商类型

        Returns:
            List[str]: 支持的提供商类型列表
        """
        return list(PROVIDER_REGISTRY.keys())

    def close(self) -> None:
        """关闭所有提供商连接，释放资源

        遍历关闭所有提供商的 HTTP 会话，清理实例缓存。
        通常在应用程序退出时调用。
        """
        for provider in self._providers.values():
            provider.close()
        self._providers.clear()


# ==================== 模块级函数 ====================

def get_llm_provider() -> LLMProvider:
    """获取 LLM 提供商管理器的全局单例实例

    这是访问 LLM 功能的推荐入口点，保证全局只有一个实例。

    Returns:
        LLMProvider: LLM 提供商管理器单例实例

    Example:
        >>> from core.llm import get_llm_provider, Message
        >>> provider = get_llm_provider()
        >>> response = provider.chat([Message("user", "你好")])
    """
    return LLMProvider()