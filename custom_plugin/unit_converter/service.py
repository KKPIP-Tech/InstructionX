"""
单位转换服务
"""


class Service:
    """单位转换服务"""
    
    def length_converter(self, value: float, from_unit: str, to_unit: str) -> float:
        """
        长度单位转换
        
        Args:
            value: 数值
            from_unit: 源单位 (m, km, cm, mm, inch, ft)
            to_unit: 目标单位
            
        Returns:
            转换后的数值
        """
        # 先转换为米
        to_meter = {
            'm': 1,
            'km': 1000,
            'cm': 0.01,
            'mm': 0.001,
            'inch': 0.0254,
            'ft': 0.3048
        }
        
        value_in_meters = value * to_meter.get(from_unit, 1)
        
        # 从米转换为目标单位
        return value_in_meters / to_meter.get(to_unit, 1)
    
    def weight_converter(self, value: float, from_unit: str, to_unit: str) -> float:
        """
        重量单位转换
        
        Args:
            value: 数值
            from_unit: 源单位 (kg, g, mg, lb, oz)
            to_unit: 目标单位
            
        Returns:
            转换后的数值
        """
        # 先转换为千克
        to_kg = {
            'kg': 1,
            'g': 0.001,
            'mg': 0.000001,
            'lb': 0.453592,
            'oz': 0.0283495
        }
        
        value_in_kg = value * to_kg.get(from_unit, 1)
        
        # 从千克转换为目标单位
        return value_in_kg / to_kg.get(to_unit, 1)
    
    def temperature_converter(self, value: float, from_unit: str, to_unit: str) -> float:
        """
        温度单位转换
        
        Args:
            value: 数值
            from_unit: 源单位 (C, F, K)
            to_unit: 目标单位
            
        Returns:
            转换后的数值
        """
        # 先转换为摄氏度
        if from_unit == 'C':
            value_in_c = value
        elif from_unit == 'F':
            value_in_c = (value - 32) * 5 / 9
        elif from_unit == 'K':
            value_in_c = value - 273.15
        else:
            value_in_c = value
        
        # 从摄氏度转换为目标单位
        if to_unit == 'C':
            return value_in_c
        elif to_unit == 'F':
            return value_in_c * 9 / 5 + 32
        elif to_unit == 'K':
            return value_in_c + 273.15
        else:
            return value_in_c