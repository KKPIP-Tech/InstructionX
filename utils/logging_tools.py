import os
import logging
import inspect
import types
import typing
from collections import deque
from logging.handlers import RotatingFileHandler
import threading

from core.observability.context import current_log_fields
from core.observability.sanitize import sanitize_text
from utils.i_logger import ILogger

LOG_FORMAT = (
    '[%(asctime)s][%(module_name)s][%(levelname)s]'
    '[trace=%(correlation_id)s][plugin=%(plugin_id)s][task=%(task_id)s]'
    '[request=%(request_id)s][conversation=%(conversation_id)s]'
    '[duration_ms=%(duration_ms)s][Message-->][%(message)s]'
)
LOG_DATE_FORMAT = '%Y-%m-%d][%H-%M-%S'
LOG_FILE_MAX_BYTES = 10 * 1024 * 1024
LOG_FILE_BACKUP_COUNT = 5
DEGRADED_MEMORY_CAPACITY = 1000
CONTEXT_FIELD_NAMES = (
    'correlation_id', 'plugin_id', 'task_id', 'request_id', 'conversation_id', 'duration_ms'
)


class _ObservabilityFilter(logging.Filter):
    """注入默认模块名和当前调用链，字段缺失时使用有限占位符。"""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if not hasattr(record, 'module_name'):
                record.module_name = getattr(record, 'module', None) or 'unknown'
            for name, value in current_log_fields().items():
                if not hasattr(record, name):
                    setattr(record, name, value)
        except Exception:
            record.module_name = getattr(record, 'module_name', 'unknown')
            for name in CONTEXT_FIELD_NAMES:
                if not hasattr(record, name):
                    setattr(record, name, '-')
        return True


class _ObservabilityFormatter(logging.Formatter):
    """在完整格式化后统一脱敏，覆盖位置参数与直接 stdlib 日志。"""

    def format(self, record: logging.LogRecord) -> str:
        try:
            return sanitize_text(super().format(record))
        except Exception:
            return sanitize_text(getattr(record, 'msg', '[日志格式化失败]'))


