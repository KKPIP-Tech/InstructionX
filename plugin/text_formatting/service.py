"""
文本格式化服务 - 功能实现
"""

class Service:
    """文本格式化服务类，提供文本格式化功能的实现"""
    
    def to_uppercase(self, text: str) -> str:
        """
        将文本转换为大写
        
        Args:
            text: 输入文本
            
        Returns:
            大写文本
        """
        return text.upper()
    
    def to_lowercase(self, text: str) -> str:
        """
        将文本转换为小写
        
        Args:
            text: 输入文本
            
        Returns:
            小写文本
        """
        return text.lower()