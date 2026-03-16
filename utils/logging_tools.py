import os
import logging
import inspect
import types
import typing
# from datetime import datetime
from logging.handlers import RotatingFileHandler
import threading


class LoggerManager:
    """
    单例模式的日志管理器类，支持按指定格式记录日志到文件
    格式：[YYYY-MM-DD][hh-mm-ss][模块名称][等级][Message:][]
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
        log_dir = "./logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # 配置日志文件路径
        log_file = os.path.join(log_dir, "application.log")
        
        # 创建logger实例
        self._logger = logging.getLogger('ApplicationLogger')
        self._logger.setLevel(logging.DEBUG)
        
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
    
    
def get_name() -> str:
    """
    自动获取当前调用位置的模块名称
    无论是从类方法、函数还是主模块调用都能正确获取
    
    返回:
        str: 模块名称（不含文件扩展名）
    """
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
        
        # 尝试获取调用者的模块
        module = inspect.getmodule(caller_frame)
        
        if module:
            # 如果是主模块(__main__)，从文件名获取
            if module.__name__ == '__main__':
                file_path = getattr(module, '__file__', None)
                if file_path:
                    return os.path.splitext(os.path.basename(file_path))[0]
                else:
                    return 'main'
            # 返回模块名称
            return module.__name__
        else:
            # 如果无法获取模块对象，从文件名获取
            code = caller_frame.f_code
            if code:
                filename = code.co_filename
                if filename:
                    return os.path.splitext(os.path.basename(filename))[0]
            # 如果连文件名都获取不到，返回默认值
            return 'unknown'
            
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
        

if __name__ == "__main__":
    logger = LoggerManager()
    logger.info('UserModule', '用户登录成功')
    logger.error('DatabaseModule', '数据库连接失败')
    logger.debug('APIModule', '处理请求开始')
    logger.warning('CacheModule', '缓存即将过期')
    logger.critical('SecurityModule', '检测到安全威胁')
    # 或者使用通用log方法
    logger.log('INFO', 'PaymentModule', '支付处理完成')
    logger.info(get_name(), '用户登录成功')
    logger.error(get_name(), '数据库连接失败')
    logger.debug(get_name(), '处理请求开始')
    logger.warning(get_name(), '缓存即将过期')
    logger.critical(get_name(), '检测到安全威胁')
