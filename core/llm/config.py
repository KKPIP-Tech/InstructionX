"""LLM 配置模块 - 提供商实例配置管理（schema v2）

该模块负责管理 LLM 提供商实例的配置信息，支持从 JSON 文件加载和保存配置。
配置中的每个 Provider 是一个**实例**，通过 ``preset_id`` 关联
``core/llm/catalog/`` 中的预设目录（``preset_id`` 为 None 表示完全自定义，
固定使用 ``openai-compatible`` 兜底适配器）。

配置结构:
    - config/llm_providers.json: 提供商实例配置（顶层含 ``version`` 字段，
      当前版本为 2；无 ``version`` 键的历史文件按 v1 处理并自动迁移）
    - config/llm_models_cache.json: 模型列表缓存（键为实例 id）

Classes:
    ProviderConfig: 单个提供商实例的配置类
    LLMConfig: 提供商配置管理类（单例，支持变更订阅）

使用示例:
    >>> from core.llm.config import get_llm_config
    >>> config = get_llm_config()
    >>> provider = config.get_provider("glm")
    >>> print(provider.chat_model)
"""

import json
import logging
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Any, Optional, List

from .exceptions import ConfigurationError
from .model_schema import normalize_model_entry
from .secure_keys import encode_secret, decode_secret

logger = logging.getLogger(__name__)


# ==================== 配置路径常量 ====================

# 配置目录: core/llm/config.py -> 项目根目录/config
CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"

# 提供商配置文件路径
CONFIG_FILE = CONFIG_DIR / "llm_providers.json"

# 模型缓存文件路径
MODELS_CACHE_FILE = CONFIG_DIR / "llm_models_cache.json"

# ==================== 配置版本与事件常量 ====================

# 当前配置文件 schema 版本（顶层 version 字段）
CONFIG_SCHEMA_VERSION = 2

# 配置变更事件：providers 集合或任一实例配置发生变化
EVENT_PROVIDERS_CHANGED = "providers_changed"

# 迁移备份文件的时间戳格式（与 data 层迁移备份命名风格一致）
_BACKUP_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%S.%f"

# 变更订阅回调签名：callback(event: str, provider_name: Optional[str])
ConfigChangeCallback = Callable[[str, Optional[str]], None]


def _atomic_write_json(file_path: Path, data: Dict[str, Any]) -> None:
    """原子写入 JSON 文件（同目录临时文件 + os.replace）

    先写入同目录的 .tmp 临时文件，再用 os.replace 原子替换目标文件，
    避免写入中途崩溃/断电导致目标文件损坏（半写状态）。

    Args:
        file_path: 目标文件路径
        data: 要序列化的字典数据

    Raises:
        OSError: 写入或替换失败时抛出（临时文件会被尽力清理）
    """
    temp_file = file_path.with_name(file_path.name + ".tmp")
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(temp_file, file_path)
    except Exception as e:
        # 失败时清理残留临时文件，避免污染配置目录
        try:
            if temp_file.exists():
                temp_file.unlink()
        except OSError as cleanup_err:
            logger.warning("清理临时文件失败: %s (%s)", temp_file, cleanup_err)
        logger.error("原子写入配置文件失败: %s (%s)", file_path, e)
        raise


