"""LLM Provider 默认定价表

定义各 Provider 的默认 token 定价（元/千 token）。
用户可通过配置文件覆盖此默认值。

Usage:
    from core.llm.pricing import DEFAULT_PRICING
"""

# 默认定价（元/千 token），可由用户在配置文件中覆盖
DEFAULT_PRICING: dict = {
    "minimax": {
        "chat": {"input_per_1k": 0.1, "output_per_1k": 0.1},
        "embedding": {"per_1k": 0.001},
    },
    "siliconflow": {
        "chat": {"input_per_1k": 0.001, "output_per_1k": 0.001},
        "embedding": {"per_1k": 0.0001},
    },
    "glm": {
        "chat": {"input_per_1k": 0.1, "output_per_1k": 0.1},
        "embedding": {"per_1k": 0.0001},
    },
    "ollama": {
        "chat": {"input_per_1k": 0.0, "output_per_1k": 0.0},
        "embedding": {"per_1k": 0.0},
    },
}
