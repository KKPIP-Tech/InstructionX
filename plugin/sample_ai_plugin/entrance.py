"""示例 AI 插件主入口

演示 LLMPluginService 的完整集成方式。
支持对话、流式输出、工具调用。
"""

from core.plugin.plugin_interface import IPlugin
from core.llm import get_llm_plugin_service
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit,
    QLabel, QComboBox, QStyle
)
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QIcon
import logging
import threading

logger = logging.getLogger(__name__)


class StreamWorker(QThread):
    """流式响应工作线程"""
    chunk_received = Signal(str)
    finished = Signal(dict)

    def __init__(self, svc, conv_id, message, provider, model, parent=None):
        super().__init__(parent)
        self.svc = svc
        self.conv_id = conv_id
        self.message = message
        self.provider = provider
        self.model = model

    def run(self):
        try:
            def callback(chunk):
                self.chunk_received.emit(chunk.content)

            content = self.svc.stream_send_message(
                self.conv_id,
                self.message,
                callback=callback,
            )
            self.finished.emit({"success": True, "content": content})
        except Exception as e:
            self.finished.emit({"success": False, "error": str(e)})


class SampleAIPlugin(IPlugin):
    """示例 AI 插件

    演示 LLMPluginService 的使用方式：
    - 创建对话
    - 发送消息（同步）
    - 流式发送消息
    - 工具调用
    """

    @property
    def plugin_name(self) -> str:
        return "示例\nAI插件"

    @property
    def skill_icon(self) -> QIcon:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            return app.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)
        return QIcon()

    @property
    def skill_description(self) -> str:
        return "LLMPluginService 演示插件"

    def __init__(self, services=None):
        super().__init__()
        self._llm = (services.llm_facade
                     if services
                     else get_llm_plugin_service())
        self._logger = (services.logger if services else None) or logger
        self._conv_id: str | None = None
        self._providers: list = []

    @property
    def llm_tools(self):
        """声明插件暴露的 LLM 工具"""
        from .tools import get_sample_tools
        return get_sample_tools()

    def _populate_providers(self):
        self._providers = self._llm.get_available_providers()
        self._provider_combo.blockSignals(True)
        self._provider_combo.clear()
        if self._providers:
            for p in self._providers:
                self._provider_combo.addItem(p.name, p.name)
            self._on_provider_changed()
        else:
            self._model_combo.clear()
            self._model_combo.addItem("无可用 Provider", "")
        self._provider_combo.blockSignals(False)

    def _on_provider_changed(self):
        idx = self._provider_combo.currentIndex()
        if idx < 0 or idx >= len(self._providers):
            return
        provider = self._providers[idx]
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        for m in provider.models:
            self._model_combo.addItem(m.name or m.id, m.id)
        if not provider.models:
            self._model_combo.addItem(provider.current_chat_model or "default", "default")
        self._model_combo.blockSignals(False)

    def _get_selected(self) -> tuple:
        provider = self._provider_combo.currentData() or "default"
        model = self._model_combo.currentData() or "default"
        return provider, model

    def _create_widget(self, parent, data_provider=None) -> QWidget:
        w = QWidget(parent)
        layout = QVBoxLayout(w)

        layout.addWidget(QLabel("示例 AI 插件 — LLMPluginService 演示"))

        # Provider / Model 选择
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("Provider:"))
        self._provider_combo = QComboBox()
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        selector_layout.addWidget(self._provider_combo)

        selector_layout.addWidget(QLabel("Model:"))
        self._model_combo = QComboBox()
        selector_layout.addWidget(self._model_combo)
        layout.addLayout(selector_layout)

        self._output = QTextEdit()
        self._output.setReadOnly(True)
        layout.addWidget(self._output)

        self._populate_providers()

        btn_chat = QPushButton("发送测试消息（同步）")
        btn_chat.clicked.connect(self._on_sync_chat)
        layout.addWidget(btn_chat)

        btn_stream = QPushButton("流式发送消息")
        btn_stream.clicked.connect(self._on_stream_chat)
        layout.addWidget(btn_stream)

        btn_tools = QPushButton("使用工具调用")
        btn_tools.clicked.connect(self._on_tools)
        layout.addWidget(btn_tools)

        return w

    def _ensure_conversation(self, provider, model):
        if not self._conv_id:
            self._append(f"[系统] 创建对话 ({provider}/{model})...")
        self._conv_id = self._llm.create_conversation(
            system_prompt="你是一个友好的助手，用简洁的语言回答。",
            provider=provider,
            model=model,
        )
        self._append(f"[系统] 对话已创建: {self._conv_id[:8]}...")

    def _append(self, text: str):
        self._output.append(text)

    def _on_sync_chat(self):
        provider, model = self._get_selected()
        self._ensure_conversation(provider, model)
        self._append(f"[用户] 请用三句话解释量子计算 ({provider}/{model})")

        def send():
            try:
                content = self._llm.send_message(
                    self._conv_id,
                    "请用三句话解释量子计算",
                )
                self._append(f"[助手] {content}")
            except Exception as e:
                self._append(f"[错误] {e}")

        t = threading.Thread(target=send)
        t.start()

    def _on_stream_chat(self):
        provider, model = self._get_selected()
        self._ensure_conversation(provider, model)
        self._append(f"[用户] 解释什么是深度学习 ({provider}/{model})")

        self._worker = StreamWorker(
            self._llm,
            self._conv_id,
            "解释什么是深度学习",
            provider,
            model,
        )
        self._worker.chunk_received.connect(self._on_chunk)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_chunk(self, text: str):
        if text:
            self._append(text)

    def _on_finished(self, result: dict):
        if not result.get("success"):
            self._append(f"[错误] {result.get('error')}")

    def _on_tools(self):
        provider, model = self._get_selected()
        self._ensure_conversation(provider, model)

        # 注册示例工具
        from .tools import register_sample_tools
        register_sample_tools()

        self._append("[系统] 工具已注册，开始工具调用...")

        def send():
            try:
                executor = self._llm.get_tool_executor()
                messages = [{"role": "user", "content": "计算 (2+3)*4 的结果"}]
                msgs, results, final = executor.chat_with_tools(
                    messages, provider=provider, model=model,
                )
                for r in results:
                    self._append(f"[工具 {r.tool_name}] {r.result}")
                self._append(f"[助手] {final}")
            except Exception as e:
                self._append(f"[错误] {e}")

        t = threading.Thread(target=send)
        t.start()
