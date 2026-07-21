"""统一模型条目 schema 模块

该模块定义 LLM 模型条目的统一数据 schema，并提供历史 schema 规范化、
能力互斥计算、模型分组推断与分组聚合等纯数据工具函数。

模型条目统一 schema（dict）::

    {
        "id": str,                          # 必填，模型唯一标识
        "name": str,                        # 显示名，缺省取 id
        "group": str,                       # 分组名，空串由 models_to_groups 归入「未分组」
        "capabilities": List[str],          # 能力闭集，见 ALL_CAPABILITIES
        "context_length": Optional[int],    # 上下文窗口长度
        "support_streaming": bool,          # 是否支持流式输出，默认 True
        "currency": str,                    # 定价币种符号（"$"/"¥"/"€"），默认 "$"
        "input_price_per_1m": Optional[float],   # 输入定价（每百万 tokens）
        "output_price_per_1m": Optional[float],  # 输出定价（每百万 tokens）
    }

历史兼容:
    - 模板式 schema（support_chat/support_vision/support_function_calling/
      support_embedding 布尔键）在 normalize_model_entry 中转换为 capabilities；
    - 历史定价键 input_price_per_1k / output_price_per_1k（每千 tokens）
      自动迁移为 per_1m 键（×1000）；
    - 未知额外键（如 description、max_output）原样保留。

三路合并:
    merge_model_entries 将目录预设模型、API 拉取/缓存模型与
    custom_models 用户覆写三路来源按 id 合并为统一 schema 列表，
    供设置界面展示模型全集（详见函数 docstring）。
"""

from typing import Any, Dict, List, Optional, Tuple


# ==================== 能力闭集常量 ====================

# 视觉（多模态图像理解）
CAPABILITY_VISION = "vision"
# 联网搜索
CAPABILITY_WEB_SEARCH = "web"
# 推理（深度思考）
CAPABILITY_REASONING = "reasoning"
# 工具调用（function calling）
CAPABILITY_TOOLS = "tools"
# 嵌入（向量化）
CAPABILITY_EMBEDDING = "embedding"
# 重排序
CAPABILITY_RERANK = "rerank"

# 能力闭集：所有合法能力值（同时作为展示顺序）
ALL_CAPABILITIES: Tuple[str, ...] = (
    CAPABILITY_VISION,
    CAPABILITY_WEB_SEARCH,
    CAPABILITY_REASONING,
    CAPABILITY_TOOLS,
    CAPABILITY_EMBEDDING,
    CAPABILITY_RERANK,
)

# 能力值 → 中文标签
CAPABILITY_LABELS: Dict[str, str] = {
    CAPABILITY_VISION: "视觉",
    CAPABILITY_WEB_SEARCH: "联网搜索",
    CAPABILITY_REASONING: "推理",
    CAPABILITY_TOOLS: "工具调用",
    CAPABILITY_EMBEDDING: "嵌入",
    CAPABILITY_RERANK: "重排序",
}

# ==================== 能力互斥规则 ====================

# 互斥能力组：同一组内任一能力被选中时，其余全部能力不可用
# （嵌入/重排序模型不兼具对话类能力，且二者彼此互斥）
MUTUALLY_EXCLUSIVE_CAPABILITY_GROUPS: Tuple[frozenset, ...] = (
    frozenset({CAPABILITY_EMBEDDING, CAPABILITY_RERANK}),
)

# ==================== 分组常量 ====================

# 空组名条目的归组名
GROUP_UNGROUPED = "未分组"
# 关键字推断未命中时的归组名
GROUP_OTHER = "其他"

# ==================== 历史 schema 迁移常量 ====================

# 历史模板式布尔能力键 → 统一能力映射（support_chat 不映射为能力，仅删除）
_LEGACY_BOOL_CAPABILITY_MAP: Dict[str, str] = {
    "support_vision": CAPABILITY_VISION,
    "support_function_calling": CAPABILITY_TOOLS,
    "support_embedding": CAPABILITY_EMBEDDING,
}

# 需要删除的历史模板式布尔键全集
_LEGACY_BOOL_KEYS: Tuple[str, ...] = (
    "support_chat",
    "support_vision",
    "support_function_calling",
    "support_embedding",
)

# 历史定价键迁移映射：旧键（每千 tokens） -> 新键（每百万 tokens）
_PRICE_KEY_MIGRATION: Tuple[Tuple[str, str], ...] = (
    ("input_price_per_1k", "input_price_per_1m"),
    ("output_price_per_1k", "output_price_per_1m"),
)

