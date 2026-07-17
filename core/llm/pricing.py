"""LLM Provider 默认定价表

定义各 Provider 的默认 token 定价。

单位约定:
    统一为 **元人民币 / 百万 tokens（per_1m）**。
    结构: {"<provider>": {"models": {"<model>": {"input": x, "output": y}}}}
    input/output 分别为每百万输入/输出 tokens 的价格（元）。

注意:
    以下价格仅供参考（截至整理时的公开价格按汇率粗略折算），
    实际计费以各厂商最新定价为准。用户可通过配置文件覆盖此默认值。

Usage:
    from core.llm.pricing import DEFAULT_PRICING
"""

# 默认定价（元人民币/百万 tokens），可由用户在配置文件中覆盖
# 仅供参考，以厂商最新定价为准
DEFAULT_PRICING: dict = {
    "glm": {
        "models": {
            # 免费模型
            "glm-4-flash": {"input": 0.0, "output": 0.0},
            "glm-4-flash-250414": {"input": 0.0, "output": 0.0},
            "glm-4.5-flash": {"input": 0.0, "output": 0.0},
            "glm-4.7-flash": {"input": 0.0, "output": 0.0},
            "glm-4v-flash": {"input": 0.0, "output": 0.0},
            # 高性价比
            "glm-4-air": {"input": 0.5, "output": 0.5},
            "glm-4.5-air": {"input": 0.5, "output": 0.5},
            "glm-4.5-airx": {"input": 1.0, "output": 1.0},
            # 高智能模型
            "glm-4.5": {"input": 2.0, "output": 8.0},
            "glm-4.6": {"input": 2.0, "output": 8.0},
            "glm-4-long": {"input": 1.0, "output": 1.0},
            # 向量模型
            "embedding-3": {"input": 0.5, "output": 0.0},
            "embedding-2": {"input": 0.5, "output": 0.0},
        },
    },
    "minimax": {
        "models": {
            "MiniMax-M2": {"input": 2.1, "output": 8.4},
            "MiniMax-M2.1": {"input": 2.1, "output": 8.4},
            "MiniMax-M2.5": {"input": 2.1, "output": 8.4},
            "MiniMax-M2.7": {"input": 2.1, "output": 8.4},
            "embedding-2": {"input": 0.7, "output": 0.0},
        },
    },
    "siliconflow": {
        "models": {
            # DeepSeek 系列约 1-2 元/百万输入
            "deepseek-ai/DeepSeek-V3": {"input": 2.0, "output": 8.0},
            "Pro/deepseek-ai/DeepSeek-V3": {"input": 2.0, "output": 8.0},
            "deepseek-ai/DeepSeek-R1": {"input": 4.0, "output": 16.0},
            # 免费小模型
            "Qwen/Qwen2.5-7B-Instruct": {"input": 0.0, "output": 0.0},
            "BAAI/bge-m3": {"input": 0.0, "output": 0.0},
            "BAAI/bge-large-zh-v1.5": {"input": 0.0, "output": 0.0},
        },
    },
    "openai": {
        "models": {
            # 按美元官方价粗略折算（1 USD ≈ 7.2 CNY）
            "gpt-4o": {"input": 18.0, "output": 72.0},
            "gpt-4o-mini": {"input": 1.1, "output": 4.4},
            "gpt-4-turbo": {"input": 72.0, "output": 216.0},
            "gpt-3.5-turbo": {"input": 3.6, "output": 10.8},
            "text-embedding-3-small": {"input": 0.15, "output": 0.0},
            "text-embedding-3-large": {"input": 0.95, "output": 0.0},
        },
    },
    "ollama": {
        # 本地部署，无计费
        "models": {},
    },
}
