"""每订阅者独立有界邮箱的异步事件分发器。"""

import itertools
import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4


logger = logging.getLogger(__name__)
_STOP_EVENT = object()


class BackpressurePolicy:
    """邮箱满时的显式处理策略。"""

    REJECT = "reject"
    COALESCE = "coalesce"
    DROP_OLDEST = "drop_oldest"
    ALL = frozenset((REJECT, COALESCE, DROP_OLDEST))


@dataclass(frozen=True, slots=True)
class PublishReceipt:
    """异步发布回执，queue_full 表示至少一个邮箱拒绝接收。"""

    event_id: int
    accepted: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class EventDeliveryStats:
    """订阅者维度的分发统计。"""

    queued: int
    delivered: int
    coalesced: int
    dropped: int
    failed: int
    lag_ms: float


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """带单调序号和发布时间的内部事件。"""

    event_id: int
    publisher_id: str
    key: str
    old_value: Any
    new_value: Any
    published_at_ns: int


@dataclass(slots=True)
class _Mailbox:
    """单订阅邮箱及其独立 worker。"""

    subscription_id: str
    subscriber_id: str
    callback: Callable
    queue: queue.Queue
    worker: threading.Thread
    closed: bool = False
    delivered: int = 0
    coalesced: int = 0
    dropped: int = 0
    failed: int = 0
    lag_ms: float = 0.0


