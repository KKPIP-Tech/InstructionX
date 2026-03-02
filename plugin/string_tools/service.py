"""
字符串工具服务 - 提供 API 方法供其他插件调用
"""

class Service:
    """字符串工具服务类，提供各种字符串处理功能"""
    
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
    
    def reverse_text(self, text: str) -> str:
        """
        反转文本
        
        Args:
            text: 输入文本
            
        Returns:
            反转后的文本
        """
        return text[::-1]
    
    def capitalize_words(self, text: str) -> str:
        """
        将每个单词的首字母大写
        
        Args:
            text: 输入文本
            
        Returns:
            首字母大写的文本
        """
        return ' '.join(word.capitalize() for word in text.split())
    
    def count_words(self, text: str) -> int:
        """
        统计单词数量
        
        Args:
            text: 输入文本
            
        Returns:
            单词数量
        """
        return len(text.split())
    
    def count_chars(self, text: str, include_spaces: bool = True) -> int:
        """
        统计字符数量
        
        Args:
            text: 输入文本
            include_spaces: 是否包含空格，默认为 True
            
        Returns:
            字符数量
        """
        if include_spaces:
            return len(text)
        else:
            return len(text.replace(" ", ""))
    
    def remove_whitespace(self, text: str) -> str:
        """
        移除所有空白字符
        
        Args:
            text: 输入文本
            
        Returns:
            移除空白后的文本
        """
        return ''.join(text.split())