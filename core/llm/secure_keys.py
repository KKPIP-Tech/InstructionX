"""API 密钥存储编码模块(跨平台)

按项目决策,密钥以 **Base64 编码**存储(``b64:`` 前缀),任何平台行为一致。

注意:Base64 是**编码而非加密**——仅避免配置文件被翻阅时直接暴露
明文密钥(防瞥视),不提供安全防护。需要真正机密性的部署环境应
自行通过文件系统权限保护 config/ 目录。

设计要点:
    - 只在「配置文件读写边界」编解码,内存中的 ProviderConfig.api_key
      始终是明文(UI 编辑、Provider 请求头均不受影响);
    - 无前缀的值按明文原样处理(向后兼容旧版配置,首次保存自动升级
      为 Base64 编码);
    - 解码失败(非法 Base64)时原样返回并记 warning,容错优先。
"""

import base64
import binascii
import logging

logger = logging.getLogger(__name__)

#: Base64 编码标识前缀
ENCODED_PREFIX = "b64:"


def encode_secret(plain: str) -> str:
    """把密钥字符串编码为 ``b64:<base64>`` 形式

    空字符串原样返回(不空前缀化,保持配置文件干净)。

    Args:
        plain: 明文密钥

    Returns:
        str: ``b64:`` 前缀的 Base64 编码串
    """
    if not plain:
        return plain
    encoded = base64.b64encode(plain.encode("utf-8")).decode("ascii")
    return ENCODED_PREFIX + encoded


def decode_secret(stored: str) -> str:
    """把存储的密钥字符串解码回明文

    无 ``b64:`` 前缀的值按明文原样返回(向后兼容旧版明文配置)。

    Args:
        stored: 存储的值(明文或 ``b64:`` 编码串)

    Returns:
        str: 明文密钥;解码失败时原样返回并记 warning
    """
    if not stored or not stored.startswith(ENCODED_PREFIX):
        return stored
    payload = stored[len(ENCODED_PREFIX):]
    try:
        return base64.b64decode(payload).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as e:
        logger.warning(f"API 密钥 Base64 解码失败,按原文使用: {e}")
        return stored
