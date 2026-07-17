"""
QSS 样式片段自动加载模块
"""

import os
import re
from ..registry import QssRegistry

# 样式文件加载顺序（对应文件名，不含 .qss 扩展名）
# 唯一事实来源是 QssRegistry._STYLE_PRIORITIES，此处仅做推导；新增样式文件只需在 registry 登记
_STYLE_FILES = QssRegistry.style_file_order()


def _remove_comments(qss: str) -> str:
    """
    移除 QSS 注释，避免编码问题

    仅移除 /* ... */ 块注释、行首 // 注释（stripped 以 // 开头）以及
    前置空白的行内 // 注释；url(http://...) 等 :// 形式不受影响。
    """
    # 移除 /* ... */ 块注释
    qss = re.sub(r'/\*.*?\*/', '', qss, flags=re.DOTALL)
    # 移除单行注释
    lines = []
    for line in qss.split('\n'):
        # 行首注释：stripped 以 // 开头
        if line.lstrip().startswith('//'):
            lines.append('')
            continue
        # 行内注释：// 前置空白（url 中的 :// 前面是冒号，不会命中）
        m = re.search(r'\s//', line)
        if m:
            line = line[:m.start()]
        lines.append(line)
    return '\n'.join(lines)


def _load_qss_file(file_path: str) -> str:
    """加载单个 QSS 文件"""
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            content = f.read()
            # 移除注释
            return _remove_comments(content)
    except Exception as e:
        print(f"Warning: Failed to load {file_path}: {e}")
        return ''


def init_styles():
    """初始化并注册所有样式文件"""
    # 获取当前模块目录
    styles_dir = os.path.dirname(__file__)

    for style_name in _STYLE_FILES:
        file_path = os.path.join(styles_dir, f'{style_name}.qss')
        if os.path.exists(file_path):
            qss_content = _load_qss_file(file_path)
            # 优先级由 registry 单一事实来源推导
            QssRegistry.register(style_name, qss_content, QssRegistry._get_priority(style_name))


# 模块加载时自动初始化样式
init_styles()
