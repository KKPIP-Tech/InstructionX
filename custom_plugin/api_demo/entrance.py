"""
API 调用演示插件 - UI 界面入口
展示如何使用 PluginManager 调用其他插件的 API
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QGroupBox, QTextEdit,
    QListWidget, QSplitter, QMessageBox
)
from PySide6.QtCore import Qt
from core.plugin.plugin_interface import IPlugin
from core.plugin.manager import PluginManager


class ApiDemoPlugin(IPlugin):
    """API 调用演示插件"""
    
    def __init__(self):
        super().__init__()
        self.plugin_manager = PluginManager()
        self.my_plugin_id = "api-demo"
    
    @property
    def plugin_name(self) -> str:
        return "API 调用\n演示"
    
    def get_widget(self, parent=None, data_provider=None) -> QWidget:
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        
        # 标题和说明
        title = QLabel("API 调用演示")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        desc = QLabel("此插件演示如何通过 PluginManager 调用其他插件（字符串工具）的 API 方法。")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666; margin: 5px 10px;")
        layout.addWidget(desc)
        
        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧：API 列表
        left_panel = self._create_api_list_panel()
        splitter.addWidget(left_panel)
        
        # 右侧：输入输出和结果显示
        right_panel = self._create_io_panel()
        splitter.addWidget(right_panel)
        
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)
        
        return widget
    
    def _create_api_list_panel(self) -> QWidget:
        """创建 API 列表面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # API 列表组
        group = QGroupBox("可用 API 方法")
        list_layout = QVBoxLayout()
        
        # 刷新按钮
        refresh_btn = QPushButton("刷新 API 列表")
        refresh_btn.clicked.connect(self._refresh_api_list)
        list_layout.addWidget(refresh_btn)
        
        # API 列表
        self.api_list = QListWidget()
        self.api_list.itemClicked.connect(self._on_api_selected)
        list_layout.addWidget(self.api_list)
        
        # 查看所有插件 API 按钮
        view_all_btn = QPushButton("查看所有插件 API")
        view_all_btn.clicked.connect(self._show_all_apis)
        list_layout.addWidget(view_all_btn)
        
        # 查看 Function Tools 按钮
        view_tools_btn = QPushButton("查看 Function Tools")
        view_tools_btn.clicked.connect(self._show_function_tools)
        list_layout.addWidget(view_tools_btn)
        
        group.setLayout(list_layout)
        layout.addWidget(group)
        
        # 加载初始 API 列表
        self._refresh_api_list()
        
        return panel
    
    def _create_io_panel(self) -> QWidget:
        """创建输入输出面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # 输入区域
        input_group = QGroupBox("输入参数")
        input_layout = QVBoxLayout()
        
        self.input_label = QLabel("请选择一个 API 方法...")
        input_layout.addWidget(self.input_label)
        
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("在此输入要处理的文本...")
        self.input_text.setMinimumHeight(80)
        input_layout.addWidget(self.input_text)
        
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)
        
        # 执行按钮
        button_layout = QHBoxLayout()
        self.execute_btn = QPushButton("执行 API 调用")
        self.execute_btn.setEnabled(False)
        self.execute_btn.clicked.connect(self._execute_api_call)
        self.execute_btn.setStyleSheet(
            "background-color: #0078d4; color: white; font-weight: bold; padding: 10px;"
        )
        button_layout.addWidget(self.execute_btn)
        layout.addLayout(button_layout)
        
        # 输出区域
        output_group = QGroupBox("调用结果")
        output_layout = QVBoxLayout()
        
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMinimumHeight(100)
        output_layout.addWidget(self.output_text)
        
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)
        
        return panel
    
    def _refresh_api_list(self):
        """刷新 API 列表"""
        self.api_list.clear()
        
        # 获取字符串工具插件的 ID
        string_tools_id = self.plugin_manager.get_plugin_id_by_name("字符串\n工具")
        
        if string_tools_id:
            # 获取该插件的 API
            plugin_api = self.plugin_manager.get_plugin_api(string_tools_id)
            
            if plugin_api:
                # 显示所有方法
                for method_name in plugin_api['methods']:
                    item_text = f"{method_name}()"
                    self.api_list.addItem(item_text)
                    self.api_list.item(self.api_list.count() - 1).setData(
                        Qt.ItemDataRole.UserRole, 
                        method_name
                    )
            else:
                self.api_list.addItem("字符串工具插件未注册 API")
        else:
            self.api_list.addItem("未找到字符串工具插件")
    
    def _on_api_selected(self, item):
        """当选择 API 方法时"""
        method_name = item.data(Qt.ItemDataRole.UserRole)
        
        if method_name:
            self.input_label.setText(f"方法: {method_name}() - 输入文本参数:")
            self.execute_btn.setEnabled(True)
            
            # 清空之前的结果
            self.output_text.clear()
    
    def _execute_api_call(self):
        """执行 API 调用"""
        current_item = self.api_list.currentItem()
        
        if not current_item:
            QMessageBox.warning(
                None,
                "警告",
                "请先选择一个 API 方法"
            )
            return
        
        method_name = current_item.data(Qt.ItemDataRole.UserRole)
        text_input = self.input_text.toPlainText()
        
        if not text_input:
            QMessageBox.warning(
                None,
                "警告",
                "请输入文本参数"
            )
            return
        
        # 获取字符串工具插件的 ID
        string_tools_id = self.plugin_manager.get_plugin_id_by_name("字符串\n工具")
        
        if not string_tools_id:
            self.output_text.setText("错误: 未找到字符串工具插件")
            return
        
        try:
            # 调用 API
            result = self.plugin_manager.call_plugin_method(
                caller_id=self.my_plugin_id,
                plugin_id=string_tools_id,
                method_name=method_name,
                text=text_input
            )
            
            # 显示结果
            self.output_text.setText(f"✓ 调用成功\n\n结果: {result}")
            
        except ValueError as e:
            self.output_text.setText(f"✗ API 不可用\n\n错误: {str(e)}")
        except RuntimeError as e:
            self.output_text.setText(f"✗ 调用失败\n\n错误: {str(e)}")
        except Exception as e:
            self.output_text.setText(f"✗ 未知错误\n\n{type(e).__name__}: {str(e)}")
    
    def _show_all_apis(self):
        """显示所有插件的 API 信息"""
        all_apis = self.plugin_manager.get_all_apis()
        
        info_text = "所有已注册的 API:\n\n"
        
        for plugin_id, api_info in all_apis.items():
            info_text += f"插件: {api_info['plugin_name']} (ID: {plugin_id})\n"
            info_text += f"类型: {api_info['plugin_type']}\n"
            info_text += f"方法: {', '.join(api_info['methods'])}\n"
            info_text += "-" * 50 + "\n"
        
        self.output_text.setText(info_text)
    
    def _show_function_tools(self):
        """显示 Function Tools 定义"""
        tools = self.plugin_manager.get_all_function_tools()
        
        info_text = f"Function Tools 定义 (共 {len(tools)} 个):\n\n"
        
        for tool in tools:
            function_info = tool['function']
            info_text += f"名称: {function_info['name']}\n"
            info_text += f"描述: {function_info['description']}\n"
            
            params = function_info['parameters']
            if params.get('properties'):
                info_text += "参数:\n"
                for param_name, param_info in params['properties'].items():
                    info_text += f"  - {param_name} ({param_info['type']}): {param_info['description']}\n"
            
            info_text += "-" * 50 + "\n"
        
        self.output_text.setText(info_text)