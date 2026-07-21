# ui/dialog/llm_settings/workers.py
"""LLM 设置界面后台 Worker 线程模块

提供模型拉取、连接检查与逐模型健康检查三个后台线程，避免主线程
同步 HTTP 请求阻塞界面。

线程模型：
- Worker 均为 QThread 子类，run() 在工作线程中执行；
- 所有对外通知通过 Qt 信号发出；跨线程连接时 Qt 自动将信号排队
  封送到接收者所在（UI）线程，槽函数中可直接操作控件；
- 构造时必须传入 parent（宿主对话框/面板），finished 信号统一
  连接 deleteLater 实现自销毁，禁止无主 Worker 泄漏；
- 宿主关闭时应对仍在运行的 Worker 调用 requestInterruption()
  并 wait() 回收；HealthCheckWorker 在循环中响应中断，其余为
  一次性网络请求（中断于请求结束后生效）。
"""

from typing import List

from PySide6.QtCore import QObject, QThread, Signal

from core.llm.llm_provider import get_llm_provider

from .constants import MODEL_CHECK_TIMEOUT_S


class FetchModelsWorker(QThread):
    """后台线程：强制刷新指定实例的模型列表并取回缓存结果.

    内部调用 LLMProvider.check_provider() 触发真实 API 拉取（成功时
    同步更新模型缓存与本地缓存文件），再经 get_cached_models() 取回
    ModelInfo 列表随 succeeded 信号发出；失败原因直接取
    check_provider 返回的错误信息，不再访问 last_errors。
    """

    succeeded = Signal(str, list)   # (实例 id, ModelInfo 列表)
    failed = Signal(str, str)       # (实例 id, 错误信息)

    def __init__(self, instance_id: str, parent: QObject):
        """构造 Worker

        Args:
            instance_id: 提供商实例 id
            parent: 宿主对象（必填，用于生命周期归属）
        """
        super().__init__(parent)
        self._instance_id = instance_id
        self.finished.connect(self.deleteLater)

    def run(self) -> None:
        provider = get_llm_provider()
        ok, error, _model_count = provider.check_provider(self._instance_id)
        if not ok:
            self.failed.emit(self._instance_id, error)
            return
        models = provider.get_cached_models(self._instance_id)
        self.succeeded.emit(self._instance_id, models)


class ConnectionCheckWorker(QThread):
    """后台线程：连通性检查（验证 API 配置可用性并统计可用模型数）.

    由旧 ValidateProviderWorker 迁移改造：内部改用
    LLMProvider.check_provider()，单次发出 checked 信号携带完整结果，
    使用方据 (成功, 错误, 模型数) 更新状态展示。
    """

    # (实例 id, 是否成功, 错误信息或 None, 模型数)
    checked = Signal(str, bool, object, int)

    def __init__(self, instance_id: str, parent: QObject):
        """构造 Worker

        Args:
            instance_id: 提供商实例 id
            parent: 宿主对象（必填，用于生命周期归属）
        """
        super().__init__(parent)
        self._instance_id = instance_id
        self.finished.connect(self.deleteLater)

    def run(self) -> None:
        ok, error, model_count = get_llm_provider().check_provider(
            self._instance_id)
        self.checked.emit(self._instance_id, ok, error, model_count)


class HealthCheckWorker(QThread):
    """后台线程：逐模型健康检查（最小化请求探测），支持中断取消.

    按给定模型 id 列表依次调用 LLMProvider.check_model()，每完成一个
    模型发出一次 progress 信号；循环中检查 isInterruptionRequested()，
    外部可调用 cancel()（或 requestInterruption()）在下一个模型探测
    开始前安全终止，整体结束以继承的 finished 信号为准。
    """

    # (当前序号, 总数, 模型 id, ModelCheckResult)
    progress = Signal(int, int, str, object)

    def __init__(
        self,
        instance_id: str,
        model_ids: List[str],
        parent: QObject,
        timeout: float = MODEL_CHECK_TIMEOUT_S,
    ):
        """构造 Worker

        Args:
            instance_id: 提供商实例 id
            model_ids: 待探测的模型 id 列表（按列表顺序探测）
            parent: 宿主对象（必填，用于生命周期归属）
            timeout: 单模型探测超时（秒），默认
                constants.MODEL_CHECK_TIMEOUT_S
        """
        super().__init__(parent)
        self._instance_id = instance_id
        self._model_ids = list(model_ids)
        self._timeout = timeout
        self.finished.connect(self.deleteLater)

    def run(self) -> None:
        provider = get_llm_provider()
        total = len(self._model_ids)
        for index, model_id in enumerate(self._model_ids):
            if self.isInterruptionRequested():
                break
            result = provider.check_model(
                self._instance_id, model_id, timeout=self._timeout)
            self.progress.emit(index, total, model_id, result)

    def cancel(self) -> None:
        """请求中断：当前模型探测结束后退出循环（非强制杀线程）"""
        self.requestInterruption()
