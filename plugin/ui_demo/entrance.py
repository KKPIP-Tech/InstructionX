"""
UI 控件演示插件 - 最终修复方案（不干扰样式）

展示所有控件效果
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QTextEdit, QPlainTextEdit,
    QComboBox, QCheckBox, QRadioButton, QSlider, QProgressBar,
    QSpinBox, QDoubleSpinBox, QGroupBox, QTabWidget, QListWidget,
    QTableWidget, QTreeWidget, QMenuBar, QMenu, QToolBar,
    QToolButton, QScrollArea, QFrame, QSplitter, QStackedWidget,
    QButtonGroup, QListWidgetItem, QTableWidgetItem, QTreeWidgetItem,
    QScrollBar, QStatusBar, QDialogButtonBox, QSizePolicy, QStyle,
    QMessageBox, QStyleOptionSlider
)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QAction, QIcon, QColor
from core.plugin.plugin_interface import IPlugin
from .service import Service


class UiDemoPlugin(IPlugin):
    """UI 控件演示插件"""

    def __init__(self):
        """初始化插件"""
        super().__init__()
        self.progress_bar = None
        self._timer = None
        self._progress_step = 0
        self.radio_group = None

    @property
    def plugin_name(self) -> str:
        return "UI\n演示"

    def _create_widget(self, parent=None, data_provider=None) -> QWidget:
        """创建插件控件"""
        service = Service()

        # 主容器 - 使用滚动区域
        widget = QWidget(parent)
        main_layout = QVBoxLayout(widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        # 滚动内容容器
        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout(scroll_content)
        scroll_content_layout.setContentsMargins(10, 10, 10, 10)
        scroll_content_layout.setSpacing(10)

        # 创建标签页
        tab_widget = QTabWidget()
        tab_widget.setDocumentMode(True)

        # ========== 基础控件页面 ==========
        basic_tab = self._create_basic_controls_tab()
        tab_widget.addTab(basic_tab, "基础控件")

        # ========== 输入控件页面 ==========
        input_tab = self._create_input_controls_tab()
        tab_widget.addTab(input_tab, "输入控件")

        # ========== 容器控件页面 ==========
        container_tab = self._create_container_controls_tab()
        tab_widget.addTab(container_tab, "容器控件")

        # ========== 列表控件页面 ==========
        list_tab = self._create_list_controls_tab()
        tab_widget.addTab(list_tab, "列表控件")

        # ========== 菜单工具栏页面 ==========
        menu_tab = self._create_menu_toolbar_tab(parent)
        tab_widget.addTab(menu_tab, "菜单工具栏")

        scroll_content_layout.addWidget(tab_widget)

        # 状态栏
        status_bar = QStatusBar()
        status_bar.showMessage("就绪 - 控件演示")
        scroll_content_layout.addWidget(status_bar)

        # 设置滚动区域的内容
        scroll_area.setWidget(scroll_content)

        main_layout.addWidget(scroll_area)

        return widget

    def _create_basic_controls_tab(self) -> QWidget:
        """创建基础控件页面（含滑块调试功能）"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(15)

        # 标题
        title = QLabel("基础控件演示")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        # 按钮组
        button_group = QGroupBox("按钮 (QPushButton)")
        button_layout = QVBoxLayout()

        # 普通按钮
        row1 = QHBoxLayout()
        normal_btn = QPushButton("普通按钮")
        normal_btn.clicked.connect(lambda: self._show_message("普通按钮点击"))
        row1.addWidget(normal_btn)

        primary_btn = QPushButton("主要按钮")
        primary_btn.setProperty("class", "primary")
        primary_btn.clicked.connect(lambda: self._show_message("主要按钮点击"))
        row1.addWidget(primary_btn)

        danger_btn = QPushButton("危险按钮")
        danger_btn.setProperty("class", "danger")
        danger_btn.clicked.connect(lambda: self._show_message("危险按钮点击"))
        row1.addWidget(danger_btn)

        success_btn = QPushButton("成功按钮")
        success_btn.setProperty("class", "success")
        success_btn.clicked.connect(lambda: self._show_message("成功按钮点击"))
        row1.addWidget(success_btn)
        button_layout.addLayout(row1)

        # 第二行按钮
        row2 = QHBoxLayout()
        outline_btn = QPushButton("轮廓按钮")
        outline_btn.setProperty("class", "outline")
        outline_btn.clicked.connect(lambda: self._show_message("轮廓按钮点击"))
        row2.addWidget(outline_btn)

        subtle_btn = QPushButton("柔和按钮")
        subtle_btn.setProperty("class", "subtle")
        subtle_btn.clicked.connect(lambda: self._show_message("柔和按钮点击"))
        row2.addWidget(subtle_btn)

        disabled_btn = QPushButton("禁用按钮")
        disabled_btn.setEnabled(False)
        row2.addWidget(disabled_btn)

        row2.addStretch()
        button_layout.addLayout(row2)
        button_group.setLayout(button_layout)
        layout.addWidget(button_group)

        # 复选框和单选按钮
        checkbox_group = QGroupBox("复选框 (QCheckBox) 和 单选按钮 (QRadioButton)")
        checkbox_layout = QHBoxLayout()

        # 复选框
        check1 = QCheckBox("复选框 1")
        check1.setChecked(True)
        checkbox_layout.addWidget(check1)

        check2 = QCheckBox("复选框 2")
        checkbox_layout.addWidget(check2)

        check3 = QCheckBox("半选状态")
        check3.setTristate(True)
        check3.setCheckState(Qt.CheckState.PartiallyChecked)
        checkbox_layout.addWidget(check3)

        checkbox_layout.addSpacing(30)

        # 单选按钮
        self.radio_group = QButtonGroup(widget)
        radio1 = QRadioButton("选项 A")
        radio1.setChecked(True)
        radio2 = QRadioButton("选项 B")
        radio3 = QRadioButton("选项 C")
        self.radio_group.addButton(radio1)
        self.radio_group.addButton(radio2)
        self.radio_group.addButton(radio3)
        checkbox_layout.addWidget(radio1)
        checkbox_layout.addWidget(radio2)
        checkbox_layout.addWidget(radio3)

        checkbox_layout.addStretch()
        checkbox_group.setLayout(checkbox_layout)
        layout.addWidget(checkbox_group)

        # ═══════════════════════════════════════════════════════════════════════
        # 滑块和进度条 - 【最终方案：不设置尺寸，让样式完全控制】
        # ═══════════════════════════════════════════════════════════════════════
        slider_group = QGroupBox("滑块 (QSlider) 和 进度条 (QProgressBar)")
        slider_layout = QGridLayout()
        slider_layout.setColumnStretch(1, 1)
        # 【关键】增加行间距，给滑块上下留空间
        slider_layout.setRowMinimumHeight(0, 40)
        slider_layout.setRowMinimumHeight(1, 40)

        # ═══════════════════════════════════════════════════════════════════════
        # 【关键修复 1】水平滑块 - 不设置任何尺寸限制
        # ═══════════════════════════════════════════════════════════════════════
        h_slider = QSlider(Qt.Orientation.Horizontal)
        h_slider.setMinimum(0)
        h_slider.setMaximum(100)
        h_slider.setValue(50)
        # ❌ 删除所有 setMinimumHeight/setMaximumHeight
        # ❌ 删除 setSizePolicy
        # ✅ 让样式完全控制
        slider_layout.addWidget(QLabel("水平滑块:"), 0, 0)
        slider_layout.addWidget(h_slider, 0, 1)

        # ═══════════════════════════════════════════════════════════════════════
        # 【关键修复 2】垂直滑块 - 只设置最小宽度，不限制高度
        # ═══════════════════════════════════════════════════════════════════════
        v_slider = QSlider(Qt.Orientation.Vertical)
        v_slider.setMinimum(0)
        v_slider.setMaximum(100)
        v_slider.setValue(50)
        # ✅ 只设置一个合理的最小宽度
        v_slider.setMinimumWidth(32)
        # ❌ 不设置 maximumWidth
        # ❌ 不设置 minimumHeight（让布局决定）
        slider_layout.addWidget(QLabel("垂直滑块:"), 0, 2)
        slider_layout.addWidget(v_slider, 0, 3, 3, 1)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(60)
        slider_layout.addWidget(QLabel("进度条:"), 1, 0)
        slider_layout.addWidget(self.progress_bar, 1, 1)

        # 进度条控制按钮
        progress_btn_layout = QHBoxLayout()
        decrease_btn = QPushButton("-10")
        decrease_btn.clicked.connect(lambda: self._adjust_progress(-10))
        progress_btn_layout.addWidget(decrease_btn)

        increase_btn = QPushButton("+10")
        increase_btn.clicked.connect(lambda: self._adjust_progress(10))
        progress_btn_layout.addWidget(increase_btn)

        animate_btn = QPushButton("动画")
        animate_btn.clicked.connect(self._animate_progress)
        progress_btn_layout.addWidget(animate_btn)

        slider_layout.addLayout(progress_btn_layout, 2, 1)
        slider_group.setLayout(slider_layout)
        layout.addWidget(slider_group)

        # ═══════════════════════════════════════════════════════════════════════
        # 【调试按钮】点击打印滑块尺寸信息
        # ═══════════════════════════════════════════════════════════════════════
        debug_btn = QPushButton("🔍 调试：打印滑块尺寸信息")
        debug_btn.clicked.connect(
            lambda: self._debug_slider_info(h_slider, v_slider)
        )
        layout.addWidget(debug_btn)

        # 【自动调试】窗口显示后 500ms 自动打印一次调试信息
        def auto_debug():
            self._debug_slider_info(h_slider, v_slider)
        QTimer.singleShot(500, auto_debug)

        layout.addStretch()
        return widget

    def _debug_slider_info(self, h_slider: QSlider, v_slider: QSlider):
        """
        打印滑块调试信息到控制台
        
        Args:
            h_slider: 水平滑块实例
            v_slider: 垂直滑块实例
        """
        print("\n" + "=" * 70)
        print("[DEBUG] 滑块尺寸调试信息")
        print("=" * 70)
        
        # 水平滑块信息
        print("\n【水平滑块】")
        print(f"  geometry:      {h_slider.geometry()}")
        print(f"  rect:          {h_slider.rect()}")
        print(f"  sizeHint:      {h_slider.sizeHint()}")
        print(f"  minimumHeight: {h_slider.minimumHeight()}px")
        print(f"  height:        {h_slider.height()}px")
        
        # 创建样式选项并初始化
        h_option = QStyleOptionSlider()
        h_option.initFrom(h_slider)
        h_option.orientation = Qt.Orientation.Horizontal
        h_option.minimum = h_slider.minimum()
        h_option.maximum = h_slider.maximum()
        h_option.sliderPosition = h_slider.sliderPosition()
        h_option.sliderValue = h_slider.value()
        h_option.upsideDown = h_slider.invertedAppearance()
        
        # 获取各个区域的尺寸
        h_groove_rect = h_slider.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            h_option,
            QStyle.SubControl.SC_SliderGroove,
            h_slider
        )
        h_handle_rect = h_slider.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            h_option,
            QStyle.SubControl.SC_SliderHandle,
            h_slider
        )
        
        print(f"  groove rect:   {h_groove_rect}")
        print(f"  groove height: {h_groove_rect.height()}px")
        print(f"  handle rect:   {h_handle_rect}")
        print(f"  handle size:   {h_handle_rect.width()}x{h_handle_rect.height()}px")
        
        # 垂直滑块信息
        print("\n【垂直滑块】")
        print(f"  geometry:      {v_slider.geometry()}")
        print(f"  rect:          {v_slider.rect()}")
        print(f"  sizeHint:      {v_slider.sizeHint()}")
        print(f"  minimumWidth:  {v_slider.minimumWidth()}px")
        print(f"  width:         {v_slider.width()}px")
        print(f"  height:        {v_slider.height()}px")
        
        # 创建样式选项并初始化
        v_option = QStyleOptionSlider()
        v_option.initFrom(v_slider)
        v_option.orientation = Qt.Orientation.Vertical
        v_option.minimum = v_slider.minimum()
        v_option.maximum = v_slider.maximum()
        v_option.sliderPosition = v_slider.sliderPosition()
        v_option.sliderValue = v_slider.value()
        v_option.upsideDown = v_slider.invertedAppearance()
        
        # 获取各个区域的尺寸
        v_groove_rect = v_slider.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            v_option,
            QStyle.SubControl.SC_SliderGroove,
            v_slider
        )
        v_handle_rect = v_slider.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            v_option,
            QStyle.SubControl.SC_SliderHandle,
            v_slider
        )
        
        print(f"  groove rect:   {v_groove_rect}")
        print(f"  groove width:  {v_groove_rect.width()}px")
        print(f"  handle rect:   {v_handle_rect}")
        print(f"  handle size:   {v_handle_rect.width()}x{v_handle_rect.height()}px")
        
        # 截断检查
        print("\n【截断检查】")
        h_clipped = h_handle_rect.top() < 0 or h_handle_rect.bottom() > h_slider.height()
        v_clipped = v_handle_rect.left() < 0 or v_handle_rect.right() > v_slider.width()
        
        if h_clipped:
            print(f"  ⚠️  水平滑块 handle 可能截断")
        else:
            print(f"  ✅ 水平滑块 handle 无截断")
        
        if v_clipped:
            print(f"  ⚠️  垂直滑块 handle 可能截断")
        else:
            print(f"  ✅ 垂直滑块 handle 无截断")
        
        print("=" * 70 + "\n")

    def _create_input_controls_tab(self) -> QWidget:
        """创建输入控件页面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(15)

        # 标题
        title = QLabel("输入控件演示")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        # 单行输入框
        line_edit_group = QGroupBox("单行输入框 (QLineEdit)")
        line_edit_layout = QVBoxLayout()

        normal_input = QLineEdit()
        normal_input.setPlaceholderText("普通输入框...")
        line_edit_layout.addWidget(normal_input)

        password_input = QLineEdit()
        password_input.setPlaceholderText("密码输入框...")
        password_input.setEchoMode(QLineEdit.EchoMode.Password)
        line_edit_layout.addWidget(password_input)

        read_only_input = QLineEdit()
        read_only_input.setText("只读输入框")
        read_only_input.setReadOnly(True)
        line_edit_layout.addWidget(read_only_input)

        line_edit_group.setLayout(line_edit_layout)
        layout.addWidget(line_edit_group)

        # 多行文本编辑
        text_edit_group = QGroupBox("文本编辑 (QTextEdit / QPlainTextEdit)")
        text_edit_layout = QVBoxLayout()

        text_edit = QTextEdit()
        text_edit.setPlaceholderText("这是一个 QTextEdit，可编辑富文本...")
        text_edit_layout.addWidget(text_edit)

        plain_text_edit = QPlainTextEdit()
        plain_text_edit.setPlaceholderText("这是一个 QPlainTextEdit，纯文本...")
        text_edit_layout.addWidget(plain_text_edit)

        text_edit_group.setLayout(text_edit_layout)
        layout.addWidget(text_edit_group)

        # 数值选择框
        spin_group = QGroupBox("数值选择框 (QSpinBox / QDoubleSpinBox)")
        spin_layout = QHBoxLayout()

        spin_box = QSpinBox()
        spin_box.setRange(0, 100)
        spin_box.setValue(50)
        spin_layout.addWidget(QLabel("整数:"))
        spin_layout.addWidget(spin_box)

        double_spin = QDoubleSpinBox()
        double_spin.setRange(0.0, 100.0)
        double_spin.setValue(50.5)
        double_spin.setDecimals(2)
        spin_layout.addWidget(QLabel("浮点数:"))
        spin_layout.addWidget(double_spin)

        spin_layout.addStretch()
        spin_group.setLayout(spin_layout)
        layout.addWidget(spin_group)

        # 下拉框
        combo_group = QGroupBox("下拉框 (QComboBox)")
        combo_layout = QVBoxLayout()

        combo = QComboBox()
        combo.addItems(["选项 1", "选项 2", "选项 3", "选项 4", "选项 5"])
        combo.setCurrentIndex(0)
        combo_layout.addWidget(combo)

        editable_combo = QComboBox()
        editable_combo.setEditable(True)
        editable_combo.addItems(["可编辑 1", "可编辑 2", "可编辑 3"])
        combo_layout.addWidget(editable_combo)

        combo_group.setLayout(combo_layout)
        layout.addWidget(combo_group)

        layout.addStretch()
        return widget

    def _create_container_controls_tab(self) -> QWidget:
        """创建容器控件页面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(15)

        # 标题
        title = QLabel("容器控件演示")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        # 标签页
        tab_group = QGroupBox("标签页 (QTabWidget)")
        tab_layout = QVBoxLayout()

        tab_widget = QTabWidget()

        # 标签页 1
        page1 = QWidget()
        page1_layout = QVBoxLayout()
        page1_layout.addWidget(QLabel("这是标签页 1 的内容"))
        page1_layout.addWidget(QPushButton("标签页按钮"))
        page1_layout.addStretch()
        page1.setLayout(page1_layout)
        tab_widget.addTab(page1, "页面 1")

        # 标签页 2
        page2 = QWidget()
        page2_layout = QVBoxLayout()
        page2_layout.addWidget(QLabel("这是标签页 2 的内容"))
        page2_layout.addWidget(QComboBox())
        page2_layout.addStretch()
        page2.setLayout(page2_layout)
        tab_widget.addTab(page2, "页面 2")

        # 标签页 3
        page3 = QWidget()
        page3_layout = QVBoxLayout()
        page3_layout.addWidget(QLabel("这是标签页 3 的内容"))
        inner_slider = QSlider(Qt.Orientation.Horizontal)
        # ✅ 不设置任何尺寸
        page3_layout.addWidget(inner_slider)
        page3_layout.addStretch()
        page3.setLayout(page3_layout)
        tab_widget.addTab(page3, "页面 3")

        tab_layout.addWidget(tab_widget)
        tab_group.setLayout(tab_layout)
        layout.addWidget(tab_group)

        # 分组框
        group_layout = QHBoxLayout()

        # 复选框分组框
        checkable_group = QGroupBox("可折叠分组框")
        checkable_group.setCheckable(True)
        checkable_group.setChecked(True)
        checkable_layout = QVBoxLayout()
        checkable_layout.addWidget(QCheckBox("选项 A"))
        checkable_layout.addWidget(QCheckBox("选项 B"))
        checkable_layout.addWidget(QCheckBox("选项 C"))
        checkable_group.setLayout(checkable_layout)
        group_layout.addWidget(checkable_group)

        # 普通分组框
        normal_group = QGroupBox("普通分组框")
        normal_layout = QVBoxLayout()
        normal_layout.addWidget(QLabel("分组框内容"))
        normal_layout.addWidget(QPushButton("分组框按钮"))
        normal_group.setLayout(normal_layout)
        group_layout.addWidget(normal_group)

        layout.addLayout(group_layout)

        # 滚动区域
        scroll_group = QGroupBox("滚动区域 (QScrollArea)")
        scroll_layout = QVBoxLayout()

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_inner_layout = QVBoxLayout()
        for i in range(10):
            scroll_inner_layout.addWidget(QPushButton(f"滚动区域按钮 {i+1}"))
        scroll_inner_layout.addStretch()
        scroll_widget.setLayout(scroll_inner_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_layout.addWidget(scroll_area)
        scroll_group.setLayout(scroll_layout)
        layout.addWidget(scroll_group)

        layout.addStretch()
        return widget

    def _create_list_controls_tab(self) -> QWidget:
        """创建列表控件页面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(15)

        # 标题
        title = QLabel("列表控件演示")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        # 列表视图
        list_group = QGroupBox("列表视图 (QListWidget)")
        list_layout = QVBoxLayout()

        list_widget = QListWidget()
        list_widget.addItems([
            "列表项 1", "列表项 2", "列表项 3",
            "列表项 4", "列表项 5", "列表项 6"
        ])
        list_widget.setCurrentRow(0)
        list_layout.addWidget(list_widget)
        list_group.setLayout(list_layout)
        layout.addWidget(list_group)

        # 表格视图和树视图
        table_tree_layout = QHBoxLayout()

        # 树视图
        tree_group = QGroupBox("树视图 (QTreeWidget)")
        tree_layout = QVBoxLayout()

        tree_widget = QTreeWidget()
        tree_widget.setHeaderLabels(["名称", "描述"])
        root1 = QTreeWidgetItem(["根节点 1", "这是根节点 1"])
        root1.addChild(QTreeWidgetItem(["子节点 1.1", "子节点"]))
        root1.addChild(QTreeWidgetItem(["子节点 1.2", "子节点"]))
        root2 = QTreeWidgetItem(["根节点 2", "这是根节点 2"])
        root2.addChild(QTreeWidgetItem(["子节点 2.1", "子节点"]))
        tree_widget.addTopLevelItem(root1)
        tree_widget.addTopLevelItem(root2)
        tree_widget.expandAll()
        tree_layout.addWidget(tree_widget)
        tree_group.setLayout(tree_layout)
        table_tree_layout.addWidget(tree_group)

        # 表格视图
        table_group = QGroupBox("表格视图 (QTableWidget)")
        table_layout = QVBoxLayout()

        table_widget = QTableWidget(5, 3)
        table_widget.setHorizontalHeaderLabels(["列 1", "列 2", "列 3"])
        for i in range(5):
            for j in range(3):
                table_widget.setItem(i, j, QTableWidgetItem(f"单元格 {i+1},{j+1}"))
        table_layout.addWidget(table_widget)
        table_group.setLayout(table_layout)
        table_tree_layout.addWidget(table_group)

        layout.addLayout(table_tree_layout)

        layout.addStretch()
        return widget

    def _create_menu_toolbar_tab(self, parent=None) -> QWidget:
        """创建菜单和工具栏页面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(15)

        # 标题
        title = QLabel("菜单和工具栏演示")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        # 菜单栏演示
        menu_group = QGroupBox("菜单栏 (QMenuBar)")
        menu_layout = QVBoxLayout()

        menu_bar = QMenuBar()

        # 文件菜单
        file_menu = QMenu("文件 (&F)")
        file_menu.addAction("新建", lambda: self._show_message("新建文件"))
        file_menu.addAction("打开", lambda: self._show_message("打开文件"))
        file_menu.addSeparator()
        file_menu.addAction("保存", lambda: self._show_message("保存文件"))
        file_menu.addAction("另存为", lambda: self._show_message("另存文件"))
        file_menu.addSeparator()
        file_menu.addAction("退出", lambda: self._show_message("退出"))
        menu_bar.addMenu(file_menu)

        # 编辑菜单
        edit_menu = QMenu("编辑 (&E)")
        edit_menu.addAction("撤销", lambda: self._show_message("撤销"))
        edit_menu.addAction("重做", lambda: self._show_message("重做"))
        edit_menu.addSeparator()
        edit_menu.addAction("剪切", lambda: self._show_message("剪切"))
        edit_menu.addAction("复制", lambda: self._show_message("复制"))
        edit_menu.addAction("粘贴", lambda: self._show_message("粘贴"))
        menu_bar.addMenu(edit_menu)

        # 视图菜单
        view_menu = QMenu("视图 (&V)")
        view_menu.addAction("全屏", lambda: self._show_message("全屏"))
        view_menu.addAction("放大", lambda: self._show_message("放大"))
        view_menu.addAction("缩小", lambda: self._show_message("缩小"))
        menu_bar.addMenu(view_menu)

        # 帮助菜单
        help_menu = QMenu("帮助 (&H)")
        help_menu.addAction("关于", lambda: self._show_message("关于"))
        help_menu.addAction("文档", lambda: self._show_message("文档"))
        menu_bar.addMenu(help_menu)

        menu_layout.addWidget(menu_bar)
        menu_group.setLayout(menu_layout)
        layout.addWidget(menu_group)

        # 工具栏演示
        toolbar_group = QGroupBox("工具栏 (QToolBar)")
        toolbar_layout = QVBoxLayout()

        toolbar = QToolBar()
        toolbar.setMovable(False)

        toolbar.addAction("新建", lambda: self._show_message("新建"))
        toolbar.addAction("打开", lambda: self._show_message("打开"))
        toolbar.addAction("保存", lambda: self._show_message("保存"))
        toolbar.addSeparator()

        action1 = QAction("设置", toolbar)
        toolbar.addAction(action1)
        toolbar.addAction("帮助", lambda: self._show_message("帮助"))

        toolbar_layout.addWidget(toolbar)
        toolbar_group.setLayout(toolbar_layout)
        layout.addWidget(toolbar_group)

        # 分割器演示
        splitter_group = QGroupBox("分割器 (QSplitter)")
        splitter_layout = QVBoxLayout()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(QPushButton("面板 1"))
        splitter.addWidget(QPushButton("面板 2"))
        splitter.addWidget(QPushButton("面板 3"))
        splitter_layout.addWidget(splitter)
        splitter_group.setLayout(splitter_layout)
        layout.addWidget(splitter_group)

        layout.addStretch()
        return widget

    def _show_message(self, message: str):
        """显示消息"""
        QMessageBox.information(None, "提示", message)

    def _adjust_progress(self, delta: int):
        """调整进度条"""
        if self.progress_bar is None:
            return
        new_value = self.progress_bar.value() + delta
        new_value = max(0, min(100, new_value))
        self.progress_bar.setValue(new_value)

    def _animate_progress(self):
        """动画进度条"""
        if self._timer is not None:
            self._timer.stop()
        self._progress_step = 0
        self._timer = QTimer()
        self._timer.timeout.connect(self._update_progress)
        self._timer.start(50)

    def _update_progress(self):
        """更新进度条"""
        if self.progress_bar is None:
            return
        self._progress_step += 1
        if self._progress_step > 100:
            if self._timer is not None:
                self._timer.stop()
            self._progress_step = 0
        else:
            self.progress_bar.setValue(self._progress_step)