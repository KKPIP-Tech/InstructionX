"""
Framework API Demo 插件入口

展示 InstructionX 框架提供的所有核心 API 接口的使用方法。
"""

from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QPushButton, QTextEdit, QGroupBox,
    QLineEdit, QComboBox, QSpinBox, QListWidget,
    QListWidgetItem, QMessageBox, QFormLayout,
    QScrollArea, QFrame
)
from PySide6.QtCore import Qt, Signal, QObject, Slot

from core.plugin.plugin_interface import IPlugin
from core.data.data_provider import DataProvider, DataProviderError
from utils.logging_tools import LoggerManager, get_name

from .service import (
    DataDemoService, TaskDemoService, LLMDemoService,
    APIDemoService, FrameworkInfoService
)


class SignalBridge(QObject):
    """Qt 信号桥接器，用于线程安全的 UI 更新"""
    log_message = Signal(str)


class FrameworkAPIDemoPlugin(IPlugin):
    """Framework API Demo 插件"""

    _logger = LoggerManager()

    def __init__(self):
        super().__init__()
        self._data_provider = DataProvider()
        self._signal_bridge = SignalBridge()
        self._log_widget = None

        # 初始化服务
        self.data_service: Optional[DataDemoService] = None
        self.task_service: Optional[TaskDemoService] = None
        self.llm_service: Optional[LLMDemoService] = None
        self.api_service: Optional[APIDemoService] = None
        self.info_service: Optional[FrameworkInfoService] = None

    @property
    def plugin_name(self) -> str:
        return "Framework\nAPI Demo"

    def _create_widget(self, parent=None, data_provider=None) -> QWidget:
        # 使用 DataProvider
        dp = data_provider if data_provider else DataProvider()

        # 确保 plugin_id 存在
        if not self.plugin_id:
            self._plugin_id = f"framework-api-demo-{uuid.uuid4().hex[:8]}"

        actual_plugin_id = self.plugin_id

        # 注册插件
        try:
            dp.register_plugin(actual_plugin_id, "FrameworkAPIDemo")
            dp.set_active_instance(actual_plugin_id)
        except DataProviderError:
            pass

        # 初始化服务
        self.data_service = DataDemoService(actual_plugin_id, dp)
        self.task_service = TaskDemoService(actual_plugin_id, dp)
        self.llm_service = LLMDemoService(actual_plugin_id, dp)
        self.api_service = APIDemoService(actual_plugin_id, dp)
        self.info_service = FrameworkInfoService(actual_plugin_id, dp)

        # 连接信号
        self._signal_bridge.log_message.connect(self._on_log_message)

        # 创建主 UI
        widget = QWidget(parent)
        main_layout = QVBoxLayout(widget)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # 标题
        title = QLabel("Framework API Demo")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        main_layout.addWidget(title)

        # 显示插件 UUID
        self.plugin_id_label = QLabel(f"插件 UUID: {actual_plugin_id}")
        main_layout.addWidget(self.plugin_id_label)

        # 创建标签页
        tab_widget = QTabWidget()
        tab_widget.addTab(self._create_data_tab(), "DataProvider")
        tab_widget.addTab(self._create_task_tab(), "Task")
        tab_widget.addTab(self._create_llm_tab(), "LLM")
        tab_widget.addTab(self._create_api_tab(), "API")
        tab_widget.addTab(self._create_info_tab(), "Info")

        main_layout.addWidget(tab_widget)

        # 日志区域
        log_group = QGroupBox("执行日志")
        log_layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        log_layout.addWidget(self.log_text)

        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

        self._log_widget = self.log_text

        # 初始日志
        self._log("Framework API Demo 插件已加载")
        self._log(f"插件 ID: {actual_plugin_id}")

        return widget

    def _create_data_tab(self) -> QWidget:
        """创建 DataProvider 演示标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 插件注册区域
        register_group = QGroupBox("插件注册")
        register_layout = QHBoxLayout()
        register_layout.setSpacing(10)

        self.register_plugin_btn = QPushButton("注册演示插件")
        self.register_plugin_btn.setMinimumWidth(120)
        self.register_plugin_btn.clicked.connect(self._on_register_plugin)
        register_layout.addWidget(self.register_plugin_btn)

        self.unregister_plugin_btn = QPushButton("注销演示插件")
        self.unregister_plugin_btn.setMinimumWidth(120)
        self.unregister_plugin_btn.clicked.connect(self._on_unregister_plugin)
        register_layout.addWidget(self.unregister_plugin_btn)

        register_layout.addStretch()
        register_group.setLayout(register_layout)
        layout.addWidget(register_group)

        # 数据操作区域
        data_group = QGroupBox("数据操作")
        data_layout = QVBoxLayout()
        data_layout.setSpacing(10)

        # 私有数据行
        private_row = QHBoxLayout()
        private_row.setSpacing(8)
        
        private_label = QLabel("Private 数据:")
        private_label.setMinimumWidth(80)
        private_row.addWidget(private_label)

        self.private_key_input = QLineEdit()
        self.private_key_input.setPlaceholderText("key")
        self.private_key_input.setText("test_key")
        self.private_key_input.setMinimumWidth(100)
        private_row.addWidget(self.private_key_input)

        self.private_value_input = QLineEdit()
        self.private_value_input.setPlaceholderText("value")
        self.private_value_input.setText("test_value")
        self.private_value_input.setMinimumWidth(100)
        private_row.addWidget(self.private_value_input)

        self.write_private_btn = QPushButton("写入 Private")
        self.write_private_btn.setMinimumWidth(90)
        self.write_private_btn.clicked.connect(self._on_write_private)
        private_row.addWidget(self.write_private_btn)

        self.read_private_btn = QPushButton("读取 Private")
        self.read_private_btn.setMinimumWidth(90)
        self.read_private_btn.clicked.connect(self._on_read_private)
        private_row.addWidget(self.read_private_btn)

        private_row.addStretch()
        data_layout.addLayout(private_row)

        # 公共数据行
        public_row = QHBoxLayout()
        public_row.setSpacing(8)

        public_label = QLabel("Public 数据:")
        public_label.setMinimumWidth(80)
        public_row.addWidget(public_label)

        self.public_key_input = QLineEdit()
        self.public_key_input.setPlaceholderText("key")
        self.public_key_input.setText("shared_key")
        self.public_key_input.setMinimumWidth(100)
        public_row.addWidget(self.public_key_input)

        self.public_value_input = QLineEdit()
        self.public_value_input.setPlaceholderText("value")
        self.public_value_input.setText("shared_value")
        self.public_value_input.setMinimumWidth(100)
        public_row.addWidget(self.public_value_input)

        self.write_public_btn = QPushButton("写入 Public")
        self.write_public_btn.setMinimumWidth(90)
        self.write_public_btn.clicked.connect(self._on_write_public)
        public_row.addWidget(self.write_public_btn)

        self.read_public_btn = QPushButton("读取 Public")
        self.read_public_btn.setMinimumWidth(90)
        self.read_public_btn.clicked.connect(self._on_read_public)
        public_row.addWidget(self.read_public_btn)

        public_row.addStretch()
        data_layout.addLayout(public_row)

        # 查询行
        query_row = QHBoxLayout()
        query_row.setSpacing(8)

        query_label = QLabel("查询:")
        query_label.setMinimumWidth(80)
        query_row.addWidget(query_label)

        self.get_all_data_btn = QPushButton("获取所有数据")
        self.get_all_data_btn.setMinimumWidth(120)
        self.get_all_data_btn.clicked.connect(self._on_get_all_data)
        query_row.addWidget(self.get_all_data_btn)

        query_row.addStretch()
        data_layout.addLayout(query_row)

        data_group.setLayout(data_layout)
        layout.addWidget(data_group)

        # 资源管理区域
        asset_group = QGroupBox("资源管理")
        asset_layout = QHBoxLayout()
        asset_layout.setSpacing(10)

        self.save_asset_btn = QPushButton("保存资源")
        self.save_asset_btn.setMinimumWidth(120)
        self.save_asset_btn.clicked.connect(self._on_save_asset)
        asset_layout.addWidget(self.save_asset_btn)

        self.load_asset_btn = QPushButton("加载资源")
        self.load_asset_btn.setMinimumWidth(120)
        self.load_asset_btn.clicked.connect(self._on_load_asset)
        asset_layout.addWidget(self.load_asset_btn)

        asset_layout.addStretch()
        asset_group.setLayout(asset_layout)
        layout.addWidget(asset_group)

        layout.addStretch()
        return widget

    def _create_task_tab(self) -> QWidget:
        """创建 Task 演示标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 任务创建区域
        create_group = QGroupBox("创建任务")
        create_layout = QFormLayout()

        self.task_name_input = QLineEdit("demo_task")
        create_layout.addRow("任务名称:", self.task_name_input)

        self.task_type_combo = QComboBox()
        self.task_type_combo.addItems(["sync", "async", "scheduled"])
        create_layout.addRow("任务类型:", self.task_type_combo)

        self.task_interval_spin = QSpinBox()
        self.task_interval_spin.setRange(5, 3600)
        self.task_interval_spin.setValue(60)
        self.task_interval_spin.setSuffix(" 秒")
        create_layout.addRow("间隔(定时任务):", self.task_interval_spin)

        self.create_task_btn = QPushButton("创建任务")
        self.create_task_btn.clicked.connect(self._on_create_task)
        create_layout.addRow("", self.create_task_btn)

        create_group.setLayout(create_layout)
        layout.addWidget(create_group)

        # 任务查询区域
        query_group = QGroupBox("任务查询")
        query_layout = QVBoxLayout()

        self.query_tasks_btn = QPushButton("查询所有任务")
        self.query_tasks_btn.clicked.connect(self._on_query_tasks)
        query_layout.addWidget(self.query_tasks_btn)

        self.tasks_list = QListWidget()
        self.tasks_list.setMaximumHeight(150)
        query_layout.addWidget(self.tasks_list)

        self.clear_tasks_btn = QPushButton("清理已完成任务")
        self.clear_tasks_btn.clicked.connect(self._on_clear_tasks)
        query_layout.addWidget(self.clear_tasks_btn)

        query_group.setLayout(query_layout)
        layout.addWidget(query_group)

        layout.addStretch()
        return widget

    def _create_llm_tab(self) -> QWidget:
        """创建 LLM 演示标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Provider 信息区域
        provider_group = QGroupBox("Provider 信息")
        provider_layout = QVBoxLayout()

        self.get_providers_btn = QPushButton("获取 Provider 列表")
        self.get_providers_btn.clicked.connect(self._on_get_providers)
        provider_layout.addWidget(self.get_providers_btn)

        self.providers_list = QListWidget()
        self.providers_list.setMaximumHeight(80)
        provider_layout.addWidget(self.providers_list)

        self.get_models_btn = QPushButton("获取模型列表")
        self.get_models_btn.clicked.connect(self._on_get_models)
        provider_layout.addWidget(self.get_models_btn)

        provider_group.setLayout(provider_layout)
        layout.addWidget(provider_group)

        # 聊天区域
        chat_group = QGroupBox("聊天测试")
        chat_layout = QFormLayout()

        self.chat_message_input = QLineEdit("你好，请介绍一下自己")
        chat_layout.addRow("消息:", self.chat_message_input)

        self.chat_btn = QPushButton("发送聊天")
        self.chat_btn.clicked.connect(self._on_send_chat)
        chat_layout.addRow("", self.chat_btn)

        self.chat_result_text = QTextEdit()
        self.chat_result_text.setReadOnly(True)
        self.chat_result_text.setMaximumHeight(100)
        chat_layout.addRow("结果:", self.chat_result_text)

        chat_group.setLayout(chat_layout)
        layout.addWidget(chat_group)

        # 嵌入测试
        embed_group = QGroupBox("嵌入测试")
        embed_layout = QHBoxLayout()

        self.embed_text_input = QLineEdit("Hello world")
        embed_layout.addWidget(self.embed_text_input)

        self.embed_btn = QPushButton("发送嵌入")
        self.embed_btn.clicked.connect(self._on_send_embed)
        embed_layout.addWidget(self.embed_btn)

        embed_group.setLayout(embed_layout)
        layout.addWidget(embed_group)

        layout.addStretch()
        return widget

    def _create_api_tab(self) -> QWidget:
        """创建 API 演示标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 插件查询区域
        plugin_group = QGroupBox("插件查询")
        plugin_layout = QVBoxLayout()

        self.get_all_plugins_btn = QPushButton("获取所有插件")
        self.get_all_plugins_btn.clicked.connect(self._on_get_all_plugins)
        plugin_layout.addWidget(self.get_all_plugins_btn)

        self.plugins_list = QListWidget()
        self.plugins_list.setMaximumHeight(120)
        plugin_layout.addWidget(self.plugins_list)

        plugin_group.setLayout(plugin_layout)
        layout.addWidget(plugin_group)

        # API 查询区域
        api_group = QGroupBox("API 查询")
        api_layout = QVBoxLayout()

        self.get_all_apis_btn = QPushButton("获取所有 API")
        self.get_all_apis_btn.clicked.connect(self._on_get_all_apis)
        api_layout.addWidget(self.get_all_apis_btn)

        self.apis_list = QListWidget()
        self.apis_list.setMaximumHeight(100)
        api_layout.addWidget(self.apis_list)

        api_group.setLayout(api_layout)
        layout.addWidget(api_group)

        # Function Calling 区域
        func_group = QGroupBox("Function Calling")
        func_layout = QVBoxLayout()

        self.get_function_tools_btn = QPushButton("获取所有 Function Tools")
        self.get_function_tools_btn.clicked.connect(self._on_get_function_tools)
        func_layout.addWidget(self.get_function_tools_btn)

        self.function_tools_list = QListWidget()
        self.function_tools_list.setMaximumHeight(100)
        func_layout.addWidget(self.function_tools_list)

        func_group.setLayout(func_layout)
        layout.addWidget(func_group)

        # 跨插件调用区域
        call_group = QGroupBox("跨插件调用")
        call_layout = QFormLayout()

        self.call_plugin_input = QLineEdit()
        self.call_plugin_input.setPlaceholderText("输入 plugin_id.method")
        call_layout.addRow("调用:", self.call_plugin_input)

        self.call_method_btn = QPushButton("调用插件方法")
        self.call_method_btn.clicked.connect(self._on_call_plugin_method)
        call_layout.addRow("", self.call_method_btn)

        self.call_result_text = QTextEdit()
        self.call_result_text.setReadOnly(True)
        self.call_result_text.setMaximumHeight(80)
        call_layout.addRow("结果:", self.call_result_text)

        call_group.setLayout(call_layout)
        layout.addWidget(call_group)

        layout.addStretch()
        return widget

    def _create_info_tab(self) -> QWidget:
        """创建框架信息标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        info_group = QGroupBox("框架信息")
        info_layout = QVBoxLayout()

        self.get_info_btn = QPushButton("获取框架信息")
        self.get_info_btn.clicked.connect(self._on_get_framework_info)
        info_layout.addWidget(self.get_info_btn)

        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        info_layout.addWidget(self.info_text)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # 接口文档区域
        doc_group = QGroupBox("可用接口文档")
        doc_layout = QVBoxLayout()

        doc_text = QTextEdit()
        doc_text.setReadOnly(True)
        doc_text.setPlainText("""
