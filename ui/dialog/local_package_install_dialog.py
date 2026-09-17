# -*- coding: utf-8 -*-
"""本地插件包安装对话框

选择本地 zip（典型来源：GitHub 仓库的「Download ZIP」）→ 自动识别包内是
单插件还是插件集 → 勾选后一次装完。

识别与安装均在后台线程执行（大包解压、多插件逐个安装都不阻塞界面）；
运行中禁止直接关闭，避免强杀线程留下半成品目录。
"""

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QProgressBar,
    QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from core.i18n import get_language_manager, resolve_i18n_field, tr
from core.plugin.github_plugin_installer import (
    GitHubPluginInstaller, InstallResult, LocalInstallPlan, LocalPackageInspection,
)
from core.plugin.package_discovery import PACKAGE_KIND_INVALID, PACKAGE_KIND_SINGLE
from utils.logging_tools import LoggerManager, get_name
from InstructionX_UIKit import T, set_property
from InstructionX_UIKit.components import Button, CheckBox, Dialog, Message

# 模块级日志器（LoggerManager 为单例）
_logger = LoggerManager()

# i18n 文案分组名
_TR_GROUP = "dialog_local_package_install"

# 结果页索引
_PAGE_HINT = 0
_PAGE_RESULT = 1
_PAGE_INVALID = 2

# 关闭等待参数（与 GitHub 安装对话框保持一致的行为）
_CLOSE_POLL_INTERVAL_MS = 200
_CLOSE_WAIT_TIMEOUT_MS = 3000

# 与已安装版本的关系 → i18n 键（关系文案带版本号时在 _relation_text 中填充）
_RELATION_KEYS = {
    "new": "relation.new",
    "upgrade": "relation.upgrade",
    "downgrade": "relation.downgrade",
    "reinstall": "relation.reinstall",
}


def _resolve_field(value) -> str:
    """将可多语言字段（字符串或 {语言代码: 文案} 字典）解析为当前语言文案"""
    return resolve_i18n_field(value, get_language_manager().current_language())


def _confirm(parent, title: str, text: str) -> bool:
    """阻塞式确认对话框（UIKit Dialog，与插件管理对话框同款交互）"""
    dialog = Dialog(parent, title=title)
    dialog.set_text(text)
    return dialog.exec() == QDialog.DialogCode.Accepted


class _InspectWorker(QThread):
    """后台线程：识别本地插件包（解压 + 目录扫描）"""

    finished = Signal(object)      # LocalPackageInspection
    error = Signal(str)

    def __init__(self, installer: GitHubPluginInstaller, zip_path: str,
                 target_scope: Optional[str] = None):
        super().__init__()
        self._installer = installer
        self._zip_path = zip_path
        self._target_scope = target_scope

    def run(self) -> None:
        """执行识别，结果或异常经信号送回 UI 线程"""
        try:
            self.finished.emit(self._installer.inspect_local_package(
                self._zip_path, target_scope=self._target_scope))
        except Exception as e:  # noqa: BLE001 —— 线程内异常必须转为信号，不能抛出
            _logger.error(get_name(), f"识别本地插件包失败: {e}")
            self.error.emit(str(e))


class _InstallWorker(QThread):
    """后台线程：安装所选插件（逐个安装，逐插件回报进度）"""

    finished = Signal(list)        # List[InstallResult]
    progress = Signal(str)
    error = Signal(str)

    def __init__(self, installer: GitHubPluginInstaller, zip_path: str,
                 selected_plugins: List[str],
                 target_scope: Optional[str] = None):
        super().__init__()
        self._installer = installer
        self._zip_path = zip_path
        self._selected_plugins = selected_plugins
        self._target_scope = target_scope

    def run(self) -> None:
        """执行安装，结果或异常经信号送回 UI 线程"""
        try:
            results = self._installer.install_from_zip(
                self._zip_path,
                progress_callback=self.progress.emit,
                selected_plugins=self._selected_plugins,
                target_scope=self._target_scope,
            )
            self.finished.emit(results)
        except Exception as e:  # noqa: BLE001 —— 线程内异常必须转为信号，不能抛出
            _logger.error(get_name(), f"本地插件包安装失败: {e}")
            self.error.emit(str(e))


