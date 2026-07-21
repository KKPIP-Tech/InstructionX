import os
import logging
import inspect
import types
import typing
# from datetime import datetime
from logging.handlers import RotatingFileHandler
import threading

from utils.i_logger import ILogger


class _ModuleNameFilter(logging.Filter):
    """
    为日志记录注入默认 module_name 属性的过滤器

    Formatter 依赖自定义属性 %(module_name)s，只有经 LoggerManager.log()
    写入的记录才带该属性；直接向 'ApplicationLogger' 写日志的代码会缺少
    module_name 而抛 KeyError。此过滤器在记录缺少该属性时回退为标准
    module 属性（再退化为 'unknown'），保持日志格式外观不变。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, 'module_name'):
            record.module_name = getattr(record, 'module', None) or 'unknown'
        return True


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
        
        # 创建logs目录（如果不存在）
        # 默认 "./logs"（历史行为，被测试基线锁定）；
        # 可通过环境变量 INSTRUCTIONX_LOG_DIR 覆盖为其他路径（如项目根推导路径）
        log_dir = os.environ.get('INSTRUCTIONX_LOG_DIR', './logs')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # 配置日志文件路径
        log_file = os.path.join(log_dir, "application.log")
        
        # 创建logger实例
        # 全局日志等级可通过环境变量 INSTRUCTIONX_LOG_LEVEL 调节（默认 DEBUG，保持兼容）；
        # 非法等级值回退 DEBUG
        self._logger = logging.getLogger('ApplicationLogger')
        level_name = os.environ.get('INSTRUCTIONX_LOG_LEVEL', 'DEBUG').upper()
        log_level = getattr(logging, level_name, None)
        if not isinstance(log_level, int):
            log_level = logging.DEBUG
        self._logger.setLevel(log_level)
        
        # 防止重复添加handler
        if not self._logger.handlers:
            # 创建文件处理器（支持日志轮转，每个文件最大10MB，保留5个备份）
            file_handler = RotatingFileHandler(
                log_file, 
                maxBytes=10*1024*1024, 
                backupCount=5,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)
            
            # 创建格式化器
            formatter = logging.Formatter(
                fmt='[%(asctime)s][%(module_name)s][%(levelname)s][Message-->][%(message)s]',
                datefmt='%Y-%m-%d][%H-%M-%S'
            )
            file_handler.setFormatter(formatter)
            
            # 添加处理器到logger
            self._logger.addHandler(file_handler)
            
            # 添加过滤器：为未经 log() 写入的记录注入默认 module_name
            self._logger.addFilter(_ModuleNameFilter())
            
            # 如果是开发环境（有控制台），添加控制台处理器
            if os.environ.get('DEVELOPMENT_MODE', 'false').lower() == 'true':
                console_handler = logging.StreamHandler()
                console_handler.setLevel(logging.DEBUG)
                console_handler.setFormatter(formatter)
                self._logger.addHandler(console_handler)
        
        self._initialized = True

    def log(self, level: str, module_name: str, message: str) -> None:
        """
        记录日志
        
        参数:
            level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            module_name: 模块名称
            message: 日志消息
        """
        # 使用extra参数传递module_name
        # 注意：非法 level 会抛 AttributeError（历史行为，被测试基线锁定）
        logger = self._logger
        if logger is not None:
            logger.log(
                getattr(logging, level.upper()),
                message,
                extra={'module_name': module_name}
            )

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
        