Framework API Demo 演示以下接口:

1. DataProvider
   - register_plugin() / unregister_plugin()
   - get_plugin_data() / set_plugin_data()
   - save_asset() / load_asset()

2. BackgroundTaskManager
   - register_sync_task() / register_async_task()
   - register_scheduled_task()
   - get_tasks_by_plugin() / clear_completed_tasks()

3. LLMProvider
   - get_all_providers() / get_cached_models()
   - chat() / stream_chat()
   - embed()

4. PluginManager
   - get_all_plugins() / get_plugin_by_id()
   - get_all_apis() / call_plugin_method()
   - get_all_function_tools() (Function Calling)
   - get_api_description()

5. LoggerManager
   - debug() / info() / warning() / error() / critical()
        """)
        doc_layout.addWidget(doc_text)

        doc_group.setLayout(doc_layout)
        layout.addWidget(doc_group)

        layout.addStretch()
        return widget

    # 日志方法
    def _log(self, message: str):
        """添加日志"""
        timestamp = QLabel()
        from datetime import datetime
        timestamp.setText(f"[{datetime.now().strftime('%H:%M:%S')}]")
        if hasattr(self, "log_text") and self.log_text:
            self.log_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
            self.log_text.verticalScrollBar().setValue(
                self.log_text.verticalScrollBar().maximum()
            )
        else:
            self._signal_bridge.log_message.emit(message)

    @Slot(str)
    def _on_log_message(self, message: str):
        if hasattr(self, "log_text") and self.log_text:
            from datetime import datetime
            self.log_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    # DataProvider 槽函数
    def _on_register_plugin(self):
        result = self.data_service.register_demo_plugin()
        self._log(f"注册插件: {result}")
        QMessageBox.information(None, "结果", str(result))

    def _on_unregister_plugin(self):
        result = self.data_service.unregister_demo_plugin()
        self._log(f"注销插件: {result}")
        QMessageBox.information(None, "结果", str(result))

    def _on_write_private(self):
        key = self.private_key_input.text()
        value = self.private_value_input.text()
        result = self.data_service.write_private_data(key, value)
        self._log(f"写入Private: {result}")

    def _on_read_private(self):
        key = self.private_key_input.text()
        result = self.data_service.read_private_data(key)
        self._log(f"读取Private: {result}")

    def _on_write_public(self):
        key = self.public_key_input.text()
        value = self.public_value_input.text()
        result = self.data_service.write_public_data(key, value)
        self._log(f"写入Public: {result}")

    def _on_read_public(self):
        key = self.public_key_input.text()
        result = self.data_service.read_public_data(key)
        self._log(f"读取Public: {result}")

    def _on_get_all_data(self):
        result = self.data_service.get_all_data()
        self._log(f"获取所有数据: {result}")

    def _on_save_asset(self):
        result = self.data_service.save_demo_asset()
        self._log(f"保存资源: {result}")

    def _on_load_asset(self):
        result = self.data_service.save_demo_asset()
        if result.get("success"):
            result = self.data_service.load_demo_asset(result.get("path"))
        self._log(f"加载资源: {result}")

    # Task 槽函数
    def _on_create_task(self):
        name = self.task_name_input.text()
        task_type = self.task_type_combo.currentText()

        if task_type == "sync":
            result = self.task_service.create_sync_task(name)
        elif task_type == "async":
            result = self.task_service.create_async_task(name)
        else:
            interval = self.task_interval_spin.value()
            result = self.task_service.create_scheduled_task(name, interval)

        self._log(f"创建任务: {result}")

    def _on_query_tasks(self):
        result = self.task_service.query_tasks()
        self._log(f"查询任务: {result}")

        self.tasks_list.clear()
        for task in result.get("tasks", []):
            self.tasks_list.addItem(f"{task['name']} [{task['status']}]")
        for task in result.get("scheduled_tasks", []):
            status = "运行中" if task["enabled"] else "已禁用"
            self.tasks_list.addItem(f"[定时] {task['name']} ({task['interval']}s) [{status}]")

    def _on_clear_tasks(self):
        result = self.task_service.clear_completed()
        self._log(f"清理任务: {result}")
        self._on_query_tasks()

    # LLM 槽函数
    def _on_get_providers(self):
        result = self.llm_service.get_providers()
        self._log(f"获取Provider: {result}")

        self.providers_list.clear()
        for p in result.get("providers", []):
            self.providers_list.addItem(p)

    def _on_get_models(self):
        result = self.llm_service.get_models()
        self._log(f"获取模型: {result}")

    def _on_send_chat(self):
        message = self.chat_message_input.text()
        result = self.llm_service.send_chat(message)
        self._log(f"聊天结果: {result}")

        if result.get("success"):
            self.chat_result_text.setPlainText(result.get("response", ""))
        else:
            self.chat_result_text.setPlainText(f"错误: {result.get('error')}")

    def _on_send_embed(self):
        text = self.embed_text_input.text()
        result = self.llm_service.send_embedding(text)
        self._log(f"嵌入结果: {result}")
        QMessageBox.information(None, "嵌入结果", str(result))

    # API 槽函数
    def _on_get_all_plugins(self):
        result = self.api_service.get_all_plugins()
        self._log(f"获取插件: {result}")

        self.plugins_list.clear()
        for plugin in result.get("plugins", []):
            self.plugins_list.addItem(f"{plugin['name']} ({plugin['id']})")

    def _on_get_all_apis(self):
        result = self.api_service.get_all_apis()
        self._log(f"获取API: {result}")

        self.apis_list.clear()
        for pid, info in result.get("apis", {}).items():
            self.apis_list.addItem(f"{info['name']}: {', '.join(info['methods'])}")

    def _on_get_function_tools(self):
        result = self.api_service.get_all_function_tools()
        self._log(f"获取Function Tools: {result}")

        self.function_tools_list.clear()
        for tool in result.get("tools", []):
            func = tool.get("function", {})
            name = func.get("name", "unknown")
            desc = func.get("description", "")[:50]
            self.function_tools_list.addItem(f"{name}: {desc}...")

        # 显示完整 JSON
        import json
        QMessageBox.information(None, "Function Tools", json.dumps(result.get("tools", []), indent=2, ensure_ascii=False)[:2000])

    def _on_call_plugin_method(self):
        input_text = self.call_plugin_input.text()
        if not input_text or "." not in input_text:
            QMessageBox.warning(None, "输入错误", "请输入格式: plugin_id.method")
            return

        parts = input_text.split(".", 1)
        plugin_id = parts[0]
        method_name = parts[1]

        result = self.api_service.call_plugin_method(plugin_id, method_name)
        self._log(f"调用结果: {result}")

        import json
        if result.get("success"):
            self.call_result_text.setPlainText(json.dumps(result.get("result"), indent=2, ensure_ascii=False))
        else:
            self.call_result_text.setPlainText(f"错误: {result.get('error')}")

    # Info 槽函数
    def _on_get_framework_info(self):
        result = self.info_service.get_framework_info()
        import json
        self.info_text.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))
        self._log(f"框架信息: {result}")


import uuid
