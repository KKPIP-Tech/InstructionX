"""
任务报告生成器服务
"""

import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from core.data.data_provider import DataProvider, DataProviderError, DataNamespace

from utils.logging_tools import LoggerManager, get_name


class ReporterService:
    """报告生成服务"""

    _logger = LoggerManager()

    def __init__(self, plugin_id: str):
        """
        初始化报告服务

        Args:
            plugin_id: 插件ID
        """
        self.plugin_id = plugin_id
        self.data_provider = DataProvider()
        self.event_log = []

    def get_active_task_manager_id(self) -> Optional[str]:
        """
        自动获取活跃的 TaskManager 实例 ID

        Returns:
            活跃的 TaskManager 插件 ID，如果不存在则返回 None
        """
        return self.data_provider.get_active_instance("TaskManager")

    def _resolve_task_manager_id(self, task_manager_id: Optional[str]) -> Optional[str]:
        """
        解析 TaskManager ID，如果未提供则自动获取活跃实例

        Args:
            task_manager_id: 传入的 TaskManager ID，如果为 None 或无效则自动获取

        Returns:
            有效的 TaskManager ID 或 None
        """
        if task_manager_id:
            return task_manager_id
        return self.get_active_task_manager_id()

    def subscribe_to_task_manager(self, task_manager_id: Optional[str] = None) -> bool:
        """
        订阅任务管理器的数据变更

        Args:
            task_manager_id: 任务管理器插件ID，如果为 None 则自动获取活跃实例

        Returns:
            是否订阅成功
        """
        # 自动获取活跃的 TaskManager 实例
        resolved_id = self._resolve_task_manager_id(task_manager_id)
        if not resolved_id:
            self._logger.warning(get_name(), 'Subscribe failed: No active TaskManager instance found')
            return False

        try:
            # 订阅统计信息变更
            self.data_provider.subscribe(
                subscriber_id=self.plugin_id,
                target_plugin_id=resolved_id,
                target_key="statistics",
                callback=self._on_statistics_changed
            )

            # 订阅事件变更
            self.data_provider.subscribe(
                subscriber_id=self.plugin_id,
                target_plugin_id=resolved_id,
                target_key="last_event",
                callback=self._on_task_event
            )

            return True
        except DataProviderError as e:
            self._logger.warning(get_name(), f'Subscribe failed: {e}')
            return False

    def unsubscribe_from_task_manager(self, task_manager_id: Optional[str] = None):
        """
        取消订阅任务管理器

        Args:
            task_manager_id: 可选，任务管理器插件ID
        """
        self.data_provider.unsubscribe(self.plugin_id, task_manager_id)

    def _on_statistics_changed(self, target_plugin_id: str, key: str, old_value: Any, new_value: Any):
        """统计信息变更回调"""
        self.event_log.append({
            "timestamp": datetime.now().isoformat(),
            "type": "statistics_changed",
            "plugin_id": target_plugin_id,
            "old_stats": old_value,
            "new_stats": new_value
        })

        # 保存事件日志
        self._save_event_log()

    def _on_task_event(self, target_plugin_id: str, key: str, old_value: Any, new_value: Any):
        """任务事件回调"""
        if new_value and "type" in new_value:
            self.event_log.append({
                "timestamp": datetime.now().isoformat(),
                "type": "task_event",
                "plugin_id": target_plugin_id,
                "event_type": new_value.get("type"),
                "event_data": new_value
            })

            # 保存事件日志
            self._save_event_log()

    def _save_event_log(self) -> None:
        """保存事件日志"""
        try:
            self.data_provider.set_plugin_data(
                self.plugin_id,
                "event_log",
                self.event_log,
                DataNamespace.PRIVATE
            )
        except DataProviderError as e:
            # 插件未注册，记录错误但不中断程序
            self._logger.warning(get_name(), f'Cannot save event log: {e}')

    def get_statistics_report(self, task_manager_id: Optional[str] = None) -> Dict[str, Any]:
        """
        获取统计报告

        Args:
            task_manager_id: 任务管理器插件ID，如果为 None 则自动获取活跃实例

        Returns:
            统计报告字典
        """
        # 自动获取活跃的 TaskManager 实例
        resolved_id = self._resolve_task_manager_id(task_manager_id)
        if not resolved_id:
            return {"error": "未找到活跃的 TaskManager 实例"}

        try:
            stats = self.data_provider.get_plugin_data(
                resolved_id,
                "statistics",
                DataNamespace.PUBLIC,
                None
            )

            if not stats:
                return {"error": "无法获取统计信息"}

            # 计算完成率
            total = stats.get("total", 0)
            completed = stats.get("completed", 0)
            completion_rate = (completed / total * 100) if total > 0 else 0

            return {
                "generated_at": datetime.now().isoformat(),
                "task_manager_id": resolved_id,
                "statistics": stats,
                "metrics": {
                    "completion_rate": round(completion_rate, 2),
                    "pending_ratio": round(stats.get("pending", 0) / total * 100, 2) if total > 0 else 0,
                    "in_progress_ratio": round(stats.get("in_progress", 0) / total * 100, 2) if total > 0 else 0
                }
            }
        except Exception as e:
            return {"error": str(e)}

    def get_event_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取事件历史

        Args:
            limit: 最大返回数量

        Returns:
            事件列表
        """
        try:
            self.event_log = self.data_provider.get_plugin_data(
                self.plugin_id,
                "event_log",
                DataNamespace.PRIVATE,
                []
            )
        except DataProviderError:
            # 插件未注册，返回空列表
            self.event_log = []

        return self.event_log[-limit:]

    def generate_report(self, task_manager_id: Optional[str] = None, format: str = "json") -> str:
        """
        生成完整报告

        Args:
            task_manager_id: 任务管理器插件ID，如果为 None 则自动获取活跃实例
            format: 报告格式 (json, txt, html)

        Returns:
            报告文件的相对路径
        """
        # 自动获取活跃的 TaskManager 实例
        resolved_id = self._resolve_task_manager_id(task_manager_id)
        if not resolved_id:
            raise ValueError("未找到活跃的 TaskManager 实例")

        # 获取统计数据
        stats_report = self.get_statistics_report(resolved_id)

        # 获取事件历史
        events = self.get_event_history(50)

        report_data = {
            "generated_at": datetime.now().isoformat(),
            "task_manager_id": resolved_id,
            "statistics_report": stats_report,
            "recent_events": events,
            "total_events": len(self.event_log)
        }

        if format == "json":
            content = json.dumps(report_data, ensure_ascii=False, indent=2).encode('utf-8')
            filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        elif format == "txt":
            lines = [
                "任务管理器报告",
                "=" * 50,
                f"生成时间: {report_data['generated_at']}",
                f"任务管理器ID: {resolved_id}",
                "",
                "统计信息:",
                "-" * 30
            ]

            if "statistics" in stats_report:
                stats = stats_report["statistics"]
                lines.extend([
                    f"  总计: {stats.get('total', 0)}",
                    f"  待办: {stats.get('pending', 0)}",
                    f"  进行中: {stats.get('in_progress', 0)}",
                    f"  已完成: {stats.get('completed', 0)}",
                    f"  已取消: {stats.get('cancelled', 0)}",
                    ""
                ])

            if "metrics" in stats_report:
                lines.extend([
                    "性能指标:",
                    "-" * 30,
                    f"  完成率: {stats_report['metrics'].get('completion_rate', 0)}%",
                    f"  待办比例: {stats_report['metrics'].get('pending_ratio', 0)}%",
                    f"  进行中比例: {stats_report['metrics'].get('in_progress_ratio', 0)}%",
                    ""
                ])

            lines.extend([
                "最近事件:",
                "-" * 30
            ])

            for event in events[-10:]:
                event_type = event.get("type", "unknown")
                timestamp = event.get("timestamp", "")
                lines.append(f"  [{timestamp}] {event_type}")

            lines.append("")
            lines.append(f"总事件数: {report_data['total_events']}")

            content = "\n".join(lines).encode('utf-8')
            filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

        elif format == "html":
            html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>任务管理器报告</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
        .metric {{ margin: 10px 0; padding: 10px; background: #e7f3ff; border-radius: 5px; }}
    </style>
</head>
<body>
    <h1>任务管理器报告</h1>
    <p><strong>生成时间:</strong> {report_data['generated_at']}</p>
    <p><strong>任务管理器ID:</strong> {resolved_id}</p>

    <h2>统计信息</h2>
"""

            if "statistics" in stats_report:
                stats = stats_report["statistics"]
                html += f"""
    <table>
        <tr><th>状态</th><th>数量</th></tr>
        <tr><td>总计</td><td>{stats.get('total', 0)}</td></tr>
        <tr><td>待办</td><td>{stats.get('pending', 0)}</td></tr>
        <tr><td>进行中</td><td>{stats.get('in_progress', 0)}</td></tr>
        <tr><td>已完成</td><td>{stats.get('completed', 0)}</td></tr>
        <tr><td>已取消</td><td>{stats.get('cancelled', 0)}</td></tr>
    </table>
"""

            if "metrics" in stats_report:
                metrics = stats_report["metrics"]
                html += """
    <h2>性能指标</h2>
"""
                html += f"""
    <div class="metric">完成率: {metrics.get('completion_rate', 0)}%</div>
    <div class="metric">待办比例: {metrics.get('pending_ratio', 0)}%</div>
    <div class="metric">进行中比例: {metrics.get('in_progress_ratio', 0)}%</div>
"""

            html += f"""
    <h2>最近事件</h2>
    <p><strong>总事件数:</strong> {report_data['total_events']}</p>
    <table>
        <tr><th>时间</th><th>类型</th></tr>
"""

            for event in events[-10:]:
                event_type = event.get("type", "unknown")
                timestamp = event.get("timestamp", "")
                html += f"        <tr><td>{timestamp}</td><td>{event_type}</td></tr>\n"

            html += """
    </table>
</body>
</html>
"""
            content = html.encode('utf-8')
            filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"

        else:
            raise ValueError(f"不支持的报告格式: {format}")

        # 保存报告
        return self.data_provider.save_asset(
            self.plugin_id,
            filename,
            content
        )

    def clear_event_log(self) -> None:
        """清除事件日志"""
        self.event_log = []
        self._save_event_log()
