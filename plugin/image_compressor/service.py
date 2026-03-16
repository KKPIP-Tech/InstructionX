"""
图片压缩服务
"""
from PySide6.QtWidgets import QFileDialog, QMessageBox
import os

from utils.logging_tools import LoggerManager, get_name


class Service:
    """图片压缩服务"""

    _logger = LoggerManager()

    def compress_image(self, file_path: str, quality: int = 85) -> bool:
        """
        压缩图片
        
        Args:
            file_path: 图片文件路径
            quality: 压缩质量 (1-100)
            
        Returns:
            是否成功
        """
        try:
            # 这里实现实际的图片压缩逻辑
            # 简化版本，仅作为示例
            if not os.path.exists(file_path):
                return False
            
            # 实际应用中可以使用 Pillow 等库进行压缩
            # from PIL import Image
            # img = Image.open(file_path)
            # img.save(output_path, quality=quality, optimize=True)
            
            return True
        except Exception as e:
            self._logger.error(get_name(), f'Error compressing image: {e}')
            return False
    
    def get_image_info(self, file_path: str) -> dict:
        """
        获取图片信息
        
        Args:
            file_path: 图片文件路径
            
        Returns:
            图片信息字典
        """
        try:
            if not os.path.exists(file_path):
                return {}
            
            file_size = os.path.getsize(file_path)
            file_size_mb = file_size / (1024 * 1024)
            
            return {
                'file_path': file_path,
                'file_size': file_size_mb,
                'file_size_str': f"{file_size_mb:.2f} MB"
            }
        except Exception as e:
            self._logger.error(get_name(), f'Error getting image info: {e}')
            return {}