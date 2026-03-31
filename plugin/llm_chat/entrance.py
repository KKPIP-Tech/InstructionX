"""
LLM Chat 插件入口 - UI 界面
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit,
    QComboBox, QGroupBox, QFileDialog,
    QMessageBox, QScrollArea, QFrame,
    QSplitter, QListWidget, QListWidgetItem,
    QSlider
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QTextCursor, QColor, QTextCharFormat

from core.plugin.plugin_interface import IPlugin
from core.data.data_provider import DataProvider, DataProviderError

from utils.logging_tools import LoggerManager, get_name


# 延迟导入 service，避免插件加载时的循环依赖问题
def _get_service(plugin_id, data_provider):
    from .service import LLMChatService
    return LLMChatService(plugin_id, data_provider)


class ChatWorker(QThread):
    """聊天工作线程"""
    finished = Signal(dict)
    chunk_received = Signal(str)

    def __init__(self, service, message, provider, model, temperature, max_tokens, images, history):
        super().__init__()
        self.service = service
        self.message = message
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.images = images
        self.history = history
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if self._is_cancelled:
            return

        try:
            # 使用流式接口
            for result in self.service.stream_send_message(
                self.message,
                self.provider,
                self.model,
                self.temperature,
                self.max_tokens,
                self.images,
                self.history,
            ):
                if self._is_cancelled:
                    break

                if "error" in result and result.get("done"):
                    self.finished.emit(result)
                    break

                if not result.get("done"):
                    self.chunk_received.emit(result.get("chunk", ""))
                else:
                    self.finished.emit({
                        "success": True,
                        "full_response": result.get("full_response", ""),
                        "model": result.get("model", ""),
                    })
        except Exception as e:
            self.finished.emit({
                "success": False,
                "error": str(e),
            })


class LLMChatPlugin(IPlugin):
    """LLM Chat 插件"""

    _logger = LoggerManager()

    @property
    def plugin_name(self) -> str:
        return "LLM\nChat"

    def _create_widget(self, parent=None, data_provider=None) -> QWidget:
        # 使用单例的 DataProvider
        dp = DataProvider()

        # 确保 plugin_id 存在
        if not self.plugin_id:
            self._plugin_id = "llm-chat-default"

        actual_plugin_id = self.plugin_id
        if actual_plugin_id is None:
            actual_plugin_id = "llm-chat-default"
            self._plugin_id = actual_plugin_id

        # 尝试注册插件
        try:
            dp.register_plugin(actual_plugin_id, "LLMChat")
            dp.set_active_instance(actual_plugin_id)
        except DataProviderError:
            pass

        # 创建服务实例
        self.service = _get_service(actual_plugin_id, dp)

        # 如果外部传入了 data_provider，也尝试使用它注册
        if data_provider:
            try:
                data_provider.register_plugin(actual_plugin_id, "LLMChat")
                data_provider.set_active_instance(actual_plugin_id)
            except DataProviderError:
                pass

        # 创建 UI
        widget = QWidget(parent)
        main_layout = QVBoxLayout(widget)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # ========== 顶部配置区域 ==========
        config_group = QGroupBox("配置")
        config_layout = QHBoxLayout()

        # Provider 选择
        config_layout.addWidget(QLabel("供应商:"))
        self.provider_combo = QComboBox()
        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        config_layout.addWidget(self.provider_combo)

        # Model 选择
        config_layout.addWidget(QLabel("模型:"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(200)
        config_layout.addWidget(self.model_combo)

        # 刷新模型按钮
        refresh_btn = QPushButton("刷新模型")
        refresh_btn.clicked.connect(self._refresh_models)
        config_layout.addWidget(refresh_btn)

        # 验证按钮
        validate_btn = QPushButton("验证配置")
        validate_btn.clicked.connect(self._validate_provider)
        config_layout.addWidget(validate_btn)

        config_group.setLayout(config_layout)
        main_layout.addWidget(config_group)

        # ========== 参数设置区域 ==========
        params_group = QGroupBox("参数")
        params_layout = QHBoxLayout()

        # Temperature
        params_layout.addWidget(QLabel("Temperature:"))
        self.temp_slider = QSlider(Qt.Orientation.Horizontal)
        self.temp_slider.setRange(0, 100)
        self.temp_slider.setValue(70)
        self.temp_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.temp_slider.setTickInterval(10)
        self.temp_slider.setToolTip("控制输出的随机性，值越低越确定")
        params_layout.addWidget(self.temp_slider)
        self.temp_label = QLabel("0.7")
        params_layout.addWidget(self.temp_label)
        self.temp_slider.valueChanged.connect(
            lambda v: self.temp_label.setText(f"{v / 100:.1f}")
        )

        # Max Tokens
        params_layout.addWidget(QLabel("Max Tokens:"))
        self.max_tokens_combo = QComboBox()
        self.max_tokens_combo.addItems(["256", "512", "1024", "2048", "4096", "无限制"])
        self.max_tokens_combo.setCurrentIndex(1)
        params_layout.addWidget(self.max_tokens_combo)

        # 多模态 - 图片按钮
        self.image_btn = QPushButton("添加图片")
        self.image_btn.clicked.connect(self._add_image)
        params_layout.addWidget(self.image_btn)

        # 已添加图片列表
        self.images_list = QListWidget()
        self.images_list.setMaximumHeight(40)
        params_layout.addWidget(self.images_list)

        # 清除图片按钮
        clear_img_btn = QPushButton("清除图片")
        clear_img_btn.clicked.connect(self._clear_images)
        params_layout.addWidget(clear_img_btn)

        params_group.setLayout(params_layout)
        main_layout.addWidget(params_group)

        # ========== 对话区域 ==========
        splitter = QSplitter(Qt.Orientation.Vertical)

        # 历史记录
        history_group = QGroupBox("对话历史")
        history_layout = QVBoxLayout()
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(100)
        self.history_list.itemClicked.connect(self._on_history_item_clicked)
        history_layout.addWidget(self.history_list)

        # 清除历史按钮
        clear_history_btn = QPushButton("清除对话历史")
        clear_history_btn.clicked.connect(self._clear_history)
        history_layout.addWidget(clear_history_btn)

        history_group.setLayout(history_layout)
        splitter.addWidget(history_group)

        # 聊天区域
        chat_group = QGroupBox("对话")
        chat_layout = QVBoxLayout()

        # 输出区域
        self.output_edit = QTextEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setPlaceholderText("AI 回复将显示在这里...")
        chat_layout.addWidget(self.output_edit)

        # 输入区域
        input_layout = QHBoxLayout()

        self.input_edit = QTextEdit()
        self.input_edit.setPlaceholderText("输入您的问题... (按 Enter 发送)")
        self.input_edit.setMaximumHeight(80)
        self.input_edit.keyPressEvent = self._handle_input_keypress
        input_layout.addWidget(self.input_edit)

        # 发送按钮
        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self._send_message)
        self.send_btn.setMinimumWidth(80)
        input_layout.addWidget(self.send_btn)

        # 停止按钮
        self.stop_btn = QPushButton("停止")
        self.stop_btn.clicked.connect(self._stop_stream)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setMinimumWidth(80)
        input_layout.addWidget(self.stop_btn)

        chat_layout.addLayout(input_layout)
        chat_group.setLayout(chat_layout)
        splitter.addWidget(chat_group)

        main_layout.addWidget(splitter)

        # ========== 状态栏 ==========
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: gray;")
        main_layout.addWidget(self.status_label)

        # ========== 初始化 ==========
        self._load_preferences()
        self._init_providers()
        self._chat_worker = None
        self._images = []  # 存储图片 base64

        self.widget = widget
        # 连接主窗口的 LLM Provider 切换 Signal
        main_window = self._find_main_window()
        if main_window and hasattr(main_window, 'llm_provider_changed'):
            main_window.llm_provider_changed.connect(self._on_global_llm_changed)

        return widget

    def _find_main_window(self):
        """向上查找 MainWindow"""
        parent = self.widget.parent()
        while parent:
            try:
                from ui.main_window import InstructionXMainWindow
                if isinstance(parent, InstructionXMainWindow):
                    return parent
            except ImportError:
                pass
            parent = parent.parent()
        return None

    def _on_global_llm_changed(self, provider: str, model: str):
        """响应全局 LLM Provider 切换"""
        # 切换 Provider combo
        idx = self.provider_combo.findText(provider)
        if idx >= 0 and idx != self.provider_combo.currentIndex():
            self.provider_combo.setCurrentIndex(idx)
        # 切换 Model combo
        if model:
            idx = self.model_combo.findText(model)
            if idx >= 0 and idx != self.model_combo.currentIndex():
                self.model_combo.setCurrentIndex(idx)
        # 保存偏好
        self.service.save_preference("last_provider", provider)

    def _init_providers(self):
        """初始化 Provider 列表"""
        self.provider_combo.clear()
        providers = self.service.get_providers()

        if not providers:
            # 尝试获取所有 Provider
            all_providers = self.service.get_all_providers()
            providers = list(all_providers.keys())

        if not providers:
            self.provider_combo.addItem("无可用 Provider")
            QMessageBox.warning(
                None,
                "警告",
                "未找到可用的 LLM Provider。\n\n"
                "请在「编辑 > LLM设置」中配置并启用至少一个 Provider。"
            )
            return

        # 加载上次使用的 Provider
        last_provider = self.service.load_preference("last_provider", "")
        if last_provider and last_provider in providers:
            self.provider_combo.addItems(providers)
            self.provider_combo.setCurrentText(last_provider)
        else:
            self.provider_combo.addItems(providers)

    def _on_provider_changed(self, provider: str):
        """Provider 切换时刷新模型列表"""
        if provider and provider != "无可用 Provider":
            self._refresh_models()
            self.service.save_preference("last_provider", provider)

    def _refresh_models(self):
        """刷新模型列表"""
        provider = self.provider_combo.currentText()
        if not provider or provider == "无可用 Provider":
            return

        self._logger.debug(get_name(), f"Refreshing for provider: {provider}")

        self.model_combo.clear()
        models = self.service.get_models(provider)

        self._logger.debug(get_name(), f"Got {len(models)} models")

        if not models:
            self.model_combo.addItem("无可用模型")
            return

        # 只添加支持 Chat 的模型
        chat_models = [m for m in models if m.support_chat]
        if not chat_models:
            chat_models = models  # 降级：显示所有模型

        self._logger.debug(get_name(), f"Chat models: {[m.id for m in chat_models[:5]]}")

        for model in chat_models:
            self.model_combo.addItem(model.id, model)

        # 加载上次使用的模型
        last_model = self.service.load_preference(f"last_model_{provider}", "")
        if last_model:
            index = self.model_combo.findText(last_model)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)

    def _validate_provider(self):
        """验证 Provider 配置"""
        provider = self.provider_combo.currentText()
        if not provider or provider == "无可用 Provider":
            return

        result = self.service.validate_provider(provider)

        if result["valid"]:
            vision_support = "支持" if result["supports_vision"] else "不支持"
            QMessageBox.information(
                None,
                "验证成功",
                f"Provider「{provider}」配置有效。\n"
                f"Vision 多模态: {vision_support}"
            )
            # 启用/禁用图片按钮
            self.image_btn.setEnabled(result["supports_vision"])
        else:
            QMessageBox.critical(
                None,
                "验证失败",
                f"Provider「{provider}」配置无效:\n\n{result['message']}\n\n"
                "请在「编辑 > LLM设置」中配置。"
            )

    def _add_image(self):
        """添加图片"""
        files, _ = QFileDialog.getOpenFileNames(
            None,
            "选择图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.gif *.bmp *.webp)"
        )

        if not files:
            return

        for file_path in files:
            # 转换为 base64
            base64_data = self.service.load_image_as_base64(file_path)
            if base64_data:
                self._images.append(base64_data)
                # 显示文件名
                from pathlib import Path
                self.images_list.addItem(Path(file_path).name)
            else:
                QMessageBox.warning(
                    None,
                    "警告",
                    f"无法读取图片: {file_path}"
                )

    def _clear_images(self):
        """清除图片"""
        self._images.clear()
        self.images_list.clear()

    def _send_message(self):
        """发送消息"""
        # 检查是否正在运行
        if self._chat_worker and self._chat_worker.isRunning():
            QMessageBox.information(None, "提示", "正在生成中，请稍候...")
            return

        message = self.input_edit.toPlainText().strip()
        if not message:
            QMessageBox.warning(None, "警告", "请输入消息")
            return

        provider = self.provider_combo.currentText()
        if not provider or provider == "无可用 Provider":
            QMessageBox.warning(None, "警告", "请选择有效的 Provider")
            return

        self._logger.debug(get_name(), f"Selected Provider: {provider}")
        self._logger.debug(get_name(), f"Selected Model: {self.model_combo.currentText()}")

        # 验证 Provider 配置
        validation = self.service.validate_provider(provider)
        if not validation["valid"]:
            QMessageBox.critical(
                None,
                "配置无效",
                f"Provider「{provider}」配置无效:\n\n{validation['message']}\n\n"
                "请在「编辑 > LLM设置」中配置 API Key。"
            )
            return

        model = self.model_combo.currentText()
        if not model or model == "无可用模型":
            model = None  # 使用默认模型

        # 获取参数
        temperature = self.temp_slider.value() / 100
        max_tokens_str = self.max_tokens_combo.currentText()
        max_tokens = None if max_tokens_str == "无限制" else int(max_tokens_str)

        # 获取历史
        history = []
        for i in range(self.history_list.count()):
            item = self.history_list.item(i)
            if item:
                data = item.data(Qt.ItemDataRole.UserRole)
                if data:
                    history.append(data)

        # 准备发送
        self.send_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.input_edit.setEnabled(False)
        self.output_edit.clear()
        self.status_label.setText("正在生成...")

        # 添加用户消息到历史
        user_msg = {"role": "user", "content": message}
        if self._images:
            user_msg["images"] = self._images
        history.append(user_msg)

        # 启动工作线程
        self._chat_worker = ChatWorker(
            self.service,
            message,
            provider,
            model,
            temperature,
            max_tokens,
            self._images if self._images else None,
            history[:-1],  # 不包含当前消息
        )
        self._chat_worker.chunk_received.connect(self._on_chunk_received)
        self._chat_worker.finished.connect(self._on_finished)
        self._chat_worker.start()

    def _on_chunk_received(self, chunk: str):
        """接收流式响应"""
        try:
            cursor = self.output_edit.textCursor()
            if cursor.position() >= 0:
                cursor.movePosition(QTextCursor.MoveOperation.End)
                cursor.insertText(chunk)
                self.output_edit.setTextCursor(cursor)
                self.output_edit.ensureCursorVisible()
        except Exception:
            pass  # Ignore cursor errors

    def _on_finished(self, result: dict):
        """处理完成"""
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.input_edit.setEnabled(True)
        self.input_edit.setFocus()

        if result.get("success"):
            # 添加到历史记录
            history = []
            for i in range(self.history_list.count()):
                item = self.history_list.item(i)
                if item:
                    data = item.data(Qt.ItemDataRole.UserRole)
                    if data:
                        history.append(data)

            # 添加用户消息
            user_msg = {"role": "user", "content": self.input_edit.toPlainText().strip()}
            if self._images:
                user_msg["images"] = self._images.copy()
            history.append(user_msg)

            # 添加 AI 回复
            assistant_msg = {
                "role": "assistant",
                "content": result.get("full_response", ""),
            }
            history.append(assistant_msg)

            # 更新显示
            self.history_list.addItem(f"你: {user_msg['content'][:50]}...")
            self.history_list.addItem(f"AI: {assistant_msg['content'][:50]}...")

            # 保存到持久化
            self.service.save_chat_history(history)

            # 清除图片
            self._clear_images()
            self.input_edit.clear()
            self.status_label.setText(f"完成 (使用模型: {result.get('model', 'unknown')})")
        else:
            error = result.get("error", "未知错误")
            error_type = result.get("error_type", "unknown")

            # 显示错误
            self.output_edit.append("\n\n--- 错误 ---\n")
            self.output_edit.append(error)

            # 错误类型提示
            self.status_label.setText(f"错误: {error_type}")

            # 根据错误类型给出建议
            if error_type == "authentication":
                QMessageBox.critical(
                    None,
                    "认证失败",
                    f"API 认证失败。\n\n{error}\n\n"
                    "请在「编辑 > LLM设置」中检查 API Key。"
                )
            elif error_type == "rate_limit":
                QMessageBox.warning(None, "请求超限", error)
            elif error_type == "configuration":
                QMessageBox.critical(None, "配置错误", error)

    def _stop_stream(self):
        """停止流式响应"""
        if self._chat_worker and self._chat_worker.isRunning():
            self._chat_worker.cancel()
            self.status_label.setText("已停止")
            self.send_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.input_edit.setEnabled(True)

    def _on_history_item_clicked(self, item):
        """点击历史项"""
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return

        role = data.get("role", "")
        content = data.get("content", "")

        if role == "user":
            title = "用户消息"
        elif role == "assistant":
            title = "AI 回复"
        else:
            title = "消息"

        QMessageBox.information(None, title, content)

    def _clear_history(self):
        """清除对话历史"""
        reply = QMessageBox.question(
            None,
            "确认",
            "确定要清除所有对话历史吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.history_list.clear()
            self.service.save_chat_history([])

    def _handle_input_keypress(self, event):
        """处理输入框键盘事件"""
        if event.key() == Qt.Key.Key_Return and not event.modifiers():
            # Enter 键发送消息
            self._send_message()
        elif event.key() == Qt.Key.Key_Return and event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
            # Shift+Enter 换行
            self.input_edit.insertPlainText("\n")
        else:
            # 其他按键默认处理
            QTextEdit.keyPressEvent(self.input_edit, event)

    def _load_preferences(self):
        """加载偏好设置"""
        # 可以在这里加载其他偏好设置
        pass
