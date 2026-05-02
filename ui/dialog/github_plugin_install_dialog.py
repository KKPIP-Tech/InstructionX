"""
从 GitHub 安装插件对话框

支持单插件和多插件仓库的用户选择性安装。
"""

import asyncio
from typing import List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTextEdit, QCheckBox,
    QProgressBar, QFrame,
    QScrollArea, QWidget,
    QMessageBox, QStackedWidget
)
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QFont, QIcon

from core.plugin.github_plugin_installer import (
    GitHubPluginInstaller, InstallResult, RepoInspectionResult, PluginInfo
)
from core.plugin.manager import get_plugin_manager


class GitHubFetchWorker(QThread):
    """后台线程：获取仓库信息"""
    finished = Signal(RepoInspectionResult)
    error = Signal(str)

    def __init__(self, installer: GitHubPluginInstaller, url: str):
        super().__init__()
        self.installer = installer
        self.url = url

    def run(self):
        try:
            result = self.installer.inspect_repository(self.url)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class GitHubInstallWorker(QThread):
    """后台线程：安装插件"""
    finished = Signal(list)  # List[InstallResult]
    progress = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        installer: GitHubPluginInstaller,
        url: str,
        selected_plugins: List[str],
        install_dir: str
    ):
        super().__init__()
        self.installer = installer
        self.url = url
        self.selected_plugins = selected_plugins
        self.install_dir = install_dir

    def run(self):
        try:
            pm = get_plugin_manager()
            official_dir = pm.official_plugin_dir
            thirdparty_dir = pm.thirdparty_plugin_dir

            def on_progress(msg):
                self.progress.emit(msg)

            results = self.installer.install_from_url(
                self.url,
                selected_plugins=self.selected_plugins,
                official_dir=official_dir,
                thirdparty_dir=thirdparty_dir,
                progress_callback=on_progress
            )
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class PluginInfoWidget(QWidget):
    """单个插件信息展示组件"""

    def __init__(self, plugin_info: PluginInfo, parent=None):
        super().__init__(parent)
        self.plugin_info = plugin_info
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(5, 5, 5, 5)

        # 插件名称和版本
        header = QLabel(f"<b>{self.plugin_info.name}</b> (v{self.plugin_info.version})")
        header.setFont(QFont("", 10, QFont.Weight.Bold))
        layout.addWidget(header)

        # 插件 ID
        id_label = QLabel(f"ID: {self.plugin_info.plugin_id}")
        id_label.setStyleSheet("color: gray;")
        layout.addWidget(id_label)

        # 描述
        if self.plugin_info.description:
            desc_label = QLabel(self.plugin_info.description)
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)

        # 作者
        if self.plugin_info.author:
            author_label = QLabel(f"作者: {self.plugin_info.author}")
            author_label.setStyleSheet("color: gray;")
            layout.addWidget(author_label)

        # 依赖信息
        if self.plugin_info.dependencies:
            deps_text = ", ".join(
                f"{k}{v}" if v else k
                for k, v in self.plugin_info.dependencies.items()
            )
            deps_label = QLabel(f"依赖: {deps_text}")
            deps_label.setStyleSheet("color: #0078d4; font-size: 9pt;")
            deps_label.setWordWrap(True)
            layout.addWidget(deps_label)

        layout.addStretch()


