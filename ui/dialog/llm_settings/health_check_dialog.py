# ui/dialog/llm_settings/health_check_dialog.py
"""模型健康检查对话框

逐个探测当前实例合并列表中全部模型的可用性（HealthCheckWorker 后台线程），
实时渲染每行状态（等待中 / 检查中 / 正常 / 失败 / 跳过）、进度条与顶部
汇总计数（成功 / 失败 / 跳过 / 剩余）。

数据流：构造即启动探测；progress 信号按序更新行状态、进度条与汇总；
「取消」经 cancel() + wait() 安全终止 Worker；对话框关闭路径（关闭按钮 /
Esc / 窗口关闭）同样保证 Worker 回收，不遗留后台线程。

本对话框只做视图与交互编排，不修改任何配置，无需落盘与重渲染。
"""

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from core.i18n import tr
from core.llm.provider_interface import ModelCheckResult

from . import theme as _theme_module
from .constants import (
    FORM_BUTTON_HEIGHT, HEALTH_DIALOG_HEIGHT, HEALTH_DIALOG_WIDTH,
    MODEL_ROW_HEIGHT, MODEL_ROW_MARGIN_LEFT, MODEL_ROW_MARGIN_RIGHT,
    MODEL_ROW_SPACING, STATUS_TEXT_ELIDE_WIDTH,
    SUB_DIALOG_MARGIN, SUB_DIALOG_SPACING, WORKER_STOP_WAIT_MS,
)
from .theme import apply_dialog_theme
from .widgets import (
    _model_primary_type, install_focus_halo, make_badge, model_type_label,
)
from .workers import HealthCheckWorker


class _HealthCheckRow(QWidget):
    """健康检查单行：模型 id + 类型徽章 + 状态文案（按状态着色，走主题 token）

    状态文案：等待中（muted）/ 检查中（accent）/ ✓ 正常 + 延迟（success）/
    ✗ 失败 + 错误简述（danger，tooltip 完整错误）/ 跳过 + 原因（warning）。
    """

    def __init__(self, entry: Dict[str, Any], parent: Optional[QWidget] = None):
        """构造健康检查行

        Args:
            entry: 统一 schema 模型条目（取 id 与 capabilities 推导徽章）
            parent: 父控件
        """
        super().__init__(parent)
        self.setFixedHeight(MODEL_ROW_HEIGHT)
        type_key = _model_primary_type(entry)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            MODEL_ROW_MARGIN_LEFT, 0, MODEL_ROW_MARGIN_RIGHT, 0)
        layout.setSpacing(MODEL_ROW_SPACING)
        id_label = QLabel(str(entry.get("id", "")), self)
        id_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(id_label, 1)
        t = _theme_module.current_theme()
        badge = make_badge(
            model_type_label(type_key),
            t.model_type_colors.get(type_key, t.accent))
        layout.addWidget(badge)
        self._status = QLabel("", self)
        layout.addWidget(self._status)
        self.set_waiting()

    def _set_status(self, text: str, color: str, tooltip: str = "") -> None:
        """更新状态文案与颜色

        Args:
            text: 状态文本
            color: 文本颜色（主题 token）
            tooltip: 悬浮提示（如完整错误信息），空串不设置
        """
        self._status.setText(text)
        self._status.setStyleSheet(f"color: {color};")
        self._status.setToolTip(tooltip)

    def set_waiting(self) -> None:
        """置为「等待中」（探测尚未轮到该行）"""
        self._set_status(tr("dialog_llm_settings", "health.row.waiting"),
                         _theme_module.current_theme().fg_muted)

    def set_checking(self) -> None:
        """置为「检查中」（该行正在探测）"""
        self._set_status(tr("dialog_llm_settings", "health.row.checking"),
                         _theme_module.current_theme().accent)

    def set_cancelled(self) -> None:
        """置为「已取消」（用户取消时该行尚未探测）"""
        self._set_status(tr("dialog_llm_settings", "health.row.cancelled"),
                         _theme_module.current_theme().fg_muted)

    def set_result(self, result: ModelCheckResult) -> None:
        """按探测结果更新行状态（跳过 / 正常 / 失败）

        Args:
            result: 单模型探测结果
        """
        t = _theme_module.current_theme()
        if result.skipped:
            reason = result.skip_reason or tr(
                "dialog_llm_settings", "health.row.not_checked")
            self._set_status(tr("dialog_llm_settings", "health.row.skipped",
                                reason=reason), t.warning, reason)
            return
        if result.ok:
            latency = result.latency_ms or 0.0
            self._set_status(tr("dialog_llm_settings", "health.row.ok",
                                latency=f"{latency:.0f}"), t.success)
            return
        error = result.error or tr("dialog_llm_settings", "misc.unknown_error")
        short = self._status.fontMetrics().elidedText(
            error, Qt.TextElideMode.ElideRight, STATUS_TEXT_ELIDE_WIDTH)
        self._set_status(tr("dialog_llm_settings", "health.row.fail",
                            error=short), t.danger, error)


