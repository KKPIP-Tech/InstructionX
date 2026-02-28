"""
代码格式化服务
"""
import re


class Service:
    """代码格式化服务"""
    
    def format_json(self, json_str: str) -> str:
        """
        格式化JSON字符串
        
        Args:
            json_str: JSON字符串
            
        Returns:
            格式化后的JSON字符串
        """
        try:
            import json
            data = json.loads(json_str)
            return json.dumps(data, indent=4, ensure_ascii=False)
        except Exception as e:
            return f"JSON格式错误: {e}"
    
    def format_xml(self, xml_str: str) -> str:
        """
        格式化XML字符串
        
        Args:
            xml_str: XML字符串
            
        Returns:
            格式化后的XML字符串
        """
        try:
            # 简单的XML格式化
            # 实际应用中可以使用 xml.dom.minidom 或 lxml
            from xml.dom.minidom import parseString
            dom = parseString(xml_str)
            return dom.toprettyxml(indent="  ")
        except Exception as e:
            return f"XML格式错误: {e}"
    
    def remove_comments(self, code: str, language: str = "python") -> str:
        """
        移除代码注释
        
        Args:
            code: 代码字符串
            language: 编程语言
            
        Returns:
            移除注释后的代码
        """
        try:
            if language == "python":
                # 移除 Python 单行注释
                lines = []
                for line in code.split('\n'):
                    # 移除行尾注释
                    line = re.sub(r'#.*$', '', line)
                    lines.append(line)
                return '\n'.join(lines)
            elif language == "javascript":
                # 移除 JavaScript 单行和多行注释
                code = re.sub(r'//.*', '', code)  # 单行注释
                code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)  # 多行注释
                return code
            else:
                return code
        except Exception as e:
            return f"移除注释错误: {e}"
    
    def compress_code(self, code: str) -> str:
        """
        压缩代码（移除空白字符）
        
        Args:
            code: 代码字符串
            
        Returns:
            压缩后的代码
        """
        try:
            # 移除多余的空行和空白字符
            lines = []
            for line in code.split('\n'):
                stripped = line.strip()
                if stripped:
                    lines.append(stripped)
            return '\n'.join(lines)
        except Exception as e:
            return f"压缩代码错误: {e}"