class EventDispatcher:
    """通过独立 worker 隔离慢订阅者，并提供三种显式背压策略。"""

    DEFAULT_QUEUE_CAPACITY = 256

    def __init__(self, default_queue_capacity: int = DEFAULT_QUEUE_CAPACITY):
        self._default_capacity = default_queue_capacity
        self._lock = threading.RLock()
        self._mailboxes: Dict[str, _Mailbox] = {}
        self._sequence = itertools.count(1)
        self._closed = False

    def subscribe(self, subscriber_id, target_plugin_id, target_key, callback, queue_capacity=None):
        """注册订阅并启动独立邮箱 worker，返回 subscription_id。"""
        capacity = queue_capacity or self._default_capacity
        subscription_id = f"{subscriber_id}:{target_plugin_id}:{target_key}:{uuid4().hex}"
        mailbox = _Mailbox(
            subscription_id=subscription_id,
            subscriber_id=subscriber_id,
            callback=callback,
            queue=queue.Queue(maxsize=capacity),
            worker=None,
        )
        worker = threading.Thread(
            target=self._run_mailbox,
            args=(mailbox, target_plugin_id, target_key),
            daemon=True,
            name=f"EventDispatcher-{subscriber_id}",
        )
        mailbox.worker = worker
        with self._lock:
            if self._closed:
                raise RuntimeError("事件分发器已关闭")
            self._mailboxes[subscription_id] = mailbox
        worker.start()
        return subscription_id

    def publish(self, publisher_id, key, old_value, new_value, policy=BackpressurePolicy.REJECT) -> PublishReceipt:
        """向全部匹配邮箱投递事件，返回接收状态而非持久化确认。"""
        if policy not in BackpressurePolicy.ALL:
            raise ValueError(f"未知背压策略: {policy}")
        event = EventEnvelope(
            next(self._sequence), publisher_id, key, old_value, new_value, time.time_ns()
        )
        with self._lock:
            if self._closed:
                return PublishReceipt(event.event_id, False, "dispatcher_closed")
            mailboxes = list(self._mailboxes.values())
        accepted = True
        reason = ""
        for mailbox in mailboxes:
            if not self._offer(mailbox, event, policy):
                accepted = False
                reason = "queue_full"
        return PublishReceipt(event.event_id, accepted, reason)

    def _offer(self, mailbox, event, policy) -> bool:
        try:
            mailbox.queue.put_nowait(event)
            return True
        except queue.Full:
            pass
        if policy == BackpressurePolicy.REJECT:
            mailbox.dropped += 1
            return False
        if policy == BackpressurePolicy.DROP_OLDEST:
            self._discard_oldest(mailbox)
        else:
            mailbox.coalesced += self._drain(mailbox)
        try:
            mailbox.queue.put_nowait(event)
            return True
        except queue.Full:
            mailbox.dropped += 1
            return False

    @staticmethod
    def _discard_oldest(mailbox) -> None:
        try:
            mailbox.queue.get_nowait()
            mailbox.dropped += 1
        except queue.Empty:
            return

    @staticmethod
    def _drain(mailbox) -> int:
        drained = 0
        while True:
            try:
                mailbox.queue.get_nowait()
                drained += 1
            except queue.Empty:
                return drained

    def _run_mailbox(self, mailbox, publisher_id, target_key) -> None:
        """串行消费单订阅邮箱，异常只影响当前订阅回调。"""
        while True:
            item = mailbox.queue.get()
            if item is _STOP_EVENT or mailbox.closed:
                return
            try:
                mailbox.callback(publisher_id, target_key, item.old_value, item.new_value)
            except Exception as exc:
                mailbox.failed += 1
                logger.warning("异步订阅回调失败 %s: %s", mailbox.subscriber_id, exc)
                continue
            mailbox.delivered += 1
            mailbox.lag_ms = (time.time_ns() - item.published_at_ns) / 1_000_000

    def unsubscribe(self, subscription_id: str) -> None:
        """取消单个订阅并停止其 worker。"""
        with self._lock:
            mailbox = self._mailboxes.pop(subscription_id, None)
        if mailbox is not None:
            self._close_mailbox(mailbox)

    def unsubscribe_matching(self, subscriber_id=None, target_plugin_id=None, target_key=None) -> None:
        """按订阅方、目标插件和键的任意组合取消匹配邮箱。"""
        with self._lock:
            targets = []
            for subscription_id, mailbox in self._mailboxes.items():
                parts = subscription_id.split(":", 3)
                if subscriber_id is not None and parts[0] != subscriber_id:
                    continue
                if target_plugin_id is not None and parts[1] != target_plugin_id:
                    continue
                if target_key is not None and parts[2] != target_key:
                    continue
                targets.append(subscription_id)
        for subscription_id in targets:
            self.unsubscribe(subscription_id)

    def unsubscribe_subscriber(self, subscriber_id: str) -> None:
        """取消某订阅方的全部邮箱。"""
        with self._lock:
            targets = [
                key for key, mailbox in self._mailboxes.items()
                if mailbox.subscriber_id == subscriber_id
            ]
        for subscription_id in targets:
            self.unsubscribe(subscription_id)

    def unsubscribe_target(self, target_plugin_id: str) -> None:
        """停止某目标插件的全部邮箱，防止卸载后继续回调。"""
        with self._lock:
            targets = [
                key for key, mailbox in self._mailboxes.items()
                if mailbox.subscription_id.startswith(f"{target_plugin_id}:")
                or f":{target_plugin_id}:" in mailbox.subscription_id
            ]
        for subscription_id in targets:
            self.unsubscribe(subscription_id)

    def get_stats(self, subscriber_id: str) -> EventDeliveryStats:
        """汇总订阅方全部邮箱的队列与分发指标。"""
        with self._lock:
            mailboxes = [
                mailbox for mailbox in self._mailboxes.values()
                if mailbox.subscriber_id == subscriber_id
            ]
        return EventDeliveryStats(
            queued=sum(mailbox.queue.qsize() for mailbox in mailboxes),
            delivered=sum(mailbox.delivered for mailbox in mailboxes),
            coalesced=sum(mailbox.coalesced for mailbox in mailboxes),
            dropped=sum(mailbox.dropped for mailbox in mailboxes),
            failed=sum(mailbox.failed for mailbox in mailboxes),
            lag_ms=max((mailbox.lag_ms for mailbox in mailboxes), default=0.0),
        )

    def close(self) -> None:
        """关闭全部邮箱并等待 worker 退出，重复调用安全。"""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            mailboxes = list(self._mailboxes.values())
            self._mailboxes.clear()
        for mailbox in mailboxes:
            self._close_mailbox(mailbox)

    @staticmethod
    def _close_mailbox(mailbox) -> None:
        """投递停止标记并限时等待单个 worker。"""
        mailbox.closed = True
        try:
            mailbox.queue.put_nowait(_STOP_EVENT)
        except queue.Full:
            pass
        mailbox.worker.join(timeout=2.0)
