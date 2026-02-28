"""
颜色转换服务 - 功能实现
"""

class Service:
    """颜色转换服务类，提供颜色格式转换功能的实现"""
    
    def hex_to_rgb(self, hex_str: str) -> str:
        """
        将 HEX 颜色格式转换为 RGB 格式
        
        Args:
            hex_str: HEX 颜色字符串（如 #FF5733 或 FF5733）
            
        Returns:
            RGB 格式字符串（如 rgb(255, 87, 51)），如果格式无效则返回错误信息
        """
        # 移除 # 前缀
        if hex_str.startswith('#'):
            hex_str = hex_str[1:]
        
        # 验证长度
        if len(hex_str) != 6:
            return "无效的 HEX 格式"
        
        try:
            # 转换为 RGB
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
            return f"rgb({r}, {g}, {b})"
        except ValueError:
            return "无效的 HEX 格式"