class ProviderConfig:
    """单个 LLM 提供商实例的配置类

    封装单个提供商实例的所有配置信息，包括 API 密钥、端 URL、模型名称等。
    实例通过 ``preset_id`` 关联预设目录（None 表示完全自定义），
    通过 ``adapter`` 指定协议适配器家族键。

    Attributes:
        preset_id: 关联的预设目录 ID（None = 完全自定义）
        name: 实例显示名称
        adapter: 适配器家族键（对应 PROVIDER_REGISTRY 的键）
        api_key: API 密钥（内存中始终为明文）
        base_url: API 基础 URL（空串表示使用目录默认）
        chat_model: 聊天模型名称
        embedding_model: 嵌入模型名称
        enabled_chat: 是否启用聊天功能
        enabled_embedding: 是否启用嵌入功能
        support_vision: 是否支持视觉（多模态）
        order: 列表排序权重（拖拽排序持久化）
        cache_fields: 缓存字段配置
        extra: 额外的配置参数（含 custom_models 等未列入一等字段的键）
    """

    def __init__(
        self,
        name: str,
        api_key: str = "",
        base_url: str = "",
        chat_model: str = "",
        embedding_model: str = "",
        enabled_chat: bool = True,
        enabled_embedding: bool = False,
        support_vision: bool = True,
        cache_fields: Optional[Dict[str, Any]] = None,
        preset_id: Optional[str] = None,
        adapter: Optional[str] = None,
        order: int = 0,
        **kwargs
    ):
        """初始化提供商实例配置

        Args:
            name: 实例显示名称
            api_key: API 密钥（可选）
            base_url: API 基础 URL（可选）
            chat_model: 聊天模型名称（可选）
            embedding_model: 嵌入模型名称（可选）
            enabled_chat: 是否启用聊天功能，默认 True
            enabled_embedding: 是否启用嵌入功能，默认 False
            support_vision: 是否支持视觉（多模态），默认 True
            cache_fields: 缓存字段配置（可选）
            preset_id: 关联的预设目录 ID，None 表示完全自定义
            adapter: 适配器家族键（对应 PROVIDER_REGISTRY 的键）
            order: 列表排序权重，默认 0
            **kwargs: 额外的配置参数（存入 extra）
        """
        self.preset_id = preset_id
        self.name = name
        self.adapter = adapter or ""
        self.api_key = api_key
        self.base_url = base_url
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        self.enabled_chat = enabled_chat
        self.enabled_embedding = enabled_embedding
        self.support_vision = support_vision
        self.order = order
        self.cache_fields = cache_fields or {}
        self.extra = kwargs

    def to_dict(self) -> Dict[str, Any]:
        """将配置转换为字典

        输出 v2 字段集（preset_id/adapter/order 等）。

        Returns:
            Dict[str, Any]: 包含所有配置项的字典
        """
        return {
            "preset_id": self.preset_id,
            "name": self.name,
            "adapter": self.adapter,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "chat_model": self.chat_model,
            "embedding_model": self.embedding_model,
            "enabled_chat": self.enabled_chat,
            "enabled_embedding": self.enabled_embedding,
            "support_vision": self.support_vision,
            "order": self.order,
            "cache_fields": self.cache_fields,
            **self.extra
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProviderConfig":
        """从字典创建配置对象

        将字典数据反序列化为 ProviderConfig 对象（输入应为 v2 条目；
        v1 条目由 LLMConfig 迁移流程先行转换，其中残留的 ``provider_type``
        键在此静默丢弃）。``custom_models`` 列表逐项经
        normalize_model_entry() 规范化（含历史布尔能力键转换与
        per_1k→per_1m 定价键迁移）。未知字段会被保存到 extra 属性中。

        Args:
            data: 包含配置信息的字典

        Returns:
            ProviderConfig: 配置对象实例
        """
        data = dict(data)
        # custom_models 逐项规范化为统一模型 schema（幂等，v2 数据透传）
        custom_models = data.get("custom_models")
        if isinstance(custom_models, list):
            data["custom_models"] = [
                normalize_model_entry(m) if isinstance(m, dict) else m
                for m in custom_models
            ]

        # v1 残留的 provider_type 键不再消费，丢弃避免落入 extra 并随保存回写
        data.pop("provider_type", None)
        # 已知的标准字段
        known_fields = {
            "preset_id", "name", "adapter", "order",
            "api_key", "base_url", "chat_model", "embedding_model",
            "enabled_chat", "enabled_embedding", "support_vision",
            "cache_fields"
        }
        # 将未知字段保存到 extra 中
        extra = {k: v for k, v in data.items() if k not in known_fields}
        return cls(
            name=data.get("name", ""),
            api_key=data.get("api_key", ""),
            base_url=data.get("base_url", ""),
            chat_model=data.get("chat_model", ""),
            embedding_model=data.get("embedding_model", ""),
            enabled_chat=data.get("enabled_chat", True),
            enabled_embedding=data.get("enabled_embedding", False),
            support_vision=data.get("support_vision", True),
            cache_fields=data.get("cache_fields"),
            preset_id=data.get("preset_id"),
            adapter=data.get("adapter"),
            order=data.get("order", 0),
            **extra
        )


class LLMConfig:
    """LLM 提供商配置管理类（单例）

    负责加载、保存和管理所有 LLM 提供商实例的配置。
    全进程共享同一份内存配置，变更时通过订阅回调通知消费方，
    并以 ``version`` 计数供消费方惰性刷新比对。

    Features:
        - 从 JSON 文件加载提供商配置（v1 自动迁移为 v2 并备份原文件）
        - 单例（双重检查锁），get_llm_config() 访问器
        - 变更订阅：subscribe/unsubscribe，事件 EVENT_PROVIDERS_CHANGED
        - 获取/设置单个提供商配置
        - 获取已启用的提供商列表
        - 模型列表缓存管理
    """

    _instance: Optional["LLMConfig"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "LLMConfig":
        """单例构造（双重检查锁）

        Returns:
            LLMConfig: 全进程唯一实例
        """
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化 LLM 配置管理器

        首次构造时自动调用 _load_config() 加载配置；
        配置文件不存在时创建空 providers 的 v2 文件
        （目录即默认值，不再自动补齐内置提供商）。
        重复构造（单例）直接返回，不重复加载。
        """
        if getattr(self, "_initialized", False):
            return
        self._providers: Dict[str, ProviderConfig] = {}
        self._subscribers: List[ConfigChangeCallback] = []
        self._version: int = 0
        self._load_config()
        self._initialized = True

    # ==================== 单例与变更通知 ====================

    @property
    def version(self) -> int:
        """配置变更计数（只读）

        每次配置变更（add/remove/save）递增 1，
        供消费方（如 LLMProvider）比对并惰性刷新。

        Returns:
            int: 变更计数
        """
        return self._version

    def subscribe(self, callback: ConfigChangeCallback) -> None:
        """订阅配置变更通知

        Args:
            callback: 变更回调，签名 callback(event, provider_name)；
                event 取值为 EVENT_PROVIDERS_CHANGED，provider_name
                为变更涉及的实例 id（批量保存时为 None）
        """
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: ConfigChangeCallback) -> None:
        """取消订阅配置变更通知

        Args:
            callback: 此前订阅的回调；未订阅时静默忽略
        """
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def _notify(self, provider_name: Optional[str] = None) -> None:
        """触发变更通知（version +1 并逐个回调）

        订阅回调的异常被捕获并记 WARNING 日志，不影响主流程与其余回调。

        Args:
            provider_name: 变更涉及的实例 id，批量保存时为 None
        """
        self._version += 1
        for callback in list(self._subscribers):
            try:
                callback(EVENT_PROVIDERS_CHANGED, provider_name)
            except RuntimeError as e:
                # 回调所属 Qt 对象已销毁（如关闭的对话框面板）：自动退订，
                # 避免悬挂回调在后续每次落盘时反复报错。
                # 注意：日志不得记录 callback 本身——对已删除的 Qt 对象
                # 执行 repr/str 会再次抛出 RuntimeError。
                self._subscribers = [
                    cb for cb in self._subscribers if cb is not callback]
                logger.warning("配置变更订阅回调所属对象已销毁，已自动退订: %s", e)
            except Exception as e:
                logger.warning("配置变更订阅回调执行失败，已忽略: %s", e)

    # ==================== 配置加载与迁移 ====================

    def _load_config(self) -> None:
        """从 JSON 文件加载配置

        读取 config/llm_providers.json 文件，解析并加载所有提供商配置。
        文件不存在时创建空 providers 的 v2 文件；顶层无 version 键的
        历史文件按 v1 处理，先备份再迁移为 v2 后加载。

        Raises:
            ConfigurationError: 配置文件格式错误时抛出
        """
        # 如果配置文件不存在，创建空的 v2 配置文件
        if not CONFIG_FILE.exists():
            self._create_default_config()
            return

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise ConfigurationError(f"Failed to load config: {e}") from e

        # 顶层无 version 键即 v1：备份原文件后迁移为 v2
        if "version" not in data:
            data = self._migrate_v1_to_v2(data)

        providers = data.get("providers", {})
        for name, config_data in providers.items():
            # 落盘的 api_key 可能是 Base64 编码(b64: 前缀),加载时解码回明文
            config_data = dict(config_data)
            config_data["api_key"] = decode_secret(config_data.get("api_key", ""))
            self._providers[name] = ProviderConfig.from_dict(config_data)

    def _migrate_v1_to_v2(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """将 v1 配置数据迁移为 v2 schema（先备份原文件，再原子写回）

        迁移规则：provider_type → preset_id 同名映射；adapter = provider_type；
        order 按原顺序 0..n；迁移后条目不再保留 provider_type 键；
        custom_models 逐项规范化（在 from_dict 中完成，此处仅做条目级
        字段映射，api_key 保持落盘编码原样）。

        Args:
            data: v1 配置数据（{"providers": {...}}）

        Returns:
            Dict[str, Any]: 迁移后的 v2 配置数据
        """
        backup_path = self._backup_config_file()
        providers = data.get("providers", {})
        migrated: Dict[str, Any] = {}
        for index, (name, entry) in enumerate(providers.items()):
            migrated[name] = self._migrate_v1_entry(entry, index)
        new_data = {"version": CONFIG_SCHEMA_VERSION, "providers": migrated}
        _atomic_write_json(CONFIG_FILE, new_data)
        logger.info(
            "LLM 提供商配置已从 v1 迁移到 v2（%d 个实例），原文件备份: %s",
            len(migrated), backup_path
        )
        return new_data

    @staticmethod
    def _migrate_v1_entry(entry: Dict[str, Any], order: int) -> Dict[str, Any]:
        """迁移单个 v1 实例条目为 v2 字段集

        Args:
            entry: v1 实例条目字典
            order: 按原顺序分配的排序权重

        Returns:
            Dict[str, Any]: v2 实例条目字典
        """
        entry = dict(entry)
        provider_type = entry.pop("provider_type", "")
        # 实例 id 保持旧键名；预设默认实例 id == preset_id（向后兼容）
        entry["preset_id"] = provider_type or None
        entry["adapter"] = provider_type
        entry["order"] = order
        return entry

    @staticmethod
    def _backup_config_file() -> Path:
        """备份当前配置文件为带时间戳的 .bak 文件

        命名风格与 data 层迁移备份一致：
        ``llm_providers.migrated-<时间戳>.bak``。

        Returns:
            Path: 备份文件路径
        """
        timestamp = datetime.now(timezone.utc).strftime(_BACKUP_TIMESTAMP_FORMAT)
        backup_path = CONFIG_FILE.with_name(
            f"{CONFIG_FILE.stem}.migrated-{timestamp}.bak"
        )
        shutil.copy2(CONFIG_FILE, backup_path)
        return backup_path

    def _create_default_config(self) -> None:
        """创建初始配置文件（空 providers 的 v2 文件）

        目录即默认值：首次运行不再写入内置提供商模板，
        用户配置只存用户显式创建/修改的实例。
        """
        # 确保配置目录存在
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(CONFIG_FILE, {
            "version": CONFIG_SCHEMA_VERSION,
            "providers": {}
        })

    # ==================== 配置保存 ====================

    def save_config(self) -> None:
        """保存配置到 JSON 文件

        将当前内存中的所有提供商配置序列化为 v2 schema 并保存到配置文件，
        随后触发变更通知（version +1）。
        """
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        data: Dict[str, Any] = {
            "version": CONFIG_SCHEMA_VERSION,
            "providers": {}
        }
        for name, config in self._providers.items():
            provider_dict = config.to_dict()
            # api_key 落盘前做 Base64 编码(仅为编码非加密,内存中始终保持明文)
            provider_dict["api_key"] = encode_secret(provider_dict.get("api_key", ""))
            data["providers"][name] = provider_dict

        _atomic_write_json(CONFIG_FILE, data)
        self._notify(provider_name=None)

    # ==================== 实例查询与增删 ====================

    def get_provider(self, name: str) -> Optional[ProviderConfig]:
        """获取指定提供商配置

        Args:
            name: 提供商实例 id（键名）

        Returns:
            Optional[ProviderConfig]: 提供商配置对象，如果不存在返回 None
        """
        return self._providers.get(name)

    def get_all_providers(self) -> Dict[str, ProviderConfig]:
        """获取所有提供商配置

        Returns:
            Dict[str, ProviderConfig]: 提供商实例 id 到配置对象的映射字典
        """
        return self._providers.copy()

    def get_enabled_providers(self, feature: str = "chat") -> Dict[str, ProviderConfig]:
        """获取已启用的提供商列表

        根据功能类型筛选已启用的提供商。

        Args:
            feature: 功能类型，"chat" 或 "embedding"

        Returns:
            Dict[str, ProviderConfig]: 已启用的提供商映射字典
        """
        result = {}
        for name, config in self._providers.items():
            if feature == "chat" and config.enabled_chat:
                result[name] = config
            elif feature == "embedding" and config.enabled_embedding:
                result[name] = config
        return result

    def add_provider(self, name: str, config: ProviderConfig) -> None:
        """添加或更新提供商配置

        写入内存后立即落盘，并随保存触发变更通知。

        Args:
            name: 提供商实例 id
            config: 提供商配置对象
        """
        self._providers[name] = config
        self.save_config()

    def remove_provider(self, name: str) -> bool:
        """移除提供商配置

        移除后立即落盘（目录即默认值，移除的实例不会在下次加载时复活），
        并随保存触发变更通知。

        Args:
            name: 提供商实例 id

        Returns:
            bool: 是否成功移除
        """
        if name in self._providers:
            del self._providers[name]
            self.save_config()
            return True
        return False

    @property
    def config_file_path(self) -> Path:
        """获取配置文件路径

        Returns:
            Path: 配置文件路径对象
        """
        return CONFIG_FILE

    # ==================== 模型缓存 ====================

    def save_models_cache(self, provider_name: str, models: List[Dict[str, Any]]) -> None:
        """保存模型列表到缓存文件

        将指定提供商实例的模型列表缓存到本地文件，减少 API 调用频率。
        缓存键为实例 id。

        Args:
            provider_name: 提供商实例 id
            models: 模型信息列表
        """
        cache = self._load_models_cache()
        cache[provider_name] = models
        self._save_models_cache(cache)

    def load_models_cache(self, provider_name: str) -> Optional[List[Dict[str, Any]]]:
        """从缓存加载模型列表

        读取端兼容两种格式：TTL 信封 ``{"timestamp", "models"}`` 与
        纯 list 旧格式，原样返回由调用方解释。

        Args:
            provider_name: 提供商实例 id

        Returns:
            Optional[List[Dict[str, Any]]]: 模型列表（或 TTL 信封），
                如果不存在返回 None
        """
        cache = self._load_models_cache()
        return cache.get(provider_name)

    def _load_models_cache(self) -> Dict[str, Any]:
        """加载模型缓存文件

        Returns:
            Dict[str, Any]: 缓存数据字典
        """
        if not MODELS_CACHE_FILE.exists():
            return {}

        try:
            with open(MODELS_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("加载模型缓存文件失败，返回空缓存: %s (%s)", MODELS_CACHE_FILE, e)
            return {}

    def _save_models_cache(self, cache: Dict[str, Any]) -> None:
        """保存模型缓存文件

        Args:
            cache: 缓存数据字典
        """
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(MODELS_CACHE_FILE, cache)


def get_llm_config() -> LLMConfig:
    """获取 LLMConfig 单例访问器

    Returns:
        LLMConfig: 全进程唯一的配置管理实例
    """
    return LLMConfig()
