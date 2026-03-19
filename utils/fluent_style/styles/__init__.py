"""
QSS 样式片段自动加载模块
"""

import os
import re
from ..registry import QssRegistry

# 样式文件加载顺序（对应文件名，不含 .qss 扩展名）
_STYLE_FILES = [
    'base',           # 基础设置
    'custom',         # 自定义样式（可覆盖）
    'label',          # 标签
    'button',         # 按钮
    'input',          # 输入控件
    'spinbox',        # 数值选择
    'combobox',       # 下拉框
    'checkbox',       # 复选框
    'radio',          # 单选按钮
    'slider',         # 滑块
    'progress',       # 进度条
    'menu',           # 菜单
    'toolbar',        # 工具栏
    'scrollbar',      # 滚动条
    'tab',            # 标签页
    'groupbox',       # 分组框
    'frame',          # 框架
    'list',           # 列表视图
    'header',         # 表头
    'splitter',       # 分割器
    'dialog',         # 对话框
    'statusbar',      # 状态栏
    'tooltip',        # 工具提示
    'dock',           # 停靠窗口
    'mainwindow',     # 主窗口
]


def _remove_comments(qss: str) -> str:
    """移除 QSS 注释，避免编码问题"""
    # 移除 /* ... */ 块注释
    qss = re.sub(r'/\*.*?\*/', '', qss, flags=re.DOTALL)
    # 移除单行注释
    lines = []
    for line in qss.split('\n'):
        # 移除 // 注释
        if '//' in line:
            line = line[:line.index('//')]
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
            # 根据文件名确定优先级
            priority = _STYLE_FILES.index(style_name) * 10
            QssRegistry.register(style_name, qss_content, priority)


# 模块加载时自动初始化样式
init_styles()