# 每千 tokens 定价 → 每百万 tokens 定价的换算系数
_PRICE_PER_1K_TO_1M_FACTOR = 1000

# 默认定价币种符号
DEFAULT_CURRENCY = "$"

# ==================== 模型分组推断常量 ====================

# 模型 ID 关键字 → 系列分组名（按声明顺序匹配，先命中优先）
_MODEL_GROUP_KEYWORDS: Dict[str, str] = {
    "kimi": "Kimi K2",
    "qwen": "Qwen",
    "deepseek": "deepseek-ai",
    "moonshot": "moonshotai",
    "glm": "GLM",
    "minimax": "MiniMax",
    "gpt": "GPT",
    "claude": "Claude",
    "llama": "Llama",
}

# 模型 ID 路径分隔符（如 "Pro/deepseek-ai/DeepSeek-V3" 取首段作为分组）
_MODEL_ID_PATH_SEPARATOR = "/"


# ==================== 能力互斥计算 ====================

def get_disabled_capabilities(selected: List[str]) -> List[str]:
    """根据已选能力计算应禁用的能力列表

    互斥规则：已选能力命中任一互斥组（如 embedding/rerank）时，
    除已选中的互斥组能力外，其余全部能力均不可用。

    Args:
        selected: 当前已选中的能力列表

    Returns:
        List[str]: 应禁用的能力列表，按 ALL_CAPABILITIES 声明顺序排列
    """
    selected_set = set(selected)
    disabled = set()
    for group in MUTUALLY_EXCLUSIVE_CAPABILITY_GROUPS:
        hit = group & selected_set
        if hit:
            disabled |= set(ALL_CAPABILITIES) - hit
    return [cap for cap in ALL_CAPABILITIES if cap in disabled]


# ==================== 条目规范化 ====================

def _migrate_price_keys(data: Dict[str, Any]) -> Dict[str, Any]:
    """将历史定价键 per_1k 迁移为 per_1m（×1000）

    仅当 per_1m 键不存在时执行迁移；若两者并存，以 per_1m 为准并删除
    per_1k 键。

    注意：本函数面向「用户配置中的 custom_models」数据（历史上 per_1k 键
    确实表示每千 tokens 定价）。模型缓存文件中的 per_1k 键值实际已是
    per_1m 语义，由 ModelInfo.from_dict 原样读取，不经过本函数。

    Args:
        data: 原始条目字典（不会被修改）

    Returns:
        Dict[str, Any]: 迁移后的新字典
    """
    data = dict(data)
    for old_key, new_key in _PRICE_KEY_MIGRATION:
        if old_key in data:
            old_value = data.pop(old_key)
            if new_key not in data and old_value is not None:
                data[new_key] = old_value * _PRICE_PER_1K_TO_1M_FACTOR
    return data


def _extract_legacy_capabilities(data: Dict[str, Any]) -> List[str]:
    """从历史模板式布尔键提取能力列表

    映射规则：support_vision→vision、support_function_calling→tools、
    support_embedding→embedding；support_chat 不映射为能力。

    Args:
        data: 条目字典（含历史布尔键）

    Returns:
        List[str]: 提取出的能力列表
    """
    capabilities = []
    for bool_key, capability in _LEGACY_BOOL_CAPABILITY_MAP.items():
        if data.get(bool_key):
            capabilities.append(capability)
    return capabilities


def _filter_capabilities(raw: Any) -> List[str]:
    """过滤并去重能力列表，仅保留闭集内的合法值

    Args:
        raw: 原始能力值（期望为列表，其他类型按空列表处理）

    Returns:
        List[str]: 合法能力列表，按 ALL_CAPABILITIES 声明顺序排列
    """
    if not isinstance(raw, list):
        return []
    requested = set(raw)
    return [cap for cap in ALL_CAPABILITIES if cap in requested]


def _apply_schema_defaults(entry: Dict[str, Any]) -> None:
    """就地补全统一 schema 的缺失键默认值

    Args:
        entry: 条目字典（就地修改）
    """
    entry.setdefault("name", entry.get("id", ""))
    entry.setdefault("group", "")
    entry.setdefault("context_length", None)
    entry.setdefault("support_streaming", True)
    entry.setdefault("currency", DEFAULT_CURRENCY)
    entry.setdefault("input_price_per_1m", None)
    entry.setdefault("output_price_per_1m", None)