class _SafeRotatingFileHandler(RotatingFileHandler):
    """轮转或写盘失败只累计诊断错误，不向业务线程抛出。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.write_failures = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
        except Exception:
            self.write_failures += 1


class _BoundedMemoryHandler(logging.Handler):
    """文件不可用时的固定容量内存降级，不无限保存日志。"""

    def __init__(self):
        super().__init__()
        self.records = deque(maxlen=DEGRADED_MEMORY_CAPACITY)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(self.format(record))
        except Exception:
            return


class LoggerManager(ILogger):
    """
    单例模式的日志管理器类，支持按指定格式记录日志到文件
    格式：[YYYY-MM-DD][HH-MM-SS][模块名称][等级][Message:][]
    """
    _instance = None
    _lock = threading.Lock()
    _logger = None

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(LoggerManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._write_failures = 0
        self._logger = logging.getLogger('ApplicationLogger')
        self._configure_level()
        if not self._logger.handlers:
            log_dir = os.environ.get('INSTRUCTIONX_LOG_DIR', './logs')
            self._configure_handlers(log_dir)
        if not any(isinstance(item, _ObservabilityFilter) for item in self._logger.filters):
            self._logger.addFilter(_ObservabilityFilter())
        self._initialized = True

    def _configure_level(self) -> None:
        """配置日志等级，非法环境变量保持历史 DEBUG 回退。"""
        level_name = os.environ.get('INSTRUCTIONX_LOG_LEVEL', 'DEBUG').upper()
        log_level = getattr(logging, level_name, None)
        self._logger.setLevel(log_level if isinstance(log_level, int) else logging.DEBUG)

    def _configure_handlers(self, log_dir: str) -> None:
        """配置文件和有界降级处理器，所有处理器共用脱敏格式。"""
        formatter = _ObservabilityFormatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
        handler = self._create_file_handler(log_dir)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)
        self._logger.addHandler(handler)
        if os.environ.get('DEVELOPMENT_MODE', 'false').lower() == 'true':
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            console_handler.setFormatter(formatter)
            self._logger.addHandler(console_handler)

    @staticmethod
    def _create_file_handler(log_dir: str) -> logging.Handler:
        """创建轮转文件处理器，失败时返回固定容量内存处理器。"""
        try:
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            log_file = os.path.join(log_dir, "application.log")
            return _SafeRotatingFileHandler(
                log_file,
                maxBytes=LOG_FILE_MAX_BYTES,
                backupCount=LOG_FILE_BACKUP_COUNT,
                encoding='utf-8',
            )
        except Exception:
            return _BoundedMemoryHandler()

    def log(self, level: str, module_name: str, message: str) -> None:
        """记录日志；非法级别保持原异常，写入失败只累计诊断错误。"""
        log_level = getattr(logging, level.upper())
        logger = self._logger
        if logger is None:
            return
        try:
            logger.log(log_level, message, extra={'module_name': module_name})
        except Exception:
            self._write_failures += 1

    def debug(self, module_name, message):
        """记录DEBUG级别日志"""
        self.log('DEBUG', module_name, message)

    def info(self, module_name, message):
        """记录INFO级别日志"""
        self.log('INFO', module_name, message)

    def warning(self, module_name, message):
        """记录WARNING级别日志"""
        self.log('WARNING', module_name, message)

    def error(self, module_name, message):
        """记录ERROR级别日志"""
        self.log('ERROR', module_name, message)

    def critical(self, module_name, message):
        """记录CRITICAL级别日志"""
        self.log('CRITICAL', module_name, message)

    def get_logger(self):
        """获取logger实例（备用方法）"""
        return self._logger
    
    
# get_name 模块名缓存：inspect.getmodule() 栈自省成本高，按调用者文件名缓存结果。
# 若 inspect.getmodule 被替换（如测试 monkeypatch），缓存自动失效以保证行为正确。
_module_name_cache: dict = {}
_cache_getmodule_ref = None


def get_name() -> str:
    """
    自动获取当前调用位置的模块名称
    无论是从类方法、函数还是主模块调用都能正确获取
    
    返回:
        str: 模块名称（不含文件扩展名）
    """
    global _cache_getmodule_ref
    frame: types.FrameType | None = None
    try:
        # 获取当前调用栈
        frame = inspect.currentframe()
        if frame is None:
            return 'unknown'
        
        # 向上跳过一帧（跳过get_name函数本身）
        caller_frame = frame.f_back
        if caller_frame is None:
            return 'unknown'
        
        # inspect.getmodule 被替换时清空缓存（兼容 monkeypatch 等场景）
        if _cache_getmodule_ref is not inspect.getmodule:
            _module_name_cache.clear()
            _cache_getmodule_ref = inspect.getmodule
        
        code = caller_frame.f_code
        filename = code.co_filename if code else None
        
        # 命中缓存则直接返回，避免重复的栈自省
        if filename and filename in _module_name_cache:
            return _module_name_cache[filename]
        
        # 尝试获取调用者的模块
        module = inspect.getmodule(caller_frame)
        
        if module:
            # 如果是主模块(__main__)，从文件名获取
            if module.__name__ == '__main__':
                file_path = getattr(module, '__file__', None)
                if file_path:
                    name = os.path.splitext(os.path.basename(file_path))[0]
                else:
                    name = 'main'
            else:
                # 返回模块名称
                name = module.__name__
        else:
            # 如果无法获取模块对象，从文件名获取
            if filename:
                name = os.path.splitext(os.path.basename(filename))[0]
            else:
                # 如果连文件名都获取不到，返回默认值
                return 'unknown'
        
        if filename:
            _module_name_cache[filename] = name
        return name
            
    except Exception:
        # 异常情况下返回默认值
        return 'unknown'
    finally:
        # 确保删除frame引用以避免引用循环
        if frame is not None:
            try:
                del frame
            except Exception:
                pass
        
