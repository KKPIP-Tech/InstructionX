"""
UI 演示插件服务
"""


class Service:
    """UI 演示服务类"""

    def __init__(self):
        self.control_list = [
            "QPushButton - 按钮",
            "QLineEdit - 单行输入框",
            "QTextEdit - 富文本编辑",
            "QPlainTextEdit - 纯文本编辑",
            "QComboBox - 下拉框",
            "QCheckBox - 复选框",
            "QRadioButton - 单选按钮",
            "QSlider - 滑块",
            "QProgressBar - 进度条",
            "QSpinBox - 整数选择框",
            "QDoubleSpinBox - 浮点数选择框",
            "QGroupBox - 分组框",
            "QTabWidget - 标签页",
            "QListWidget - 列表视图",
            "QTableWidget - 表格视图",
            "QTreeWidget - 树视图",
            "QMenuBar - 菜单栏",
            "QMenu - 菜单",
            "QToolBar - 工具栏",
            "QScrollArea - 滚动区域",
            "QSplitter - 分割器",
            "QStackedWidget - 堆叠窗口",
            "QFrame - 框架",
        ]

    def get_control_list(self) -> list:
        """获取所有可演示的控件列表"""
        return self.control_list
