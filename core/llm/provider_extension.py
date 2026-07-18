"""LLM Provider 扩展系统 - 灵活的 Provider 配置和注册机制

该模块提供更灵活的 Provider 扩展能力，支持：
    - 自定义 Provider 类型注册
    - 动态配置模式（JSON Schema 风格）
    - Provider 模板和预设
    - 向后兼容现有插件接口

Classes:
    ProviderSchema: Provider 配置模式定义
    ProviderTemplate: Provider 模板定义
    ExtendedProviderRegistry: 扩展的 Provider 注册表

使用示例:
    >>> from core.llm.provider_extension import (
    ...     register_custom_provider,
    ...     ProviderSchema,
    ...     ProviderField
    ... )
    >>>
    >>> # 定义自定义 Provider 模式
    >>> schema = ProviderSchema(
    ...     type_id="my_custom",
    ...     name="My Custom Provider",
    ...     description="自定义 Provider 示例",
    ...     fields=[
    ...         ProviderField("api_key", "API 密钥", required=True, secret=True),
    ...         ProviderField("base_url", "API 地址", default="https://api.example.com"),
    ...         ProviderField("timeout", "超时时间", field_type="int", default=60),
    ...     ]
    ... )
    >>>
    >>> # 注册自定义 Provider
    >>> register_custom_provider(schema, MyCustomProvider)
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Type, Callable
import json


@dataclass
class ProviderField:
    """Provider 配置字段定义

    Attributes:
        name: 字段名称（英文标识符）
        label: 显示标签（中文）
        field_type: 字段类型（str/int/float/bool/list/dict）
        required: 是否必需
        secret: 是否为敏感信息（如 API 密钥）
        default: 默认值
        description: 字段描述
        placeholder: 输入占位符
        options: 选项列表（用于枚举类型）
    """
    name: str
    label: str
    field_type: str = "str"  # str/int/float/bool/list/dict
    required: bool = False
    secret: bool = False
    default: Any = None
    description: str = ""
    placeholder: str = ""
    options: List[Any] = field(default_factory=list)


@dataclass
class ProviderSchema:
    """Provider 配置模式定义

    Attributes:
        type_id: Provider 类型标识符（如 "openai", "custom"）
        name: 显示名称
        description: 描述
        icon: 图标路径（可选）
        fields: 配置字段列表
        models_endpoint: 模型列表端点（可选，用于自动获取模型）
        capabilities: 支持的能力列表（chat/embedding/vision/tools 等）
    """
    type_id: str
    name: str
    description: str = ""
    icon: str = ""
    fields: List[ProviderField] = field(default_factory=list)
    models_endpoint: str = ""
    capabilities: List[str] = field(default_factory=lambda: ["chat"])

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "type_id": self.type_id,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "fields": [
                {
                    "name": f.name,
                    "label": f.label,
                    "field_type": f.field_type,
                    "required": f.required,
                    "secret": f.secret,
                    "default": f.default,
                    "description": f.description,
                    "placeholder": f.placeholder,
                    "options": f.options,
                }
                for f in self.fields
            ],
            "models_endpoint": self.models_endpoint,
            "capabilities": self.capabilities,
        }


@dataclass
class ProviderTemplate:
    """Provider 模板定义

    Attributes:
        template_id: 模板标识符
        name: 模板名称
        provider_type: 基础 Provider 类型
        preset_config: 预设配置
        description: 模板描述
    """
    template_id: str
    name: str
    provider_type: str
    preset_config: Dict[str, Any] = field(default_factory=dict)
    description: str = ""


class ExtendedProviderRegistry:
    """扩展的 Provider 注册表

    支持：
        - 动态 Provider 类型注册
        - 自定义配置模式
        - Provider 模板管理
        - 向后兼容现有 PROVIDER_REGISTRY
    """

    def __init__(self):
        self._schemas: Dict[str, ProviderSchema] = {}
        self._templates: Dict[str, ProviderTemplate] = {}
        self._custom_classes: Dict[str, Type] = {}
        self._initialized = False

    def register_schema(self, schema: ProviderSchema) -> None:
        """注册 Provider 配置模式

        Args:
            schema: Provider 配置模式
        """
        self._schemas[schema.type_id] = schema

    def register_template(self, template: ProviderTemplate) -> None:
        """注册 Provider 模板

        Args:
            template: Provider 模板
        """
        self._templates[template.template_id] = template

    def register_custom_class(self, type_id: str, provider_class: Type) -> None:
        """注册自定义 Provider 类

        Args:
            type_id: Provider 类型标识符
            provider_class: Provider 类
        """
        self._custom_classes[type_id] = provider_class

    def get_schema(self, type_id: str) -> Optional[ProviderSchema]:
        """获取 Provider 配置模式

        Args:
            type_id: Provider 类型标识符

        Returns:
            ProviderSchema 实例，如果不存在返回 None
        """
        return self._schemas.get(type_id)

    def get_all_schemas(self) -> List[ProviderSchema]:
        """获取所有 Provider 配置模式

        Returns:
            ProviderSchema 列表
        """
        return list(self._schemas.values())

    def get_template(self, template_id: str) -> Optional[ProviderTemplate]:
        """获取 Provider 模板

        Args:
            template_id: 模板标识符

        Returns:
            ProviderTemplate 实例，如果不存在返回 None
        """
        return self._templates.get(template_id)

    def get_all_templates(self) -> List[ProviderTemplate]:
        """获取所有 Provider 模板

        Returns:
            ProviderTemplate 列表
        """
        return list(self._templates.values())

    def get_custom_class(self, type_id: str) -> Optional[Type]:
        """获取自定义 Provider 类

        Args:
            type_id: Provider 类型标识符

        Returns:
            Provider 类，如果不存在返回 None
        """
        return self._custom_classes.get(type_id)

    def create_provider(self, type_id: str, config: Dict[str, Any], **kwargs):
        """创建 Provider 实例

        优先使用自定义 Provider 类，否则使用标准 Provider 类。

        Args:
            type_id: Provider 类型标识符
            config: 配置字典
            **kwargs: 额外参数

        Returns:
            Provider 实例

        Raises:
            ValueError: 如果 Provider 类型不存在
        """
        # 首先尝试自定义类
        if type_id in self._custom_classes:
            return self._custom_classes[type_id](config, **kwargs)

        # 然后尝试标准注册表
        from .providers import get_provider_class
        provider_class = get_provider_class(type_id)
        if provider_class:
            return provider_class(config, **kwargs)

        raise ValueError(f"未知的 Provider 类型: {type_id}")

    def validate_config(self, type_id: str, config: Dict[str, Any]) -> tuple[bool, str]:
        """验证 Provider 配置

        Args:
            type_id: Provider 类型标识符
            config: 配置字典

        Returns:
            (是否有效, 错误信息)
        """
        schema = self.get_schema(type_id)
        if not schema:
            return True, ""

        errors = []
        for field_def in schema.fields:
            value = config.get(field_def.name)
            if field_def.required and not value:
                errors.append(f"缺少必需字段: {field_def.label}")
            elif value and field_def.field_type == "int":
                try:
                    int(value)
                except (ValueError, TypeError):
                    errors.append(f"字段 {field_def.label} 必须是整数")

        return len(errors) == 0, "; ".join(errors)

    def apply_schema_defaults(self, type_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """应用模式默认值到配置

        Args:
            type_id: Provider 类型标识符
            config: 原始配置

        Returns:
            应用默认值后的配置
        """
        schema = self.get_schema(type_id)
        if not schema:
            return config

        result = dict(config)
        for field_def in schema.fields:
            if field_def.name not in result or result[field_def.name] is None:
                result[field_def.name] = field_def.default

        return result

    def _init_builtin_schemas(self) -> None:
        """初始化内置 Provider 模式"""
        if self._initialized:
            return

        # OpenAI 兼容 Provider
        openai_schema = ProviderSchema(
            type_id="openai",
            name="OpenAI",
            description="OpenAI 兼容 API",
            fields=[
                ProviderField("api_key", "API 密钥", required=True, secret=True,
                            placeholder="sk-..."),
                ProviderField("base_url", "API 地址", default="https://api.openai.com/v1",
                            placeholder="https://api.openai.com/v1"),
                ProviderField("timeout", "超时时间（秒）", field_type="int", default=60),
                ProviderField("organization", "组织 ID", required=False),
            ],
            models_endpoint="/models",
            capabilities=["chat", "embedding", "vision", "tools"],
        )
        self.register_schema(openai_schema)

        # 自定义 OpenAI 兼容 Provider
        custom_openai_schema = ProviderSchema(
            type_id="custom_openai",
            name="自定义 OpenAI 兼容",
            description="自定义 OpenAI 兼容 API 端点",
            fields=[
                ProviderField("api_key", "API 密钥", required=True, secret=True),
                ProviderField("base_url", "API 地址", required=True,
                            placeholder="https://your-api.com/v1"),
                ProviderField("timeout", "超时时间（秒）", field_type="int", default=60),
                ProviderField("custom_models", "自定义模型", field_type="list",
                            description="JSON 格式的自定义模型列表"),
            ],
            models_endpoint="/models",
            capabilities=["chat", "embedding"],
        )
        self.register_schema(custom_openai_schema)

        self._initialized = True


# ==================== 全局注册表实例 ====================

_extended_registry: Optional[ExtendedProviderRegistry] = None


def get_extended_registry() -> ExtendedProviderRegistry:
    """获取扩展 Provider 注册表实例

    Returns:
        ExtendedProviderRegistry 实例
    """
    global _extended_registry
    if _extended_registry is None:
        _extended_registry = ExtendedProviderRegistry()
        _extended_registry._init_builtin_schemas()
    return _extended_registry


def register_custom_provider(schema: ProviderSchema, provider_class: Type) -> None:
    """注册自定义 Provider

    Args:
        schema: Provider 配置模式
        provider_class: Provider 类
    """
    registry = get_extended_registry()
    registry.register_schema(schema)
    registry.register_custom_class(schema.type_id, provider_class)


def register_provider_template(template: ProviderTemplate) -> None:
    """注册 Provider 模板

    Args:
        template: Provider 模板
    """
    registry = get_extended_registry()
    registry.register_template(template)


def get_all_provider_schemas() -> List[ProviderSchema]:
    """获取所有 Provider 配置模式

    Returns:
        ProviderSchema 列表
    """
    return get_extended_registry().get_all_schemas()


def get_all_provider_templates() -> List[ProviderTemplate]:
    """获取所有 Provider 模板

    Returns:
        ProviderTemplate 列表
    """
    return get_extended_registry().get_all_templates()


def create_provider_instance(type_id: str, config: Dict[str, Any], **kwargs):
    """创建 Provider 实例

    Args:
        type_id: Provider 类型标识符
        config: 配置字典
        **kwargs: 额外参数

    Returns:
        Provider 实例
    """
    return get_extended_registry().create_provider(type_id, config, **kwargs)


__all__ = [
    "ProviderField",
    "ProviderSchema",
    "ProviderTemplate",
    "ExtendedProviderRegistry",
    "get_extended_registry",
    "register_custom_provider",
    "register_provider_template",
    "get_all_provider_schemas",
    "get_all_provider_templates",
    "create_provider_instance",
]
