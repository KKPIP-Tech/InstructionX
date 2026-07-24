"""预设模型目录模块

该模块将各提供商实现类中的预设模型列表（CHAT_MODELS / EMBEDDING_MODELS /
VISION_MODELS 等类属性与 MODEL_DETAILS 详情）迁移为统一模型 schema 的
目录数据（见 core/llm/model_schema.py）。

每个条目按 normalize_model_entry 语义构造：
- group 使用来源分组的中文名（「对话模型」「嵌入模型」「视觉模型」
  「图像生成」「视频生成」「音频模型」「其他模型」）；
- capabilities 由 MODEL_DETAILS 的 support_function_calling（→ tools）
  与来源类别（视觉组 → vision、嵌入组 → embedding）推断；
- context_length 取 MODEL_DETAILS.context_length；
- description / max_output 作为额外键保留。

数据:
    PRESET_MODELS: preset_id -> 统一 schema 模型条目列表

注意:
    siliconflow / ollama / openai 不收录预设模型——这些厂商的模型列表
    通过 API 动态拉取（openai 历史默认配置中的 custom_models 属用户配置层，
    不属于目录层），故不在目录中维护。
"""

from typing import Any, Dict, List, Tuple

from ..model_schema import (
    CAPABILITY_EMBEDDING,
    CAPABILITY_TOOLS,
    CAPABILITY_VISION,
    normalize_model_entry,
)
from ..providers.glm import GLMProvider
from ..providers.minimax import MiniMaxProvider


# ==================== 来源分组中文名常量 ====================

# 文本对话模型分组名
MODEL_GROUP_CHAT = "对话模型"
# 向量嵌入模型分组名
MODEL_GROUP_EMBEDDING = "嵌入模型"
# 视觉理解模型分组名
MODEL_GROUP_VISION = "视觉模型"
# 图像生成模型分组名
MODEL_GROUP_IMAGE = "图像生成"
# 视频生成模型分组名
MODEL_GROUP_VIDEO = "视频生成"
# 音频（语音合成/识别）模型分组名
MODEL_GROUP_AUDIO = "音频模型"
# 其他模型分组名
MODEL_GROUP_OTHER = "其他模型"


# ==================== 目录构建 ====================

# 来源表条目类型：(模型 ID 列表, 分组名, 来源类别附加能力)
_SourceSpec = Tuple[List[str], str, Tuple[str, ...]]

# GLM 预设模型来源表（与 GLMProvider 的分组类属性一一对应）
_GLM_SOURCES: Tuple[_SourceSpec, ...] = (
    (GLMProvider.CHAT_MODELS, MODEL_GROUP_CHAT, ()),
    (GLMProvider.EMBEDDING_MODELS, MODEL_GROUP_EMBEDDING, (CAPABILITY_EMBEDDING,)),
    (GLMProvider.VISION_MODELS, MODEL_GROUP_VISION, (CAPABILITY_VISION,)),
    (GLMProvider.IMAGE_MODELS, MODEL_GROUP_IMAGE, ()),
    (GLMProvider.VIDEO_MODELS, MODEL_GROUP_VIDEO, ()),
    (GLMProvider.AUDIO_MODELS, MODEL_GROUP_AUDIO, ()),
    (GLMProvider.OTHER_MODELS, MODEL_GROUP_OTHER, ()),
)

# MiniMax 预设模型来源表（与 MiniMaxProvider 的分组类属性一一对应）
_MINIMAX_SOURCES: Tuple[_SourceSpec, ...] = (
    (MiniMaxProvider.CHAT_MODELS, MODEL_GROUP_CHAT, ()),
    (MiniMaxProvider.EMBEDDING_MODELS, MODEL_GROUP_EMBEDDING, (CAPABILITY_EMBEDDING,)),
)


def _build_group_entries(
    model_ids: List[str],
    group_name: str,
    category_capabilities: Tuple[str, ...],
    model_details: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """按来源分组构建统一 schema 的模型条目列表

    Args:
        model_ids: 该分组下的模型 ID 列表
        group_name: 分组中文名
        category_capabilities: 来源类别附加的能力（如视觉组附加 vision）
        model_details: 模型详情字典（context_length / support_function_calling /
            description / max_output）

    Returns:
        List[Dict[str, Any]]: 经 normalize_model_entry 规范化的条目列表
    """
    entries = []
    for model_id in model_ids:
        details = model_details.get(model_id, {})
        capabilities = list(category_capabilities)
        if details.get("support_function_calling"):
            capabilities.append(CAPABILITY_TOOLS)
        entry: Dict[str, Any] = {
            "id": model_id,
            "name": model_id,
            "group": group_name,
            "capabilities": capabilities,
            "context_length": details.get("context_length"),
        }
        # 详情中的描述与输出上限作为额外键保留
        if details.get("description"):
            entry["description"] = details["description"]
        if details.get("max_output") is not None:
            entry["max_output"] = details["max_output"]
        entries.append(normalize_model_entry(entry))
    return entries


def _collect_preset_models(
    sources: Tuple[_SourceSpec, ...],
    model_details: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """按来源表汇总一个预设的全部模型条目

    Args:
        sources: 来源表（模型 ID 列表、分组名、类别能力的三元组序列）
        model_details: 模型详情字典

    Returns:
        List[Dict[str, Any]]: 统一 schema 的模型条目列表
    """
    entries: List[Dict[str, Any]] = []
    for model_ids, group_name, category_capabilities in sources:
        entries.extend(
            _build_group_entries(model_ids, group_name, category_capabilities, model_details)
        )
    return entries


# 预设模型目录表：preset_id -> 统一 schema 模型条目列表
# siliconflow / ollama / openai 不收录：模型列表走 API 动态拉取，无目录级预设模型
PRESET_MODELS: Dict[str, List[Dict[str, Any]]] = {
    "glm": _collect_preset_models(_GLM_SOURCES, GLMProvider.MODEL_DETAILS),
    "minimax": _collect_preset_models(_MINIMAX_SOURCES, MiniMaxProvider.MODEL_DETAILS),
}
