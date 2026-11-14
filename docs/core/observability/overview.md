# 可观测性与框架事件

## 1. 能力边界

`core/observability/` 提供进程内关联上下文、指标、健康快照和框架事件。所有能力均可在本地运行，不依赖外部监控、日志或追踪服务。

- 框架负责基础设施状态、调用关联和性能证据。
- 行业身份认证、业务审计、领域数据加密和业务验证仍由插件负责。
- `FrameworkEventJournal` 是有界内存诊断日志，不是持久化、不可抵赖的合规审计存储。
- 插件通过 `PluginServices.observability` 上报自身健康和指标；框架不规定插件业务审计格式。

## 2. 模块结构

| 文件 | 职责 |
|---|---|
| `context.py` | `CorrelationContext`、ContextVar 调用链和耗时 |
| `metrics.py` | 线程安全 counter、histogram、gauge 与有界序列 |
| `health_registry.py` | 本地组件健康状态和脱敏只读快照 |
| `events.py` | 四类框架事件及有界内存日志 |
| `plugin_facade.py` | 绑定插件身份的健康、指标和上下文门面 |
| `sanitize.py` | 凭据、患者字段和插件自定义敏感字段递归脱敏 |
| `instrumentation.py` | 共享数据库写入测量，原异常照常传播 |
| `names.py` | 框架指标名称单一来源 |

## 3. 关联上下文与日志

`CorrelationContext` 包含 `plugin_id`、`task_id`、`request_id`、`conversation_id`。`correlation_scope()` 使用 ContextVar 传播当前值并自动测量耗时；嵌套作用域继承父请求 ID，退出后恢复父上下文。跨线程或新事件循环时需要显式捕获并重新激活上下文，不能假定 ContextVar 自动跨线程传播。

`LoggerManager` 在完整日志格式化后统一脱敏，输出字段包括：

- `trace`：关联 ID；
- `plugin`、`task`、`request`、`conversation`：调用链身份；
- `duration_ms`：当前作用域耗时。

内置脱敏覆盖 `Authorization`、Bearer、`api_key`、`token`、密码、密钥和常见患者字段。插件可注册自己的敏感字段标记：

```python
from core.observability import register_sensitive_fields

register_sensitive_fields("hospital_case_number", "business_private_field")
```

轮转文件创建、轮转或写入失败不会向业务线程抛出异常。文件不可用时会降级到最多 1000 条的内存日志；其他写入失败仅累计诊断错误。既有非法日志级别仍按原契约抛出 `AttributeError`。

## 4. 指标

### 4.1 插件使用方式

```python
from core.interfaces.health import HealthStatus

observability = services.observability
observability.counter("converter.calls", {"operation": "convert"}).inc()
observability.histogram("converter.latency_ms").observe(12.5)
observability.gauge("converter.active").set(1)
observability.report_health(HealthStatus.HEALTHY, capability="converter")

with observability.context(task_id="convert-001", request_id="request-001"):
    pass
```

门面始终覆盖调用方伪造的 `plugin_id` 标签。指标操作返回布尔值；非法数值、类型冲突或超出基数时返回 `False`，不向插件业务路径抛出诊断异常。

### 4.2 框架指标

| 名称 | 类型 | 来源 |
|---|---|---|
| `task.queue_depth` | gauge | `TaskSupervisor` 提交与完成 |
| `task.schedule_delay_ms` | histogram | 定时任务调度延迟 |
| `task.restarts` | counter | 长期任务自动重启 |
| `db.write_latency_ms` | histogram | SQLite 写入 |
| `db.write_failures` | counter | SQLite 写入异常 |
| `event.dropped` | counter | 异步事件背压丢弃 |
| `event.coalesced` | counter | 异步事件合并 |
| `event.queue_depth` | gauge | 订阅者邮箱深度 |
| `mcp.sessions` | gauge | 远程 MCP 连接数及本地 Host 状态 |
| `ui.chart_ingest_ms` | histogram | 图表 `set_stream_data` 入图耗时 |

### 4.3 有界性与快照

- 每个指标名称默认最多 1024 个标签序列；超限返回 no-op 并增加 `dropped_series`。
- 每个序列最多 8 个标签，标签名和值最长 128 字符。
- 每个 histogram 保留最近 1024 个样本，同时累计全部 `count` 和 `sum`。
- `MetricsRegistry.snapshot()` 返回独立字典，包含 `series`、`dropped_series` 和 `errors`，不共享内部样本。
- 标签值同样经过敏感文本清理。

```python
from core.observability import get_metrics_registry

snapshot = get_metrics_registry().snapshot()
```

## 5. 健康快照

`HealthRegistry` 保存组件最新状态，以最严重状态聚合整体状态。插件记录使用 `plugin:{plugin_id}:{capability}` 作为组件键，卸载时清理。既有 `PluginServiceHealth` 上报会同步汇入统一快照，插件也可以直接使用自己的 `observability` 门面。

```python
from core.observability import get_health_registry

snapshot = get_health_registry().snapshot()
# {"status": "degraded", "components": {...}}
```

消息在写入和读取时均脱敏并限制为 300 字符。快照只包含状态、错误码、消息、时间和关联 ID，不包含原始异常对象或凭据。

## 6. 框架事件

支持闭集事件：

| 事件 | 产生时机 |
|---|---|
| `PLUGIN_LOADED` | 插件生命周期回调、注册和 API 自动注册成功 |
| `TASK_CANCELLED` | 取消状态已确认；仅发出 `CANCELLING` 请求不生成事件 |
| `DATA_RECOVERED` | 数据库恢复点隔离或恢复完成并验证 |
| `MCP_EXPOSED` | HTTP Server 已确认启动，记录鉴权/TLS 元数据而不记录 token |

事件默认保留最近 1024 条，详情递归脱敏。事件用于本地故障定位，不表示业务操作已审计，也不替代插件或外部系统的持久化审计。

```python
from core.observability import get_framework_event_journal

events = get_framework_event_journal().snapshot(limit=100)
```

## 7. 验证

```powershell
python -m pytest test/core/test_observability.py -q --tb=short -p no:cacheprovider
```

验收覆盖关联 ID 贯通、指标类型与基数上限、非法数值有限降级、患者和自定义字段脱敏、日志写失败、有界事件、健康快照、任务/数据库/事件/MCP/UI 指标入口。
