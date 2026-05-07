"""LLM Provider 默认定价表

定义各 Provider 的默认 token 定价（元/千 token）。
用户可通过配置文件覆盖此默认值。

Usage:
    from core.llm.pricing import DEFAULT_PRICING
"""

# 默认定价（元/千 token），可由用户在配置文件中覆盖
DEFAULT_PRICING: dict = {
    "minimax": {
        "chat": {"input_per_1k": 100, "output_per_1k": 100},
        "embedding": {"per_1k": 1},
    },
    "siliconflow": {
        "chat": {"input_per_1k": 1, "output_per_1k": 1},
        "embedding": {"per_1k": 0.1},
    },
    "glm": {
        "chat": {"input_per_1k": 100, "output_per_1k": 100},
        "embedding": {"per_1k": 0.1},
    },
    "ollama": {
        "chat": {"input_per_1k": 0.0, "output_per_1k": 0.0},
        "embedding": {"per_1k": 0.0},
    },
    "openai": {
        "chat": {"input_per_1k": 18, "output_per_1k": 72},
        "embedding": {"per_1k": 0.02},
    },
}
