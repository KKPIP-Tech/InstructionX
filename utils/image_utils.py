"""图片工具模块

提供与具体业务无关的通用图片处理工具函数。
原 ``LLMPluginService.load_image_as_base64`` 迁移至此：
该能力是纯文件工具，不属于 LLM 门面职责。
"""

import base64


def load_image_as_base64(file_path: str) -> str:
    """加载图片文件为 base64 字符串

    Args:
        file_path: 图片文件路径

    Returns:
        str: base64 编码字符串（不含 data URI 前缀）

    Raises:
        OSError: 文件不存在或读取失败时抛出
    """
    with open(file_path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode("utf-8")
