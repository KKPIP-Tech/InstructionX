# 工业/医疗辅助场景部署、灰度与回滚指南

## 1. 适用范围

本文指导部署 InstructionX 的工程可靠性能力，不构成工业控制、医疗器械、临床诊断或功能安全认证。身份认证、业务审计、领域数据加密、业务规则验证由插件和整体应用提供；硬实时采集、设备控制和安全联锁必须由外部专用系统承担。

支持平台以项目声明为准：Windows 10/11、Python 3.14+。部署前必须锁定依赖、核对 `uv.lock`，并保留应用、插件、配置和数据库的版本对应关系。

## 2. 三种部署档位

| 档位 | 适用场景 | 必需能力 | 明确限制 |
|---|---|---|---|
| 通用桌面 | 受信任插件、普通配置与展示 | 默认同进程 `PluginManager`；SQLite DataProvider；统一生命周期；有界任务池 | DataProvider 固定 balanced；不隔离插件崩溃；不承诺硬实时或断电 RPO=0 |
| 行业增强 | 非关键工业监控、医疗辅助、商业桌面 | 通用桌面全部能力；LLM 用量/会话 durable；显式健康；协作取消；批量事务；异步事件背压；可观测性；MCP 失败关闭与统一清理 | 异步事件不是可靠消息队列；插件仍负责业务可靠性；DataProvider 没有 durable 档位；外部 Provider 和真实断电需独立验收 |
| 关键插件隔离 | 明确的崩溃敏感、无 UI Service/API | 行业增强全部适用能力；显式 `PluginHost`；调用截止期；有限重启与熔断；按需外部 watchdog | 不支持 Qt/对象引用透明代理；不是安全沙箱；进程内存状态会丢失；请求不自动重放； watchdog 不执行设备控制 |

档位是部署组合，不是三个框架版本。默认同进程路径未被替换，只有应用明确实例化 `PluginHost` 才进入第三档。

## 3. 持久化语义

### 3.1 DataProvider

`DataProvider` 默认且固定使用 SQLite WAL、`synchronous=NORMAL`，对应 **balanced**。当前没有 `durable=True` 配置，也不能通过文档声明获得该能力。

- 已提交事务在进程异常退出模型下验证 RPO=0；普通运行不能外推为物理断电、存储介质损坏或操作系统崩溃后的同等保证。
- 批量写入使用一个 `BEGIN IMMEDIATE` 事务，序列化或写入失败整批回滚。
- 启动备份、损坏隔离和恢复点用于人工/分阶段恢复；多文件替换不是一次物理原子操作。
- 启动备份不是跨进程在线备份。备份期间不得有外部写入者，运维必须管理备份保留和剩余空间。

```python
values = {"channel_1": 12.5, "channel_2": 13.0, "unit": "C"}
services.data_provider.set_plugin_data_batch(
    services_plugin_id, values, notify=False,
)
```

### 3.2 LLM 用量与会话

`UsageRecordStore(data_dir=None, durable=True)` 和 `ConversationStore(db_path, durable=True)` 默认使用显式事务及 `synchronous=FULL`，对应 **durable**。传 `durable=False` 使用 `synchronous=NORMAL`，对应 **balanced**，断电时存在最近已提交事务丢失的风险窗口。

- `ConversationStore.append_turn()` 的 `WriteReceipt.durable` 反映实际配置，不代表已经通过真实断电验证。
- `UsageRecordStore.flush()` 保持旧外观；需要明确确认时使用 `flush_detailed()`，检查 `success/pending/error`。
- 默认 LLM 门面使用 durable 存储。balanced 只能由明确的核心构造参数选择，不应为了基准成绩暗中切换。
- 真实虚拟机断电未执行，因此即使 FULL 也不能在本项目中声明“断电模型 RPO=0 已验收”。

## 4. 插件接入示例

### 4.1 健康与指标

```python
from core.interfaces.health import HealthStatus

observability = services.observability
observability.report_health(HealthStatus.HEALTHY, capability="converter")
observability.counter("converter.calls", {"operation": "convert"}).inc()
observability.histogram("converter.latency_ms").observe(12.5)
```

框架事件和指标是本地有界诊断信息，不是持久化、不可抵赖的业务审计。不得在标签中放患者姓名、自由文本或设备唯一高基数字段。

### 4.2 协作取消

```python
def convert(token, source):
    token.raise_if_cancelled()
    return transform(source)

task_id = services.task_manager.register_cancellable_task(
    services_plugin_id, "转换", convert, args=(source,),
)
result = services.task_manager.request_task_cancellation(task_id, timeout=2.0)
```

运行中的函数实际退出前状态为 `CANCELLING`，不是 `CANCELLED`。插件必须在副作用前和循环中检查 token；忽略取消并正常返回的函数最终为 `COMPLETED`。旧 `cancel_task()` 保持状态取消语义，不能代替真实停止确认。

### 4.3 异步事件

```python
from core.data.event_dispatcher import BackpressurePolicy

receipt = services.data_provider.publish_async(
    services_plugin_id,
    "display_status",
    {"text": "ready"},
    policy=BackpressurePolicy.COALESCE,
)
if not receipt.accepted:
    handle_event_backpressure(receipt.reason)
```

`publish_async()` 先持久化公开数据，再投递到每订阅者有界邮箱。`PublishReceipt` 只表示邮箱是否接收，不表示回调已执行，也不是额外的一次持久化确认。`REJECT/COALESCE/DROP_OLDEST` 分别用于拒绝、保留最新值和丢弃最旧值。关键业务必须由插件实现持久化队列、确认、幂等和恢复；不得使用内存事件触发安全联锁。

