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

    @property
    def plugin_name(self) -> str:
        return "API 调用\n演示"

    def _create_widget(self, parent=None, data_provider=None) -> QWidget:
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

        # 左侧面板
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        # API 列表组
        api_group = QGroupBox("可用 API 方法")
        api_group_layout = QVBoxLayout()

        # API 列表（局部变量）
        api_list = QListWidget()
        api_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        api_group_layout.addWidget(api_list)

        # 刷新按钮
        refresh_btn = QPushButton("刷新 API 列表")
        api_group_layout.addWidget(refresh_btn)

        # 查看所有插件 API 按钮
        view_all_btn = QPushButton("查看所有插件 API")
        api_group_layout.addWidget(view_all_btn)

        # 查看 Function Tools 按钮
        view_tools_btn = QPushButton("查看 Function Tools")
        api_group_layout.addWidget(view_tools_btn)

        api_group.setLayout(api_group_layout)
        left_layout.addWidget(api_group)

        splitter.addWidget(left_panel)

        # 右侧面板
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # 输入区域
        input_group = QGroupBox("输入参数")
        input_group_layout = QVBoxLayout()

        # 输入文本框（局部变量）
        input_text = QTextEdit()
        input_text.setPlaceholderText("在此输入要处理的文本...")
        input_text.setMinimumHeight(80)
        input_group_layout.addWidget(input_text)

        input_group.setLayout(input_group_layout)
        right_layout.addWidget(input_group)

        # 执行按钮
        button_layout = QHBoxLayout()

        # 执行按钮（局部变量）
        execute_btn = QPushButton("执行 API 调用")
        execute_btn.setEnabled(False)
        execute_btn.setStyleSheet(
            "background-color: #0078d4; color: white; font-weight: bold; padding: 10px;"
        )
        button_layout.addWidget(execute_btn)
        right_layout.addLayout(button_layout)

        # 输出区域
        output_group = QGroupBox("调用结果")
        output_group_layout = QVBoxLayout()

        # 输出文本框（局部变量）
        output_text = QTextEdit()
        output_text.setReadOnly(True)
        output_text.setMinimumHeight(100)
        output_group_layout.addWidget(output_text)

        output_group.setLayout(output_group_layout)
        right_layout.addWidget(output_group)

        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

        # 刷新 API 列表
        self._refresh_api_list(api_list)

        # 绑定事件处理
        # 刷新按钮
        def on_refresh():
            self._refresh_api_list(api_list)

        refresh_btn.clicked.connect(on_refresh)

        # API 选择事件
        def on_api_selected(item):
            method_name = item.data(Qt.ItemDataRole.UserRole)
            if method_name:
                execute_btn.setEnabled(True)
                output_text.clear()

        api_list.itemClicked.connect(on_api_selected)

        # 执行按钮
        def on_execute():
            self._do_execute(api_list, input_text, output_text, execute_btn)

        execute_btn.clicked.connect(on_execute)

        # 查看所有 API 按钮
        def on_view_all():
            all_apis = self.plugin_manager.get_all_apis()
            info_text = "所有已注册的 API:\n\n"
            for plugin_id, api_info in all_apis.items():
                info_text += f"插件: {api_info['plugin_name']} (ID: {plugin_id})\n"
                info_text += f"类型: {api_info['plugin_type']}\n"
                info_text += f"方法: {', '.join(api_info['methods'])}\n"
                info_text += "-" * 50 + "\n"
            output_text.setText(info_text)

        view_all_btn.clicked.connect(on_view_all)

        # 查看 Function Tools 按钮
        def on_view_tools():
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
            output_text.setText(info_text)

        view_tools_btn.clicked.connect(on_view_tools)

        return widget

    def _refresh_api_list(self, api_list):
        """刷新 API 列表"""
        api_list.clear()

        # 获取字符串工具插件的 ID
        string_tools_id = self.plugin_manager.get_plugin_id_by_type_id("string-tools")

        if string_tools_id:
            # 获取该插件的 API
            plugin_api = self.plugin_manager.get_plugin_api(string_tools_id)

            if plugin_api:
                # 显示所有方法
                for method_name in plugin_api['methods']:
                    item_text = f"{method_name}()"
                    api_list.addItem(item_text)
                    api_list.item(api_list.count() - 1).setData(
                        Qt.ItemDataRole.UserRole,
                        method_name
                    )
            else:
                api_list.addItem("字符串工具插件未注册 API")
        else:
            api_list.addItem("未找到字符串工具插件")

    def _do_execute(self, api_list, input_text, output_text, execute_btn):
        """执行 API 调用"""
        current_item = api_list.currentItem()

        if not current_item:
            QMessageBox.warning(
                None,
                "警告",
                "请先选择一个 API 方法"
            )
            return

        method_name = current_item.data(Qt.ItemDataRole.UserRole)
        text_input = input_text.toPlainText()

        if not text_input:
            QMessageBox.warning(
                None,
                "警告",
                "请输入文本参数"
            )
            return

        # 获取字符串工具插件的 ID
        string_tools_id = self.plugin_manager.get_plugin_id_by_type_id("string-tools")

        if not string_tools_id:
            output_text.setText("错误: 未找到字符串工具插件")
            return

        try:
            # 调用 API
            result = self.plugin_manager.call_plugin_method(
                caller_id=self.plugin_id,
                plugin_id=string_tools_id,
                method_name=method_name,
                text=text_input
            )

            # 显示结果
            output_text.setText(f"✓ 调用成功\n\n结果: {result}")

        except ValueError as e:
            output_text.setText(f"✗ API 不可用\n\n错误: {str(e)}")
        except RuntimeError as e:
            output_text.setText(f"✗ 调用失败\n\n错误: {str(e)}")
        except Exception as e:
            output_text.setText(f"✗ 未知错误\n\n{type(e).__name__}: {str(e)}")