class HealthCheckDialog(QDialog):
    """模型健康检查对话框

    构造参数即探测上下文（实例 id + 实例名 + 合并后未 hidden 的模型条目），
    构造完成自动启动逐模型探测；「取消」安全终止探测并转为「关闭」。
    """

    def __init__(
        self,
        instance_id: str,
        instance_name: str,
        entries: List[Dict[str, Any]],
        parent: Optional[QWidget] = None,
    ):
        """构造健康检查对话框（构建 UI、换肤并自动启动探测）

        Args:
            instance_id: 提供商实例 id
            instance_name: 实例显示名（顶部说明行使用）
            entries: 合并后未 hidden 的统一 schema 模型条目列表
            parent: 父控件
        """
        super().__init__(parent)
        self.setWindowTitle(tr("dialog_llm_settings", "health.title"))
        self.setModal(True)
        self.resize(HEALTH_DIALOG_WIDTH, HEALTH_DIALOG_HEIGHT)
        self._instance_id = instance_id
        self._entries = list(entries)
        self._rows: List[_HealthCheckRow] = []
        self._worker: Optional[HealthCheckWorker] = None
        self._total = len(self._entries)
        self._done_count = 0
        self._ok_count = 0
        self._fail_count = 0
        self._skip_count = 0
        self._running = False
        self._init_ui(instance_name)
        apply_dialog_theme(self)
        install_focus_halo(self)
        self._start()

    # ==================== 界面构建 ====================

    def _init_ui(self, instance_name: str) -> None:
        """构建说明行 + 汇总行 + 进度条 + 模型行列表 + 底部按钮"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            SUB_DIALOG_MARGIN, SUB_DIALOG_MARGIN,
            SUB_DIALOG_MARGIN, SUB_DIALOG_MARGIN)
        layout.setSpacing(SUB_DIALOG_SPACING)
        header = QLabel(tr("dialog_llm_settings", "health.header",
                           name=instance_name, total=self._total), self)
        layout.addWidget(header)
        self._summary = QLabel("", self)
        self._summary.setObjectName("CountLabel")
        layout.addWidget(self._summary)
        self._progress = QProgressBar(self)
        self._progress.setRange(0, max(self._total, 1))
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        layout.addWidget(self._progress)
        layout.addWidget(self._build_scroll_area(), 1)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self._action_btn = QPushButton(tr("common", "cancel"), self)
        self._action_btn.setFixedHeight(FORM_BUTTON_HEIGHT)
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action_btn.clicked.connect(self._on_action_clicked)
        button_row.addWidget(self._action_btn)
        layout.addLayout(button_row)
        self._update_summary()

    def _build_scroll_area(self) -> QScrollArea:
        """构建模型行滚动列表（每行一个 _HealthCheckRow）"""
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("DetailContent")
        rows_layout = QVBoxLayout(content)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.setSpacing(0)
        for entry in self._entries:
            row = _HealthCheckRow(entry, content)
            rows_layout.addWidget(row)
            self._rows.append(row)
        if not self._entries:
            empty = QLabel(tr("dialog_llm_settings", "health.empty"), content)
            empty.setObjectName("EmptyHint")
            rows_layout.addWidget(empty)
        rows_layout.addStretch(1)
        scroll.setWidget(content)
        return scroll

    # ==================== 探测流程 ====================

    def _start(self) -> None:
        """启动逐模型探测（无模型时直接转关闭态）"""
        if not self._entries:
            self._action_btn.setText(tr("common", "close"))
            return
        self._running = True
        self._rows[0].set_checking()
        model_ids = [str(entry.get("id", "")) for entry in self._entries]
        worker = HealthCheckWorker(self._instance_id, model_ids, parent=self)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        worker.start()

    def _on_progress(
        self, index: int, _total: int, _model_id: str, result: ModelCheckResult,
    ) -> None:
        """单模型探测完成：更新行状态、计数、进度条、汇总，并标记下一行检查中

        Args:
            index: 当前完成的模型序号
            _total: 总数（信号负载，未使用）
            _model_id: 模型 id（信号负载，行定位以序号为准）
            result: 探测结果
        """
        if index >= len(self._rows):
            return
        self._rows[index].set_result(result)
        if result.skipped:
            self._skip_count += 1
        elif result.ok:
            self._ok_count += 1
        else:
            self._fail_count += 1
        self._done_count = index + 1
        self._progress.setValue(self._done_count)
        next_index = index + 1
        if next_index < len(self._rows):
            self._rows[next_index].set_checking()
        self._update_summary()

    def _on_worker_finished(self) -> None:
        """探测全部完成：显示汇总文案，按钮转「关闭」"""
        if not self._running:
            return
        self._running = False
        self._worker = None
        self._summary.setText(tr(
            "dialog_llm_settings", "health.summary_done",
            ok=self._ok_count, fail=self._fail_count, skip=self._skip_count))
        self._action_btn.setText(tr("common", "close"))

    def _update_summary(self) -> None:
        """刷新进行中汇总计数（成功 / 失败 / 跳过 / 剩余）"""
        remaining = self._total - self._done_count
        self._summary.setText(tr(
            "dialog_llm_settings", "health.summary_running",
            ok=self._ok_count, fail=self._fail_count,
            skip=self._skip_count, remaining=remaining))

    # ==================== 取消与关闭 ====================

    def _stop_worker(self) -> None:
        """安全终止探测 Worker（幂等；wait 会阻塞至当前探测结束）"""
        worker = self._worker
        self._worker = None
        self._running = False
        if worker is not None and worker.isRunning():
            worker.cancel()
            worker.wait(WORKER_STOP_WAIT_MS)

    def _on_action_clicked(self) -> None:
        """底部按钮：探测中为「取消」（终止并保留已得结果），否则为「关闭」"""
        if not self._running:
            self.accept()
            return
        self._stop_worker()
        for row in self._rows[self._done_count:]:
            row.set_cancelled()
        unchecked = self._total - self._done_count
        self._summary.setText(tr(
            "dialog_llm_settings", "health.summary_cancelled",
            ok=self._ok_count, fail=self._fail_count,
            skip=self._skip_count, unchecked=unchecked))
        self._action_btn.setText(tr("common", "close"))

    def reject(self) -> None:
        """Esc / 取消路径：先安全终止 Worker 再退出"""
        self._stop_worker()
        super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        """窗口关闭路径：先安全终止 Worker 再交给基类"""
        self._stop_worker()
        super().closeEvent(event)