class GitHubPluginInstallDialog(QDialog):
    """
    从 GitHub 安装插件对话框

    支持：
    - 输入 GitHub URL
    - 检查仓库类型（单插件/多插件）
    - 多插件时显示复选框列表供选择
    - 显示安装目录选项
    - 后台下载和安装
    """

    # 信号：插件安装完成
    plugin_installed = Signal(list)  # List[InstallResult]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.installer = GitHubPluginInstaller()
        self.repo_result: Optional[RepoInspectionResult] = None
        self.fetch_worker: Optional[GitHubFetchWorker] = None
        self.install_worker: Optional[GitHubInstallWorker] = None
        self._auto_install_dir = "thirdparty"  # 默认安装到第三方目录
        self._init_ui()

    def _init_ui(self):
        """初始化界面"""
        self.setWindowTitle("从 GitHub 安装插件")
        self.setMinimumSize(600, 450)
        self.setModal(True)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # ========== URL 输入区 ==========
        url_layout = QHBoxLayout()

        url_label = QLabel("GitHub URL:")
        url_label.setFixedWidth(80)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://github.com/owner/repo 或 git@github.com:owner/repo.git")
        self.check_btn = QPushButton("检查")
        self.check_btn.setFixedWidth(80)
        self.check_btn.clicked.connect(self._on_check_repo)

        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input, 1)
        url_layout.addWidget(self.check_btn)

        main_layout.addLayout(url_layout)

        # ========== 状态提示 ==========
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray;")
        self.status_label.setWordWrap(True)
        main_layout.addWidget(self.status_label)

        # ========== 插件信息区（堆叠窗口） ==========
        self.info_stack = QStackedWidget()
        main_layout.addWidget(self.info_stack, 1)

        # 空状态页面
        self.empty_widget = QLabel("点击「检查」按钮分析 GitHub 仓库")
        self.empty_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_widget.setStyleSheet("color: gray; border: 1px dashed gray; padding: 50px;")
        self.info_stack.addWidget(self.empty_widget)

        # 单插件页面
        self.single_plugin_widget = QScrollArea()
        self.single_plugin_widget.setWidgetResizable(True)
        self.single_plugin_content = QWidget()
        self.single_plugin_layout = QVBoxLayout(self.single_plugin_content)
        self.single_plugin_widget.setWidget(self.single_plugin_content)
        self.info_stack.addWidget(self.single_plugin_widget)

        # 多插件页面
        self.multi_plugin_widget = QScrollArea()
        self.multi_plugin_widget.setWidgetResizable(True)
        self.multi_plugin_content = QWidget()
        self.multi_plugin_layout = QVBoxLayout(self.multi_plugin_content)
        self.multi_plugin_widget.setWidget(self.multi_plugin_content)
        self.info_stack.addWidget(self.multi_plugin_widget)

        # 无效仓库页面
        self.invalid_widget = QLabel("该仓库不包含有效的插件描述文件")
        self.invalid_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.invalid_widget.setStyleSheet("color: red; border: 1px solid red; padding: 50px;")
        self.info_stack.addWidget(self.invalid_widget)

        # ========== 安装目录提示 ==========
        self.install_dir_label = QLabel("")
        self.install_dir_label.setStyleSheet("color: blue; padding: 5px; border: 1px solid #0078d4; background: #e8f4fd;")
        self.install_dir_label.setVisible(False)
        main_layout.addWidget(self.install_dir_label)

        # ========== 进度条 ==========
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)  # 不确定模式
        main_layout.addWidget(self.progress_bar)

        # ========== 按钮区 ==========
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setFixedWidth(100)
        self.cancel_btn.clicked.connect(self.reject)

        self.install_btn = QPushButton("安装")
        self.install_btn.setFixedWidth(100)
        self.install_btn.setEnabled(False)
        self.install_btn.clicked.connect(self._on_install)
        self.install_btn.setDefault(True)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.install_btn)

        main_layout.addLayout(btn_layout)

    def _set_info_page(self, page_name: str):
        """切换信息页面"""
        page_map = {
            "empty": 0,
            "single": 1,
            "multi": 2,
            "invalid": 3
        }
        if page_name in page_map:
            self.info_stack.setCurrentIndex(page_map[page_name])

    def _on_check_repo(self):
        """检查仓库按钮点击"""
        url = self.url_input.text().strip()
        if not url:
            self.status_label.setText("请输入 GitHub 仓库 URL")
            return

        self.check_btn.setEnabled(False)
        self.status_label.setText("正在检查仓库...")
        self._set_info_page("empty")

        self.fetch_worker = GitHubFetchWorker(self.installer, url)
        self.fetch_worker.finished.connect(self._on_repo_checked)
        self.fetch_worker.error.connect(self._on_fetch_error)
        self.fetch_worker.start()

    def _on_repo_checked(self, result: RepoInspectionResult):
        """仓库检查完成"""
        self.check_btn.setEnabled(True)
        self.fetch_worker = None

        if result.repo_type == "invalid":
            self.repo_result = None
            self.status_label.setText(result.error_message or "仓库无效")
            self._set_info_page("invalid")
            self.install_btn.setEnabled(False)
            self.install_dir_label.setVisible(False)
            return

        self.repo_result = result

        # 自动判定安装目录
        url = self.url_input.text().strip()
        parsed = self.installer.parse_github_url(url)
        if parsed:
            owner, _ = parsed
            if owner == GitHubPluginInstaller.KKPIP_TECH_ORG:
                dir_desc = "官方插件目录 (plugin/)"
                self._auto_install_dir = "official"
            else:
                dir_desc = "第三方插件目录 (custom_plugin/)"
                self._auto_install_dir = "thirdparty"
        else:
            dir_desc = "第三方插件目录 (custom_plugin/)"
            self._auto_install_dir = "thirdparty"

        self.install_dir_label.setText(f"将安装到: {dir_desc}")
        self.install_dir_label.setVisible(True)

        if result.repo_type == "single":
            self._show_single_plugin(result.plugins[0])
            self._set_info_page("single")
            self.status_label.setText("单插件仓库 - 确认信息后点击「安装」")
        elif result.repo_type == "multi":
            self._show_multi_plugins(result.plugins)
            self._set_info_page("multi")
            self.status_label.setText(f"多插件仓库 - 选择要安装的插件 (共 {len(result.plugins)} 个)")

        self.install_btn.setEnabled(True)

    def _on_fetch_error(self, error: str):
        """获取仓库信息出错"""
        self.check_btn.setEnabled(True)
        self.fetch_worker = None
        self.status_label.setText(f"错误: {error}")
        self._set_info_page("empty")

    def _show_single_plugin(self, plugin_info: PluginInfo):
        """显示单插件信息"""
        # 清除旧内容
        while self.single_plugin_layout.count():
            item = self.single_plugin_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        info_widget = PluginInfoWidget(plugin_info)
        self.single_plugin_layout.addWidget(info_widget)
        self.single_plugin_layout.addStretch()

    def _show_multi_plugins(self, plugins: List[PluginInfo]):
        """显示多插件列表"""
        # 清除旧内容
        while self.multi_plugin_layout.count():
            item = self.multi_plugin_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.plugin_checkboxes: List[QCheckBox] = []

        for plugin_info in plugins:
            checkbox = QCheckBox(f"{plugin_info.name} (v{plugin_info.version})")
            checkbox.setChecked(True)
            checkbox.setProperty("plugin_path", plugin_info.path)
            checkbox.setProperty("plugin_id", plugin_info.plugin_id)

            # 添加详细信息
            details = QLabel(f"  {plugin_info.description or '无描述'}")
            details.setStyleSheet("color: gray; font-size: 9pt;")
            details.setWordWrap(True)

            checkbox_layout = QVBoxLayout()
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.addWidget(details)

            container = QFrame()
            container.setFrameShape(QFrame.Shape.Box)
            container.setLineWidth(1)
            container.setLayout(checkbox_layout)

            self.multi_plugin_layout.addWidget(container)
            self.plugin_checkboxes.append(checkbox)

        # 全选/取消全选
        select_layout = QHBoxLayout()
        select_all_btn = QPushButton("全选")
        select_all_btn.clicked.connect(self._select_all)
        deselect_all_btn = QPushButton("取消全选")
        deselect_all_btn.clicked.connect(self._deselect_all)

        select_layout.addStretch()
        select_layout.addWidget(select_all_btn)
        select_layout.addWidget(deselect_all_btn)

        self.multi_plugin_layout.addLayout(select_layout)
        self.multi_plugin_layout.addStretch()

    def _select_all(self):
        """全选"""
        for checkbox in self.plugin_checkboxes:
            checkbox.setChecked(True)

    def _deselect_all(self):
        """取消全选"""
        for checkbox in self.plugin_checkboxes:
            checkbox.setChecked(False)

    def _on_install(self):
        """安装按钮点击"""
        if not self.repo_result:
            return

        url = self.url_input.text().strip()

        # 使用自动判定的安装目录
        install_dir = getattr(self, "_auto_install_dir", "thirdparty")

        # 确定要安装的插件
        selected_plugins = None
        if self.repo_result.repo_type == "multi":
            selected_plugins = []
            for checkbox in self.plugin_checkboxes:
                if checkbox.isChecked():
                    plugin_path = checkbox.property("plugin_path")
                    if plugin_path:
                        selected_plugins.append(plugin_path)

            if not selected_plugins:
                QMessageBox.warning(self, "提示", "请选择要安装的插件")
                return

        # 禁用按钮，开始安装
        self.install_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.check_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.status_label.setText("正在安装...")

        self.install_worker = GitHubInstallWorker(
            self.installer, url, selected_plugins, install_dir
        )
        self.install_worker.finished.connect(self._on_install_finished)
        self.install_worker.error.connect(self._on_install_error)
        self.install_worker.progress.connect(self._on_install_progress)
        self.install_worker.start()

    def _on_install_finished(self, results: List[InstallResult]):
        """安装完成"""
        self.install_worker = None
        self.progress_bar.setVisible(False)
        self.cancel_btn.setEnabled(True)
        self.check_btn.setEnabled(True)

        # 统计结果
        success_count = sum(1 for r in results if r.success)
        fail_count = len(results) - success_count

        if fail_count == 0:
            self.status_label.setText(f"安装成功！已安装 {success_count} 个插件")
            self.status_label.setStyleSheet("color: green;")
        else:
            self.status_label.setText(
                f"安装完成：{success_count} 个成功，{fail_count} 个失败"
            )
            self.status_label.setStyleSheet("color: orange;")

        # 显示详细结果
        details = "\n".join(
            f"  - {r.plugin_name or r.plugin_id}: {r.message}"
            for r in results
        )
        QMessageBox.information(
            self,
            "安装结果",
            f"安装{'全部成功' if fail_count == 0 else '部分完成'}：\n{details}"
        )

        # 发送信号
        self.plugin_installed.emit(results)

        # 如果至少有一个成功，关闭对话框
        if success_count > 0:
            self.accept()

    def _on_install_error(self, error: str):
        """安装出错"""
        self.install_worker = None
        self.progress_bar.setVisible(False)
        self.install_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        self.check_btn.setEnabled(True)
        self.status_label.setText(f"安装失败: {error}")
        self.status_label.setStyleSheet("color: red;")

        QMessageBox.critical(self, "安装失败", error)

    def _on_install_progress(self, msg: str):
        """安装进度更新"""
        self.status_label.setText(msg)

    def closeEvent(self, event):
        """对话框关闭事件"""
        # 取消正在进行的操作
        if self.fetch_worker and self.fetch_worker.isRunning():
            self.fetch_worker.terminate()
            self.fetch_worker.wait()

        if self.install_worker and self.install_worker.isRunning():
            self.install_worker.terminate()
            self.install_worker.wait()

        super().closeEvent(event)