def normalize_model_entry(data: Dict[str, Any]) -> Dict[str, Any]:
    """将任意历史 schema 的模型条目规范化为统一 schema

    兼容两种历史 schema：
    - 模板式：含 support_chat/support_vision/support_function_calling/
      support_embedding 布尔键，转换为 capabilities 后删除旧布尔键；
    - UI 式：已是 capabilities 列表，透传（过滤非法值）并补全默认值。

    两种 schema 均处理：历史定价键 per_1k → per_1m 迁移（×1000，
    并存时以 per_1m 为准）；未知额外键（如 description、max_output）保留。

    Args:
        data: 原始模型条目字典（不会被修改）

    Returns:
        Dict[str, Any]: 规范化后的新字典
    """
    entry = _migrate_price_keys(data)
    capabilities = entry.get("capabilities")
    if capabilities is None:
        capabilities = _extract_legacy_capabilities(entry)
    entry["capabilities"] = _filter_capabilities(capabilities)
    # 删除历史模板式布尔键（support_chat 一并删除，不映射为能力）
    for bool_key in _LEGACY_BOOL_KEYS:
        entry.pop(bool_key, None)
    _apply_schema_defaults(entry)
    return entry


# ==================== 分组工具 ====================

def infer_model_group(model_id: str) -> str:
    """按模型 ID 关键字推断系列分组名

    先按 _MODEL_GROUP_KEYWORDS 关键字表顺序匹配；未命中时按路径分隔符
    取首段（如 "Pro/xxx" → "Pro"）；仍无结果返回「其他」。

    Args:
        model_id: 模型 ID

    Returns:
        str: 分组名
    """
    lowered = model_id.lower()
    for keyword, group_name in _MODEL_GROUP_KEYWORDS.items():
        if keyword in lowered:
            return group_name
    parts = model_id.split(_MODEL_ID_PATH_SEPARATOR)
    if len(parts) > 1 and parts[0]:
        return parts[0]
    return GROUP_OTHER


def _merge_source_into(
    merged: Dict[str, Dict[str, Any]],
    order: List[str],
    models: Optional[List[Dict[str, Any]]],
) -> None:
    """将单个来源的模型条目规范化后并入合并表（就地修改）

    同 id 条目直接替换（后者覆盖前者），首次出现的 id 追加到顺序表；
    缺少 id 的条目无法参与按 id 合并，跳过。

    Args:
        merged: 合并表（id → 规范化条目），就地修改
        order: 条目顺序表（按首次出现顺序），就地修改
        models: 来源条目列表，None 或空列表视为无条目
    """
    for model in models or []:
        entry = normalize_model_entry(model)
        model_id = entry.get("id")
        if not model_id:
            continue
        if model_id not in merged:
            order.append(model_id)
        merged[model_id] = entry


def merge_model_entries(
    preset_models: Optional[List[Dict[str, Any]]],
    fetched_models: Optional[List[Dict[str, Any]]],
    custom_models: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """三路合并模型条目：目录预设 + API 拉取/缓存 + 用户覆写

    合并规则（按 id 对齐）：
    - preset_models：目录层预设模型，作为基础集合；
    - fetched_models：API 拉取/缓存模型（ModelInfo.to_dict() 形态），
      同 id 覆盖预设条目；
    - custom_models：用户覆写（含用户手工新增），同 id 优先级最高。

    全部条目均经 normalize_model_entry 规范化（历史布尔键转
    capabilities、per_1k 定价迁移、缺省键补全）；输出顺序为各来源
    条目首次出现的顺序（预设在前、拉取居中、用户覆写新增在后）。

    Args:
        preset_models: 目录预设模型条目列表，可为 None
        fetched_models: API 拉取/缓存的模型条目列表，可为 None
        custom_models: 用户覆写条目列表，可为 None

    Returns:
        List[Dict[str, Any]]: 合并后的统一 schema 条目列表
    """
    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for source in (preset_models, fetched_models, custom_models):
        _merge_source_into(merged, order, source)
    return [merged[model_id] for model_id in order]


def models_to_groups(models: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """按 group 字段将模型条目聚合为分组字典

    组名为空（空串或缺失）的条目统一归入「未分组」。

    Args:
        models: 模型条目列表（应为统一 schema）

    Returns:
        Dict[str, List[Dict[str, Any]]]: 分组名 → 条目列表（保持原顺序）
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for model in models:
        group_name = model.get("group") or GROUP_UNGROUPED
        groups.setdefault(group_name, []).append(model)
    return groups
