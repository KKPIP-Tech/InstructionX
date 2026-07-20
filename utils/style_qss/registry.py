"""
QSS 注册表 - 管理和聚合所有 QSS 片段
"""

import os
from typing import Dict, List
from .colors import get_color_dict


class QssRegistry:
    """QSS 注册表，管理所有样式片段"""

    # 存储所有注册的样式片段
    _styles: Dict[str, str] = {}

    # 加载顺序（基础 -> 控件 -> 容器 -> 窗口）
    _load_order: List[str] = []

    # 内置样式优先级（唯一事实来源，styles/ 目录的加载顺序由此推导；
    # 新增样式文件只需在此登记一处）
    _STYLE_PRIORITIES: Dict[str, int] = {
        'base': 10,
        'custom': 20,
        'label': 30,
        'button': 40,
        'input': 50,
        'spinbox': 55,
        'combobox': 60,
        'checkbox': 70,
        'radio': 71,
        'slider': 72,
        'progress': 73,
        'menu': 80,
        'toolbar': 81,
        'scrollbar': 82,
        'tab': 83,
        'groupbox': 84,
        'frame': 85,
        'list': 86,
        'header': 87,
        'splitter': 88,
        'dialog': 90,
        'statusbar': 91,
        'tooltip': 92,
        'dock': 93,
        'mainwindow': 100,
        'titlebar': 101,
        'usage_panel': 102,
    }

    @classmethod
    def register(cls, name: str, qss: str, priority: int = 50):
        """
        注册一个 QSS 片段

        Args:
            name: 样式名称
            qss: QSS 内容
            priority: 优先级，数字越小越先加载
        """
        cls._styles[name] = qss
        # 保持加载顺序
        if name not in cls._load_order:
            # 按优先级插入
            inserted = False
            for i, existing_name in enumerate(cls._load_order):
                if priority < cls._get_priority(existing_name):
                    cls._load_order.insert(i, name)
                    inserted = True
                    break
            if not inserted:
                cls._load_order.append(name)

    @classmethod
    def _get_priority(cls, name: str) -> int:
        """获取样式优先级（未登记名称默认为 50）"""
        return cls._STYLE_PRIORITIES.get(name, 50)

    @classmethod
    def style_file_order(cls) -> List[str]:
        """返回内置样式文件的加载顺序（按优先级升序）"""
        return [name for name, _ in sorted(cls._STYLE_PRIORITIES.items(), key=lambda kv: kv[1])]

    @classmethod
    def get_all(cls, theme: str = 'light') -> str:
        """
        获取所有注册的 QSS，并替换颜色变量

        Args:
            theme: 主题类型，'light' 或 'dark'

        Returns:
            完整的 QSS 字符串
        """
        colors = get_color_dict(theme)

        # 按顺序拼接所有 QSS
        qss_parts = []

        for name in cls._load_order:
            if name in cls._styles:
                qss_parts.append(cls._styles[name])

        # 合并所有 QSS
        full_qss = '\n\n'.join(qss_parts)

        # 替换颜色变量
        full_qss = cls._replace_variables(full_qss, colors)

        return full_qss

    @classmethod
    def _replace_variables(cls, qss: str, colors: dict) -> str:
        """替换 QSS 中的变量"""
        # 替换 {key} 格式的变量
        for key, value in colors.items():
            qss = qss.replace(f'{{{key}}}', value)
        return qss

    @classmethod
    def clear(cls):
        """清空所有注册的样式"""
        cls._styles.clear()
        cls._load_order.clear()

    @classmethod
    def get(cls, name: str) -> str:
        """获取指定名称的 QSS"""
        return cls._styles.get(name, '')

    @classmethod
    def apply_variables(cls, qss: str, theme: str = None) -> str:
        """
        对给定的 QSS 字符串替换颜色变量

        Args:
            qss: 包含 {variable} 的 QSS 字符串
            theme: 主题类型，None 则使用当前全局主题

        Returns:
            变量替换后的 QSS 字符串
        """
        if theme is None:
            # NOTE: 函数级导入用于打破 utils.style_qss ↔ utils.style_qss.registry
            # 循环依赖（包级 __init__ 顶部导入本模块，而 get_style_qss 定义在
            # 包级 __init__ 中），无法上移为顶部导入。
            from . import get_style_qss
            theme = get_style_qss().theme()
        colors = get_color_dict(theme)
        return cls._replace_variables(qss, colors)


def register_styles():
    """自动注册所有样式文件"""
    from . import styles
    styles.init_styles()
