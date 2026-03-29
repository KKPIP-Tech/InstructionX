"""
LLM Provider 设置对话框
允许用户管理 LLM Provider 配置，包括 API Key、模型选择等功能
"""
from typing import Optional, Dict, Any, List

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem,
    QPushButton, QFrame, QLineEdit, QComboBox,
    QCheckBox, QGroupBox, QFormLayout, QMessageBox,
    QTextEdit, QScrollArea, QWidget, QToolTip
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont

from core.llm.config import LLMConfig, ProviderConfig
from core.llm.providers import get_all_provider_types
from core.llm.provider_interface import ModelInfo


class LLMSettingsDialog(QDialog):
    """LLM Provider 设置对话框"""

    # 信号：当配置更改时发出
    config_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.llm_config = LLMConfig()
        self.current_provider = None
        self.provider_widgets = {}  # 存储各 provider 的控件引用

        self.setWindowTitle("LLM 设置")
        self.setMinimumSize(800, 550)
        self._init_ui()
        self._load_providers()

    def _init_ui(self):
        """初始化界面"""
        layout = QHBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # 左侧：Provider 列表
        left_panel = self._create_left_panel()
        layout.addWidget(left_panel, stretch=1)

        # 右侧：配置详情
        self.right_panel = self._create_right_panel()
        layout.addWidget(self.right_panel, stretch=2)

    def _create_left_panel(self) -> QWidget:
        """创建左侧面板"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        # 标题
        title_label = QLabel("Provider 列表")
        title_font = QFont()
        title_font.setPointSize(10)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        # Provider 列表
        self.provider_list = QListWidget()
        self.provider_list.setProperty("class", "dialog")
        self.provider_list.style().unpolish(self.provider_list)
        self.provider_list.style().polish(self.provider_list)
        self.provider_list.itemClicked.connect(self._on_provider_selected)
        layout.addWidget(self.provider_list)

        # 添加/删除按钮
        button_layout = QHBoxLayout()

        self.add_button = QPushButton("添加")
        self.add_button.setMinimumWidth(60)
        self.add_button.clicked.connect(self._on_add_provider)
        button_layout.addWidget(self.add_button)

        self.remove_button = QPushButton("删除")
        self.remove_button.setMinimumWidth(60)
        self.remove_button.clicked.connect(self._on_remove_provider)
        self.remove_button.setEnabled(False)
        button_layout.addWidget(self.remove_button)

        layout.addLayout(button_layout)

        return widget

    def _create_right_panel(self) -> QWidget:
        """创建右侧面板"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)
        layout.setContentsMargins(10, 0, 0, 0)

        # 滚动区域（用于配置表单）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        scroll_content = QWidget()
        self.config_layout = QFormLayout(scroll_content)
        self.config_layout.setSpacing(12)
        self.config_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Provider 名称（只读）
        self.name_edit = QLineEdit()
        self.name_edit.setReadOnly(True)
        self.config_layout.addRow("名称:", self.name_edit)

        # Provider 类型（只读）
        self.type_edit = QLineEdit()
        self.type_edit.setReadOnly(True)
        self.config_layout.addRow("类型:", self.type_edit)

        # API Key
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("请输入 API Key，填写后点击刷新模型")
        self.api_key_edit.textChanged.connect(self._on_api_key_changed)
        self.config_layout.addRow("API Key:", self.api_key_edit)

        # Base URL
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("例如: https://api.example.com/v1")
        self.base_url_edit.textChanged.connect(self._on_config_changed)
        self.config_layout.addRow("Base URL:", self.base_url_edit)

        # Chat 模型
        self.chat_model_combo = QComboBox()
        self.chat_model_combo.setEditable(True)
        self.chat_model_combo.currentTextChanged.connect(self._on_config_changed)
        self.config_layout.addRow("Chat 模型:", self.chat_model_combo)

        # Embedding 模型
        self.embedding_model_combo = QComboBox()
        self.embedding_model_combo.setEditable(True)
        self.embedding_model_combo.currentTextChanged.connect(self._on_config_changed)
        self.config_layout.addRow("Embedding 模型:", self.embedding_model_combo)

        # Chat 启用开关
        self.chat_enabled_checkbox = QCheckBox("启用 Chat 功能")
        self.chat_enabled_checkbox.stateChanged.connect(self._on_config_changed)
        self.config_layout.addRow("", self.chat_enabled_checkbox)

        # Embedding 启用开关
        self.embedding_enabled_checkbox = QCheckBox("启用 Embedding 功能")
        self.embedding_enabled_checkbox.stateChanged.connect(self._on_config_changed)
        self.config_layout.addRow("", self.embedding_enabled_checkbox)

        # Vision 支持（显示）
        self.vision_label = QLabel("未知")
        self.vision_label.setProperty("muted", "true")
        self.vision_label.style().unpolish(self.vision_label)
        self.vision_label.style().polish(self.vision_label)
        self.config_layout.addRow("多模态:", self.vision_label)

        # Function Calling 支持（显示）
        self.function_calling_label = QLabel("未知")
        self.function_calling_label.setProperty("muted", "true")
        self.function_calling_label.style().unpolish(self.function_calling_label)
        self.function_calling_label.style().polish(self.function_calling_label)
        self.config_layout.addRow("Function Calling:", self.function_calling_label)

        # 上下文长度（显示）
        self.context_length_label = QLabel("未知")
        self.context_length_label.setProperty("muted", "true")
        self.context_length_label.style().unpolish(self.context_length_label)
        self.context_length_label.style().polish(self.context_length_label)
        self.config_layout.addRow("上下文长度:", self.context_length_label)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, stretch=1)

        # 按钮区域
        button_layout = QHBoxLayout()

        # 刷新模型列表按钮
        self.refresh_button = QPushButton("刷新模型")
        self.refresh_button.setMinimumWidth(100)
        self.refresh_button.clicked.connect(self._on_refresh_models)
        button_layout.addWidget(self.refresh_button)

        # 测试连接按钮
        self.test_button = QPushButton("测试连接")
        self.test_button.setMinimumWidth(80)
        self.test_button.clicked.connect(self._on_test_connection)
        button_layout.addWidget(self.test_button)

        button_layout.addStretch()

        # 保存按钮
        self.save_button = QPushButton("保存")
        self.save_button.setMinimumWidth(80)
        self.save_button.setProperty("class", "accentSave")
        self.save_button.style().unpolish(self.save_button)
        self.save_button.style().polish(self.save_button)
        self.save_button.clicked.connect(self._on_save)
        self.save_button.setEnabled(False)
        button_layout.addWidget(self.save_button)

        button_layout.addSpacing(10)

        # 取消按钮
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setMinimumWidth(80)
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

        # 初始状态：禁用所有控件
        self._set_controls_enabled(False)

        return widget

    def _set_controls_enabled(self, enabled: bool):
        """设置控件启用状态"""
        self.api_key_edit.setEnabled(enabled)
        self.base_url_edit.setEnabled(enabled)
        self.chat_model_combo.setEnabled(enabled)
        self.embedding_model_combo.setEnabled(enabled)
        self.chat_enabled_checkbox.setEnabled(enabled)
        self.embedding_enabled_checkbox.setEnabled(enabled)
        # Vision/Function Calling 是显示信息，不是编辑控件
        self.test_button.setEnabled(enabled)
        self.save_button.setEnabled(enabled and self._has_changes())

    def _load_providers(self):
        """加载已配置的 Provider"""
        self.provider_list.clear()
        providers = self.llm_config.get_all_providers()

        for name, config in providers.items():
            item = QListWidgetItem(config.name or name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.provider_list.addItem(item)

    def _on_provider_selected(self, item: QListWidgetItem):
        """Provider 选择事件"""
        # 如果有未保存的更改，提示用户
        if self._has_changes():
            reply = QMessageBox.question(
                self,
                "未保存的更改",
                "当前配置有未保存的更改，是否保存？",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
            )

            if reply == QMessageBox.StandardButton.Save:
                self._on_save()
            elif reply == QMessageBox.StandardButton.Cancel:
                return

        provider_name = item.data(Qt.ItemDataRole.UserRole)
        self.current_provider = provider_name
        self._load_provider_config(provider_name)

        self.remove_button.setEnabled(True)

    def _load_provider_config(self, provider_name: str):
        """加载 Provider 配置到表单"""
        config = self.llm_config.get_provider(provider_name)
        if not config:
            return

        self.name_edit.setText(config.name)
        self.type_edit.setText(config.provider_type)
        self.api_key_edit.setText(config.api_key)
        self.base_url_edit.setText(config.base_url)

        # 加载 Chat 模型（通过 API，无预设）
        self.chat_model_combo.clear()
        chat_models = self._get_chat_models(provider_name)
        chat_model_ids = [m.id for m in chat_models]
        self.chat_model_combo.addItems(chat_model_ids)
        if config.chat_model and config.chat_model in chat_model_ids:
            self.chat_model_combo.setCurrentText(config.chat_model)
        elif chat_model_ids:
            # 默认选择第一个
            self.chat_model_combo.setCurrentIndex(0)

        # 加载 Embedding 模型（通过 API，无预设）
        self.embedding_model_combo.clear()
        embedding_models = self._get_embedding_models(provider_name)
        embedding_model_ids = [m.id for m in embedding_models]
        self.embedding_model_combo.addItems(embedding_model_ids)
        if config.embedding_model and config.embedding_model in embedding_model_ids:
            self.embedding_model_combo.setCurrentText(config.embedding_model)

        # 设置复选框状态
        self.chat_enabled_checkbox.setChecked(config.enabled_chat)
        self.embedding_enabled_checkbox.setChecked(config.enabled_embedding)

        # 更新模型能力显示（根据选中的模型）
        self._update_model_capabilities()

        # 监听模型选择变化
        self.chat_model_combo.currentIndexChanged.connect(self._update_model_capabilities)
        self.embedding_model_combo.currentIndexChanged.connect(self._update_model_capabilities)

        self._set_controls_enabled(True)
        self.save_button.setEnabled(False)

    def _update_model_capabilities(self):
        """更新模型能力显示"""
        # 获取当前选中的 Chat 模型
        chat_model_id = self.chat_model_combo.currentText()
        chat_models = self._get_chat_models(self.current_provider)
        chat_model = next((m for m in chat_models if m.id == chat_model_id), None)

        if chat_model:
            # Vision 支持
            vision_support = "支持" if chat_model.support_vision else "不支持"
            self.vision_label.setText(vision_support)
            self.vision_label.setStyleSheet(
                "color: green;" if chat_model.support_vision else "color: #999;"
            )

            # Function Calling 支持
            fc_support = "支持" if chat_model.support_function_calling else "不支持"
            self.function_calling_label.setText(fc_support)
            self.function_calling_label.setStyleSheet(
                "color: green;" if chat_model.support_function_calling else "color: #999;"
            )

            # 上下文长度
            if chat_model.context_length:
                ctx_len = chat_model.context_length
                if ctx_len >= 1000000:
                    self.context_length_label.setText(f"{ctx_len / 1000000:.1f}M")
                else:
                    self.context_length_label.setText(f"{ctx_len // 1000}K")
            else:
                self.context_length_label.setText("未知")
        else:
            self.vision_label.setText("无模型")
            self.function_calling_label.setText("无模型")
            self.context_length_label.setText("无模型")

    def _get_chat_models(self, provider_name: str) -> List[ModelInfo]:
        """获取 Chat 模型列表（通过 API 获取，无预设）"""
        from core.llm.llm_provider import get_llm_provider

        try:
            provider = get_llm_provider().get_provider(provider_name)
            if provider:
                models = provider.get_models()
                # 过滤出支持 Chat 的模型
                return [m for m in models if m.support_chat]
        except Exception:
            pass

        # 无预设列表，返回空列表
        return []

    def _get_embedding_models(self, provider_name: str) -> List[ModelInfo]:
        """获取 Embedding 模型列表（通过 API 获取，无预设）"""
        from core.llm.llm_provider import get_llm_provider

        try:
            provider = get_llm_provider().get_provider(provider_name)
            if provider:
                models = provider.get_models()
                # 过滤出支持 Embedding 的模型
                return [m for m in models if m.support_embedding]
        except Exception:
            pass

        # 无预设列表，返回空列表
        return []

    def _on_add_provider(self):
        """添加 Provider"""
        # 显示可用 Provider 类型供选择
        available_types = get_all_provider_types()

        # 创建选择对话框
        from PySide6.QtWidgets import QInputDialog
        provider_type, ok = QInputDialog.getItem(
            self,
            "添加 Provider",
            "选择 Provider 类型:",
            available_types,
            0,
            False
        )

        if ok and provider_type:
            # 生成唯一的名称
            base_name = provider_type
            name = base_name
            counter = 1
            while self.llm_config.get_provider(name):
                name = f"{base_name}_{counter}"
                counter += 1

            # 创建新配置
            new_config = ProviderConfig(
                name=name.capitalize(),
                provider_type=provider_type,
                api_key="",
                base_url="",
                chat_model="",
                embedding_model="",
                enabled_chat=True,
                enabled_embedding=False,
                support_vision=True
            )

            self.llm_config.add_provider(name, new_config)
            self._load_providers()

            # 选中新添加的 Provider
            for i in range(self.provider_list.count()):
                item = self.provider_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == name:
                    self.provider_list.setCurrentItem(item)
                    break

    def _on_remove_provider(self):
        """删除 Provider"""
        if not self.current_provider:
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除 Provider \"{self.name_edit.text()}\" 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.llm_config.remove_provider(self.current_provider)
            self.current_provider = None
            self._load_providers()
            self._set_controls_enabled(False)
            self.remove_button.setEnabled(False)

    def _on_api_key_changed(self, text: str):
        """API Key 更改事件 - 提示刷新模型"""
        if self.current_provider and text:
            # 提示用户刷新模型
            self.refresh_button.setText("待刷新")
            self.refresh_button.setProperty("class", "warning")
            self.refresh_button.style().unpolish(self.refresh_button)
            self.refresh_button.style().polish(self.refresh_button)
        self._on_config_changed()

    def _on_config_changed(self):
        """配置更改事件"""
        if self.current_provider:
            self.save_button.setEnabled(self._has_changes())

    def _has_changes(self) -> bool:
        """检查是否有未保存的更改"""
        if not self.current_provider:
            return False

        config = self.llm_config.get_provider(self.current_provider)
        if not config:
            return False

        return (
            self.api_key_edit.text() != config.api_key or
            self.base_url_edit.text() != config.base_url or
            self.chat_model_combo.currentText() != config.chat_model or
            self.embedding_model_combo.currentText() != config.embedding_model or
            self.chat_enabled_checkbox.isChecked() != config.enabled_chat or
            self.embedding_enabled_checkbox.isChecked() != config.enabled_embedding
        )

    def _on_refresh_models(self):
        """刷新模型列表"""
        if not self.current_provider:
            return

        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("刷新中...")

        try:
            from core.llm.llm_provider import get_llm_provider

            # 强制从 API 刷新模型列表
            get_llm_provider().refresh_provider_models(self.current_provider, force=True)

            # 重新加载模型列表
            chat_models = self._get_chat_models(self.current_provider)
            embedding_models = self._get_embedding_models(self.current_provider)

            # 更新下拉框（需要转换为 ID 列表）
            current_chat_model = self.chat_model_combo.currentText()
            current_embedding_model = self.embedding_model_combo.currentText()

            chat_model_ids = [m.id for m in chat_models]
            embedding_model_ids = [m.id for m in embedding_models]

            self.chat_model_combo.blockSignals(True)
            self.chat_model_combo.clear()
            self.chat_model_combo.addItems(chat_model_ids)
            if current_chat_model in chat_model_ids:
                self.chat_model_combo.setCurrentText(current_chat_model)
            elif chat_model_ids:
                self.chat_model_combo.setCurrentIndex(0)
            self.chat_model_combo.blockSignals(False)

            self.embedding_model_combo.blockSignals(True)
            self.embedding_model_combo.clear()
            self.embedding_model_combo.addItems(embedding_model_ids)
            if current_embedding_model in embedding_model_ids:
                self.embedding_model_combo.setCurrentText(current_embedding_model)
            elif embedding_model_ids:
                self.embedding_model_combo.setCurrentIndex(0)
            self.embedding_model_combo.blockSignals(False)

            # 更新模型能力显示
            self._update_model_capabilities()

            # 重置刷新按钮样式
            self.refresh_button.setText("刷新模型")
            self.refresh_button.setProperty("class", "accentSave")
            self.refresh_button.style().unpolish(self.refresh_button)
            self.refresh_button.style().polish(self.refresh_button)

            if chat_models or embedding_models:
                QMessageBox.information(
                    self,
                    "刷新成功",
                    f"Chat 模型: {len(chat_models)}\nEmbedding 模型: {len(embedding_models)}"
                )
            else:
                QMessageBox.warning(
                    self,
                    "无可用模型",
                    "未能获取到任何模型，请检查 API Key 是否正确。"
                )
        except Exception as e:
            QMessageBox.warning(
                self,
                "刷新失败",
                f"无法刷新模型列表：{str(e)}"
            )
        finally:
            self.refresh_button.setEnabled(True)

    def _on_test_connection(self):
        """测试连接"""
        if not self.current_provider:
            return

        self.test_button.setEnabled(False)
        self.test_button.setText("测试中...")

        # TODO: 实现实际的连接测试
        # 这里先模拟一个简单的测试
        try:
            from core.llm.llm_provider import get_llm_provider
            provider = get_llm_provider().get_provider(self.current_provider)

            if provider:
                # 尝试获取模型列表
                models = provider.get_models()
                if models:
                    QMessageBox.information(
                        self,
                        "测试成功",
                        f"连接成功！\n\n可用模型数量: {len(models)}"
                    )
                else:
                    QMessageBox.warning(
                        self,
                        "测试失败",
                        "无法获取模型列表，请检查 API Key 和网络连接。"
                    )
            else:
                QMessageBox.warning(
                    self,
                    "测试失败",
                    "Provider 未正确初始化。"
                )
        except Exception as e:
            QMessageBox.critical(
                self,
                "测试失败",
                f"连接失败：{str(e)}"
            )
        finally:
            self.test_button.setEnabled(True)
            self.test_button.setText("测试连接")

    def _on_save(self):
        """保存配置"""
        if not self.current_provider:
            return

        config = self.llm_config.get_provider(self.current_provider)
        if not config:
            return

        # 更新配置
        config.api_key = self.api_key_edit.text()
        config.base_url = self.base_url_edit.text()
        config.chat_model = self.chat_model_combo.currentText()
        config.embedding_model = self.embedding_model_combo.currentText()
        config.enabled_chat = self.chat_enabled_checkbox.isChecked()
        config.enabled_embedding = self.embedding_enabled_checkbox.isChecked()
        # support_vision 从模型信息动态获取，不需要保存

        # 保存到文件
        self.llm_config.add_provider(self.current_provider, config)

        # 刷新模型列表
        from core.llm.llm_provider import get_llm_provider
        get_llm_provider().refresh_provider_models(self.current_provider, force=True)

        self.save_button.setEnabled(False)
        self.config_changed.emit()

        QMessageBox.information(
            self,
            "保存成功",
            "配置已保存！模型列表已刷新。"
        )