class LocalPackageInstallDialog(QDialog):
    """本地插件包安装对话框

    流程：选择压缩包 → 后台识别 → 单插件直接确认 / 插件集勾选 → 后台安装 → 结果汇总。

    Signals:
        plugin_installed: 至少一个插件安装成功（携带 List[InstallResult]），
            调用方据此刷新插件列表与技能面板
    """

    plugin_installed = Signal(list)

    def __init__(self, parent=None, installer: Optional[GitHubPluginInstaller] = None,
                 target_scope: Optional[str] = None):
        """初始化对话框

        Args:
            parent: 父窗口
            installer: 安装器实例；为 None 时自建（便于测试注入）
            target_scope: 新插件的目标范围（``official`` / ``thirdparty``）；
                由插件管理页传入当前 Tab 对应的范围，None 时按安装器既有规则
                （第三方目录）。已安装同 id 插件仍沿用其原目录
        """
        super().__init__(parent)
        self._installer = installer or GitHubPluginInstaller()
        self._target_scope = target_scope
        self._zip_path: str = ""
        self._inspection: Optional[LocalPackageInspection] = None
        self._rows: List[CheckBox] = []
        self._single_path: str = ""
        self._inspect_worker: Optional[_InspectWorker] = None
        self._install_worker: Optional[_InstallWorker] = None
        self._close_timer: Optional[QTimer] = None
        self._close_wait_elapsed = 0
        self._init_ui()

    # ------------------------------------------------------------- 界面搭建

    def _init_ui(self) -> None:
        """搭建对话框骨架（文件行 + 结果页 + 底部操作区）"""
        self.setWindowTitle(tr(_TR_GROUP, "window.title"))
        self.setMinimumSize(620, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)
        layout.addLayout(self._build_header())
        layout.addWidget(self._build_body(), stretch=1)
        layout.addLayout(self._build_footer())

    def _build_header(self) -> QHBoxLayout:
        """顶部：已选文件路径 + 选择压缩包按钮"""
        header = QHBoxLayout()
        self.file_label = QLabel(tr(_TR_GROUP, "label.no_file"))
        set_property(self.file_label, "role", "secondary")
        self.file_label.setWordWrap(True)
        self.choose_btn = Button(tr(_TR_GROUP, "button.choose_zip"), variant="default")
        self.choose_btn.clicked.connect(self._on_choose_file)

        header.addWidget(self.file_label, stretch=1)
        header.addWidget(self.choose_btn)
        return header

    def _build_body(self) -> QStackedWidget:
        """中部：提示页 / 结果页 / 无效包诊断页"""
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_hint_page())
        self.pages.addWidget(self._build_result_page())
        self.pages.addWidget(self._build_invalid_page())
        return self.pages

    def _build_hint_page(self) -> QWidget:
        """提示页：尚未选择压缩包 / 正在识别"""
        page = QWidget()
        layout = QVBoxLayout(page)
        self.hint_label = QLabel(tr(_TR_GROUP, "hint.select_package"))
        set_property(self.hint_label, "role", "secondary")
        self.hint_label.setWordWrap(True)
        layout.addStretch()
        layout.addWidget(self.hint_label)
        layout.addStretch()
        return page

    def _build_result_page(self) -> QWidget:
        """结果页：来源提示 + 插件勾选列表 + 计数行"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.source_label = QLabel()
        set_property(self.source_label, "role", "secondary")
        self.source_label.setWordWrap(True)
        layout.addWidget(self.source_label)

        self.rows_container = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(6)
        self.rows_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.rows_container)
        layout.addWidget(scroll, stretch=1)

        select_row = QHBoxLayout()
        self.summary_label = QLabel()
        set_property(self.summary_label, "role", "secondary")
        self.select_all_btn = Button(tr(_TR_GROUP, "button.select_all"),
                                    variant="default", size="sm")
        self.select_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        self.deselect_all_btn = Button(tr(_TR_GROUP, "button.deselect_all"),
                                       variant="default", size="sm")
        self.deselect_all_btn.clicked.connect(lambda: self._set_all_checked(False))
        select_row.addWidget(self.summary_label, stretch=1)
        select_row.addWidget(self.select_all_btn)
        select_row.addWidget(self.deselect_all_btn)
        layout.addLayout(select_row)
        return page

    def _build_invalid_page(self) -> QWidget:
        """无效包页：诊断信息 + 指引"""
        page = QWidget()
        layout = QVBoxLayout(page)
        self.invalid_title = QLabel(tr(_TR_GROUP, "invalid.title"))
        font = self.invalid_title.font()
        font.setBold(True)
        self.invalid_title.setFont(font)
        self.invalid_label = QLabel()
        self.invalid_label.setWordWrap(True)
        self.invalid_hint = QLabel(tr(_TR_GROUP, "invalid.hint"))
        set_property(self.invalid_hint, "role", "secondary")
        self.invalid_hint.setWordWrap(True)

        layout.addWidget(self.invalid_title)
        layout.addWidget(self.invalid_label)
        layout.addWidget(self.invalid_hint)
        layout.addStretch()
        return page

    def _build_footer(self) -> QHBoxLayout:
        """底部：进度/状态 + 安装与关闭按钮"""
        footer = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        self.status_label = QLabel()
        set_property(self.status_label, "role", "secondary")

        self.install_btn = Button(tr(_TR_GROUP, "button.install_selected"),
                                  variant="primary")
        self.install_btn.setEnabled(False)
        self.install_btn.clicked.connect(self._on_install_clicked)
        self.close_btn = Button(tr(_TR_GROUP, "button.close"), variant="default")
        self.close_btn.clicked.connect(self.close)

        footer.addWidget(self.progress)
        footer.addWidget(self.status_label, stretch=1)
        footer.addWidget(self.install_btn)
        footer.addWidget(self.close_btn)
        return footer

    # ------------------------------------------------------------- 选择与识别

    def _on_choose_file(self) -> None:
        """选择本地插件包并开始识别"""
        zip_path, _selected = QFileDialog.getOpenFileName(
            self, tr(_TR_GROUP, "title.select_zip"), "",
            tr(_TR_GROUP, "file_dialog.zip_filter"))
        if not zip_path:
            return
        self.start_inspect(zip_path)

    def start_inspect(self, zip_path: str) -> None:
        """识别指定插件包（供入口调用或测试直接驱动）

        Args:
            zip_path: 本地 zip 路径
        """
        self._zip_path = zip_path
        self.file_label.setText(Path(zip_path).name)
        self.hint_label.setText(tr(_TR_GROUP, "hint.scanning"))
        self.pages.setCurrentIndex(_PAGE_HINT)
        self._set_busy(tr(_TR_GROUP, "hint.scanning"))
        self._inspect_worker = _InspectWorker(self._installer, zip_path,
                                              self._target_scope)
        self._inspect_worker.finished.connect(self._on_inspect_finished)
        self._inspect_worker.error.connect(self._on_worker_error)
        self._inspect_worker.start()

    def _on_inspect_finished(self, inspection: LocalPackageInspection) -> None:
        """识别完成：按类型切页（无效包 / 单插件或插件集勾选列表）"""
        self._set_idle()
        self._inspection = inspection
        if inspection.kind == PACKAGE_KIND_INVALID:
            self._show_invalid(inspection)
            return
        self._show_plans(inspection)

    def _show_invalid(self, inspection: LocalPackageInspection) -> None:
        """展示无效包诊断信息"""
        detail = inspection.error or tr(_TR_GROUP, "invalid.unknown")
        if inspection.warnings:
            detail = f"{detail}\n" + "\n".join(inspection.warnings)
        self.invalid_label.setText(detail)
        self.pages.setCurrentIndex(_PAGE_INVALID)
        self.status_label.setText("")

    def _show_plans(self, inspection: LocalPackageInspection) -> None:
        """展示插件清单（单插件与插件集共用同一套勾选行）"""
        self._clear_rows()
        for plan in inspection.plans:
            self.rows_layout.insertWidget(self.rows_layout.count() - 1,
                                          self._make_plan_row(plan))
        if inspection.kind == PACKAGE_KIND_SINGLE:
            self.source_label.setText(tr(_TR_GROUP, "source.single"))
        elif inspection.has_index:
            self.source_label.setText(tr(_TR_GROUP, "source.index"))
        else:
            self.source_label.setText(tr(_TR_GROUP, "source.scan"))
        if inspection.warnings:
            self.source_label.setText(
                self.source_label.text() + "\n" + "\n".join(inspection.warnings))
        self.pages.setCurrentIndex(_PAGE_RESULT)
        self._update_summary()

    def _clear_rows(self) -> None:
        """清空上一次识别的勾选行"""
        self._rows = []
        self._single_path = ""
        while self.rows_layout.count() > 1:
            item = self.rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    # ------------------------------------------------------------- 单个插件行

    def _make_plan_row(self, plan: LocalInstallPlan) -> QFrame:
        """构造单个插件的展示行（勾选框 + 名称版本 + 关系 + 目标目录 + 描述）"""
        candidate = plan.candidate
        row = QFrame()
        row.setFrameShape(QFrame.Shape.Box)
        layout = QVBoxLayout(row)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        checkbox = CheckBox(f"{_resolve_field(candidate.name)} (v{candidate.version})",
                            checked=plan.default_selected)
        checkbox.setEnabled(candidate.valid)
        checkbox.setProperty("plugin_path", candidate.rel_path)
        checkbox.stateChanged.connect(self._update_summary)
        layout.addWidget(checkbox)
        self._rows.append(checkbox)
        if not candidate.rel_path:
            self._single_path = candidate.rel_path

        layout.addWidget(self._make_detail_label(plan))
        if candidate.valid:
            layout.addWidget(self._make_meta_label(plan))
        else:
            invalid = QLabel(tr(_TR_GROUP, "row.invalid", reason=candidate.error))
            set_property(invalid, "role", "danger")
            invalid.setWordWrap(True)
            layout.addWidget(invalid)
        return row

    def _make_detail_label(self, plan: LocalInstallPlan) -> QLabel:
        """插件描述标签（多语言字段解析后展示）"""
        candidate = plan.candidate
        text = _resolve_field(candidate.description) if candidate.description \
            else tr(_TR_GROUP, "row.no_description")
        label = QLabel(f"  {text}")
        set_property(label, "role", "secondary")
        label.setWordWrap(True)
        return label

    def _make_meta_label(self, plan: LocalInstallPlan) -> QLabel:
        """插件元信息标签：包内路径 + 安装关系 + 目标目录 + 依赖"""
        parts = [f"id: {plan.candidate.descriptor_id}"]
        if plan.candidate.rel_path:
            parts.append(tr(_TR_GROUP, "row.path", path=plan.candidate.rel_path))
        parts.append(self._relation_text(plan))
        parts.append(tr(_TR_GROUP, f"scope.{plan.target_scope}"))
        if not plan.candidate.declared_in_index and self._inspection \
                and self._inspection.has_index:
            parts.append(tr(_TR_GROUP, "row.undeclared"))
        if plan.candidate.dependencies:
            deps = ", ".join(f"{k}{v}" for k, v in plan.candidate.dependencies.items())
            parts.append(tr(_TR_GROUP, "row.dependencies", deps=deps))
        label = QLabel("  " + " · ".join(parts))
        set_property(label, "role", "secondary")
        label.setWordWrap(True)
        return label

    def _relation_text(self, plan: LocalInstallPlan) -> str:
        """安装关系文案（与已安装版本的对比）"""
        key = _RELATION_KEYS.get(plan.relation, "relation.new")
        return tr(_TR_GROUP, key, prev=plan.prev_version,
                  version=plan.candidate.version)

    # ------------------------------------------------------------- 选择与安装

    def _set_all_checked(self, checked: bool) -> None:
        """全选 / 全不选（不可安装项保持不可选）"""
        for checkbox in self._rows:
            if checkbox.isEnabled():
                checkbox.setChecked(checked)
        self._update_summary()

    def _selected_paths(self) -> List[str]:
        """当前勾选的插件（返回包内相对路径或插件 id）"""
        paths = []
        for checkbox in self._rows:
            if checkbox.isChecked() and checkbox.isEnabled():
                paths.append(checkbox.property("plugin_path") or "")
        return paths

    def _update_summary(self, *_args) -> None:
        """刷新计数行与安装按钮可用状态"""
        total = len(self._rows)
        installable = sum(1 for c in self._rows if c.isEnabled())
        selected = len(self._selected_paths())
        self.summary_label.setText(tr(
            _TR_GROUP, "label.selection_summary", selected=selected,
            total=total, invalid=total - installable))
        self.install_btn.setEnabled(selected > 0)

    def _on_install_clicked(self) -> None:
        """安装勾选的插件（后台执行）

        勾选项包含降级时先弹一次确认：降级可能造成数据不兼容或配置丢失，
        与「检查更新 / 升级 / 降级」路径的保护保持一致。
        """
        selected = self._selected_paths()
        if not selected:
            Message.info(self, tr(_TR_GROUP, "message.no_selection"))
            return
        if not self._confirm_downgrade(selected):
            return
        self._set_busy(tr(_TR_GROUP, "hint.installing"))
        self._install_worker = _InstallWorker(self._installer, self._zip_path, selected,
                                              self._target_scope)
        self._install_worker.progress.connect(self._on_install_progress)
        self._install_worker.finished.connect(self._on_install_finished)
        self._install_worker.error.connect(self._on_worker_error)
        self._install_worker.start()

    def _confirm_downgrade(self, selected: List[str]) -> bool:
        """勾选项含降级时请求用户确认

        Args:
            selected: 已勾选的插件（包内相对路径或插件 id）

        Returns:
            bool: 是否继续安装（无降级项时直接返回 True）
        """
        downgrades = [plan for plan in self._selected_plans(selected)
                      if plan.relation == "downgrade"]
        if not downgrades:
            return True
        details = "\n".join(
            f"  - {_resolve_field(plan.candidate.name)}："
            f"{plan.prev_version} → {plan.candidate.version}"
            for plan in downgrades)
        return _confirm(self, tr(_TR_GROUP, "title.confirm_downgrade"),
                        tr(_TR_GROUP, "message.downgrade_confirm", details=details))

    def _selected_plans(self, selected: List[str]) -> List[LocalInstallPlan]:
        """按勾选结果取出对应的安装计划"""
        if not self._inspection:
            return []
        wanted = {item.strip("/") for item in selected}
        return [plan for plan in self._inspection.plans
                if plan.candidate.valid
                and (plan.candidate.rel_path in wanted
                     or plan.candidate.descriptor_id in wanted)]

    def _on_install_progress(self, message: str) -> None:
        """安装进度文本更新"""
        self.status_label.setText(message)

    def _on_install_finished(self, results: List[InstallResult]) -> None:
        """安装完成：汇总结果、通知调用方刷新，然后关闭"""
        self._set_idle()
        if not results:
            Message.warning(self, tr(_TR_GROUP, "result.title"),
                            tr(_TR_GROUP, "result.empty"))
            return
        success = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        details = "\n".join(
            tr(_TR_GROUP, "result.item", name=r.plugin_name or r.plugin_id or "-",
               message=r.message) for r in results)
        key = "result.partial" if failed else "result.all_success"
        dialog = Dialog(self, title=tr(_TR_GROUP, "result.title"),
                        ok_text=tr(_TR_GROUP, "result.ok"), show_cancel=False)
        dialog.set_text(tr(_TR_GROUP, key, details=details))
        dialog.exec()
        if success:
            self.plugin_installed.emit(results)
        self.close()

    def _on_worker_error(self, error: str) -> None:
        """后台线程异常：提示并恢复交互（不关闭对话框，便于重试）"""
        self._set_idle()
        _logger.error(get_name(), f"本地插件包操作失败: {error}")
        Message.warning(self, tr(_TR_GROUP, "result.title"), error)

    # ------------------------------------------------------------- 忙碌状态

    def _set_busy(self, text: str) -> None:
        """进入忙碌状态：进度条可见、操作按钮禁用"""
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.status_label.setText(text)
        self.choose_btn.setEnabled(False)
        self.install_btn.setEnabled(False)

    def _set_idle(self) -> None:
        """恢复空闲状态"""
        self.progress.setVisible(False)
        self.progress.setRange(0, 1)
        self.status_label.setText("")
        self.choose_btn.setEnabled(True)
        self._update_summary()

    # ------------------------------------------------------------- 关闭处理

    def closeEvent(self, event) -> None:
        """后台线程仍在运行时优雅关闭（避免强杀线程留下半成品目录）"""
        if self._has_running_worker():
            self._request_worker_interruption()
            self.setEnabled(False)
            event.ignore()
            self._start_close_wait()
            return
        super().closeEvent(event)

    def _has_running_worker(self) -> bool:
        """是否有后台线程仍在运行"""
        inspect_running = bool(self._inspect_worker and self._inspect_worker.isRunning())
        install_running = bool(self._install_worker and self._install_worker.isRunning())
        return inspect_running or install_running

    def _request_worker_interruption(self) -> None:
        """请求运行中的后台线程中断"""
        for worker in (self._inspect_worker, self._install_worker):
            if worker and worker.isRunning():
                worker.requestInterruption()

    def _start_close_wait(self) -> None:
        """启动轮询定时器，等待后台线程结束后真正关闭"""
        self._close_wait_elapsed = 0
        self._close_timer = QTimer(self)
        self._close_timer.setInterval(_CLOSE_POLL_INTERVAL_MS)
        self._close_timer.timeout.connect(self._on_close_wait_tick)
        self._close_timer.start()

    def _on_close_wait_tick(self) -> None:
        """轮询线程状态：结束即关闭，超时兜底强制终止后关闭"""
        if not self._has_running_worker():
            self._close_timer.stop()
            self.close()
            return
        self._close_wait_elapsed += _CLOSE_POLL_INTERVAL_MS
        if self._close_wait_elapsed < _CLOSE_WAIT_TIMEOUT_MS:
            return
        self._close_timer.stop()
        _logger.warning(
            get_name(),
            f"等待本地插件包后台线程结束超时（{_CLOSE_WAIT_TIMEOUT_MS}ms），强制终止后关闭")
        for worker in (self._inspect_worker, self._install_worker):
            if worker and worker.isRunning():
                worker.terminate()
                worker.wait()
        self.close()
