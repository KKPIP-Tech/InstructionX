"""
Logger 接口

向后兼容重导出：实际定义已移至 utils/i_logger.py
"""

# 向后兼容导入
from utils.i_logger import ILogger

__all__ = ["ILogger"]
