"""进程外插件宿主的版本化长度帧 JSON-RPC 协议。"""

import json
import struct
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, BinaryIO, Dict, Optional


PROTOCOL_VERSION = 1
MESSAGE_HEADER_SIZE = 4
DEFAULT_MAX_MESSAGE_SIZE = 1024 * 1024
_LENGTH_STRUCT = struct.Struct(">I")


class ErrorCode(StrEnum):
    """宿主与插件调用的闭集错误码。"""

    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_PARAMS = "INVALID_PARAMS"
    METHOD_NOT_FOUND = "METHOD_NOT_FOUND"
    PLUGIN_ERROR = "PLUGIN_ERROR"
    PLUGIN_UNAVAILABLE = "PLUGIN_UNAVAILABLE"
    CALL_TIMEOUT = "CALL_TIMEOUT"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    HOST_BUSY = "HOST_BUSY"
    HOST_STOPPED = "HOST_STOPPED"
    PROTOCOL_ERROR = "PROTOCOL_ERROR"
    SERIALIZATION_ERROR = "SERIALIZATION_ERROR"
    STARTUP_FAILED = "STARTUP_FAILED"


class ProtocolError(ValueError):
    """消息长度、编码或契约不合法。"""


class ProtocolEOF(ProtocolError):
    """对端在完整消息到达前关闭连接。"""


@dataclass(frozen=True, slots=True)
class RpcError:
    """可直接展示给调用方的结构化错误。"""

    code: str
    message: str


@dataclass(frozen=True, slots=True)
class RpcResult:
    """单次调用的成功值或失败原因，二者不会同时出现。"""

    value: Any = None
    error: Optional[RpcError] = None
    request_id: str = ""

    @property
    def success(self) -> bool:
        """仅在未携带错误时返回真。"""
        return self.error is None


_MESSAGE_FIELDS = {
    "call": {"version", "type", "id", "method", "args"},
    "result": {"version", "type", "id", "result"},
    "error": {"version", "type", "id", "code", "message"},
    "heartbeat": {"version", "type", "id"},
    "ready": {"version", "type", "id", "plugin_id", "methods"},
    "shutdown": {"version", "type", "id"},
    "stopped": {"version", "type", "id"},
}


def validate_message(message: Any) -> None:
    """校验消息对象；不合法时抛出 ``ProtocolError``。"""
    if not isinstance(message, dict):
        raise ProtocolError("消息根节点必须是对象")
    version = message.get("version")
    if type(version) is not int or version != PROTOCOL_VERSION:
        raise ProtocolError("协议版本不受支持")
    message_type = message.get("type")
    if not isinstance(message_type, str):
        raise ProtocolError("消息类型必须是字符串")
    required = _MESSAGE_FIELDS.get(message_type)
    if required is None:
        raise ProtocolError("消息类型不受支持")
    if set(message) != required:
        raise ProtocolError("消息字段与类型不匹配")
    request_id = message.get("id")
    if not isinstance(request_id, str) or not request_id:
        raise ProtocolError("请求 ID 必须是非空字符串")
    _validate_payload(message_type, message)


def _validate_payload(message_type: str, message: Dict[str, Any]) -> None:
    if message_type == "call":
        if not isinstance(message["method"], str) or not message["method"]:
            raise ProtocolError("调用方法名必须是非空字符串")
        if not isinstance(message["args"], (list, dict)):
            raise ProtocolError("调用参数必须是数组或对象")
    if message_type == "error":
        if not isinstance(message["code"], str) or message["code"] not in ErrorCode:
            raise ProtocolError("错误码不受支持")
        if not isinstance(message["message"], str):
            raise ProtocolError("错误消息必须是字符串")
    if message_type == "ready":
        if not isinstance(message["plugin_id"], str) or not message["plugin_id"]:
            raise ProtocolError("ready.plugin_id 必须是非空字符串")
        methods = message["methods"]
        if not isinstance(methods, list) or not all(isinstance(item, str) for item in methods):
            raise ProtocolError("ready.methods 必须是字符串数组")


def encode_message(
    message: Dict[str, Any],
    *,
    validate: bool = True,
    max_message_size: int = DEFAULT_MAX_MESSAGE_SIZE,
) -> bytes:
    """编码一个带四字节大端长度前缀的完整消息。"""
    if validate:
        validate_message(message)
    try:
        body = json.dumps(
            message, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"消息无法序列化: {exc}") from exc
    if len(body) > max_message_size:
        raise ProtocolError("消息超过声明的大小上限")
    return _LENGTH_STRUCT.pack(len(body)) + body


def decode_message(frame: bytes) -> Dict[str, Any]:
    """解码不带长度前缀的 UTF-8 JSON 消息体并执行严格校验。"""
    try:
        text = frame.decode("utf-8")
        message = json.loads(
            text, object_pairs_hook=_unique_object, parse_constant=_reject_constant
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ProtocolError(f"JSON 消息无效: {exc}") from exc
    validate_message(message)
    return message


def read_message(
    stream: BinaryIO, max_message_size: int = DEFAULT_MAX_MESSAGE_SIZE
) -> Dict[str, Any]:
    """从二进制流读取一条消息，拒绝截断帧和超长声明。"""
    header = _read_exact(stream, MESSAGE_HEADER_SIZE)
    body_size = _LENGTH_STRUCT.unpack(header)[0]
    if body_size > max_message_size:
        raise ProtocolError("对端声明的消息超过大小上限")
    return decode_message(_read_exact(stream, body_size))


def write_message(
    stream: BinaryIO,
    message: Dict[str, Any],
    max_message_size: int = DEFAULT_MAX_MESSAGE_SIZE,
) -> None:
    """写入一条完整消息并立即刷新，避免交互响应滞留缓冲区。"""
    stream.write(encode_message(message, max_message_size=max_message_size))
    stream.flush()


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = stream.read(size - len(chunks))
        if not chunk:
            raise ProtocolEOF("对端在完整消息到达前关闭连接")
        chunks.extend(chunk)
    return bytes(chunks)


def _unique_object(pairs: list) -> Dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON 包含重复字段: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"JSON 不允许非有限数值: {value}")