### 4.4 进程外宿主

```python
from pathlib import Path
from core.plugin_host import HostConfig, PluginHost

host = PluginHost()
host.start(Path("custom_plugin/critical-service"), HostConfig(
    startup_timeout=10.0,
    heartbeat_interval=1.0,
    heartbeat_timeout=3.0,
    max_restarts=2,
    max_pending_calls=16,
))
result = host.call("read_status", {"channel": "local"}, timeout=0.5)
if result.error is not None:
    handle_explicit_failure(result.error.code)
stop_report = host.stop(timeout=3.0)
```

仅限无 UI、参数和返回值可 JSON 序列化的 Service/API。子进程拥有独立单例和 DataProvider 连接，内存缓存与发布订阅不自动同步。崩溃请求结果未知，框架不重放；非幂等业务必须自行对账。详细协议和 watchdog 配置见 [进程隔离](plugin-isolation.md)。

## 5. 关闭与恢复报告

应用退出由 `ApplicationLifecycle` 统一执行：停止外部调用和新任务、取消插件任务、关闭 MCP、卸载插件、关闭任务管理器与 LLM、冲刷用量、关闭 DataProvider，最后释放 UI。

`ShutdownReport.steps` 记录每一步 `status/elapsed_ms/error`，`timed_out` 或任一步失败时 `success=False`。超时只停止等待，不保证不配合的 Python 函数已经终止；不得把 `success=True` 外推为外部设备进入安全状态。插件宿主停止另看 `StopReport.forced/success`，MCP 清理另看 `MCPShutdownReport.errors`。

## 6. 灰度步骤与回滚

以下是**待部署方执行的流程**，本项目没有宣称已完成真实行业灰度。每阶段必须记录版本、数据规模、签名结果和回滚点，未通过不得进入下一阶段。

### 阶段 0：准备

1. 停止应用写入，备份 `data/`、`config/`、插件目录和版本清单；数据库备份必须包含一致的 WAL/SHM 状态。
2. 在隔离环境运行完整测试、故障矩阵、MCP、插件契约、OSV 和性能门禁。
3. 先保持 watchdog 为 `none`，不启用进程隔离，不改变现有插件调用方式。

### 阶段 1：内部工具灰度

- 只选择非关键内部工具，逐项启用健康上报、协作取消、批量写入和异步展示事件。
- 核对队列、错误、延迟、恢复报告和旧插件兼容性；执行启动恢复与关闭演练。
- 回滚时停止新 API 调用并恢复上一插件版本；保留新数据库和迁移备份，不用旧代码强行读取更高 schema。

### 阶段 2：非关键行业辅助灰度

- 仅限监控、展示和人工辅助，不接入设备控制、自动给药、诊断或安全联锁。
- 验证 LLM durable 写回执、DataProvider balanced 风险是否被整体应用接受；完成七小时手动混合负载和行业数据规模复测。
- 任一 P0/P1、资源泄漏或兼容失败立即回本阶段修复。回滚使用阶段 0 恢复点和已知良好插件组合，不删除新库“重新开始”。

### 阶段 3：关键插件隔离灰度

- 只迁移满足无 UI/JSON/独立进程约束的 Service/API，先在测试环境完成崩溃、超时、消息洪水和主进程强杀演练。
- watchdog 先 `none` 观察，再分别审批 `exit` 和 `restart`；重启命令必须是明确应用入口，禁止设备命令。
- 回滚时先停止接受调用并执行 `PluginHost.stop()`，将 watchdog 恢复为 `none`，再切回经过兼容验证的同进程插件。不得在有在途请求时直接替换插件目录。

## 7. 发布门禁

| 检查 | 命令/证据 | 通过规则 |
|---|---|---|
| 完整测试 | `python -m pytest test/ -q --tb=short -p no:cacheprovider` | 全部通过，无回归 |
| 框架自检 | `.venv\Scripts\python.exe scripts\smoke_foundation_hardening.py` | 15/15 |
| 完整插件契约 | `.venv\Scripts\python.exe scripts\validate_plugin_contracts.py` | 包含 `legacy_pytest` 全部 PASS |
| MCP | `.venv\Scripts\python.exe scripts\_mcp_smoke.py` | 28/28，各 100 次重连无泄漏/清理警告 |
| 快速故障 | `.venv\Scripts\python.exe scripts\fault_inject_foundation.py --quick --allow-not-run` | 执行项 PASS；逐项审查 NOT_RUN |
| 完整恢复 | `.venv\Scripts\python.exe scripts\fault_inject_foundation.py` | 100 次恢复 RTO≤60 秒；环境 NOT_RUN 单独披露 |
| 当前基准 | `.venv\Scripts\python.exe scripts\benchmark_foundation.py --output temp/foundation-final.json` | 当前 P0/P1=0，适用 SLO 全部通过 |
| 长稳 | 用户手动运行 `scripts/soak_foundation.py` | 约 7 小时结果经开发者接受；禁止 pytest/CI 触发 |
| 依赖安全 | 与 CI 相同的 `uv export` + `pip-audit -s osv` | 无未处置 Critical/High；本次为无已知漏洞 |
| 文档交叉验证 | 对照本指南、验证报告和代码 | 无过期保证、无隐藏限制 |

发布说明必须逐项列出 `NOT_RUN`、历史比较中的相对回归和适用范围。任何需要真实断电、物理磁盘满、真实外部 Provider 或 72 小时证据的发布声明，在对应项目实际完成前都不得批准。
