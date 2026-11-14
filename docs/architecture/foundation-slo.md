# 工业/医疗基础框架 SLO、负载模型与故障矩阵

> 本文是 Task 0 的固定测量契约。基线用于后续任务在相同数据规模下比较，不代表工业/医疗行业认证，也不代表真实 GUI、外部网络或长期稳定性已经验收。

## 1. 采集入口与退出语义

```powershell
.venv\Scripts\python.exe scripts\benchmark_foundation.py --output temp/foundation-baseline.json
.venv\Scripts\python.exe scripts\benchmark_foundation.py --output temp/foundation-current.json --baseline temp/foundation-baseline.json
.venv\Scripts\python.exe scripts\smoke_foundation_hardening.py
```

- `--output` 与 `--baseline` 路径都必须位于项目 `temp/` 内，baseline 在打开文件前先校验路径。工作数据库、任务状态、慢盘文件和子进程数据库使用自动清理的 `temp/foundation-baseline-*`；日志环境在任何 foundation/core import 前定向到独立 `temp/foundation-import-logs-*`，退出时关闭对应 handler 并删除该目录。
- 不读取或写入真实 `data/`、`config/`、`logs/`，不访问外部服务；MCP 仅使用 `127.0.0.1` 临时端口。DataProvider 场景通过上下文在所有异常路径关闭连接并清空单例，关闭异常本身也不阻止单例清理。
- 主命令退出 `0` **只表示采集流程完成**。系统是否合格只看 JSON 的 `qualification_status`、各项 `status`、`current_failures` 和 `not_run`。
- 参数错误、历史基线无法比较或报告无法写出时退出 `2`。快速自检任一项失败退出 `1`。

## 2. 三种状态与总判定

| 状态 | 含义 |
|------|------|
| `PASS` | 对应范围已实际执行，样本有效，并且满足该项 SLO；受控替身的通过只代表替身场景，不外推到真实外部条件。 |
| `FAIL` | 对应范围已执行，但延迟越界、预期恢复行为缺失、数据受损或采集器在该项遇到错误。当前失败会进入 `current_failures`。 |
| `NOT_RUN` | 未执行、平台无法强制该条件或样本不可读。没有样本时统计值为 `null`、`sample_count=0`，绝不以 `0` 或 `PASS` 代替。 |

总 `qualification_status` 按以下优先级计算：

1. 存在当前 `FAIL` 时为 `FAIL`；
2. 没有失败但存在 `NOT_RUN` 时为 `NOT_RUN`；
3. 只有全部项目实际通过时才为 `PASS`。

`collection_status=COMPLETED` 与上述系统判定相互独立。单项负载在全部指标（包括 MCP）追加后统一派生状态：空指标列表为 NOT_RUN，任一指标失败则负载失败；没有失败但有指标未执行则负载未执行；全部指标通过才通过。报告校验拒绝空指标列表的 PASS。故障必须同时满足行为断言与全部必需指标 SLO 才能通过。`current_failures` 同时检查项目状态与指标状态，即使历史报告把所属项目误标为 PASS，其中的 FAIL 指标也不会漏计。

## 3. 统计与测量方法

- 墙钟延迟使用 `time.perf_counter`，单位为毫秒；采集过程 CPU 使用 `time.process_time`，单位为秒。
- 每个指标保留原始 `samples`，并输出 `p50`、`p95`、`p99`、`max`、`sample_count`、测量方法、单位和 SLO。
- 百分位采用**最近秩法**：样本升序排列，取第 `ceil(p × N)` 项，秩从 1 开始。空样本不计算百分位。
- 生命周期和关闭项目前为单样本，`p50=p95=p99=max`；这提供当前观测值，不构成稳定分布，后续比较仍需重复运行。
- 进程内存使用 Windows `GetProcessMemoryInfo` 的 `WorkingSetSize`，报告为字节或 MiB；API 不可读时为 `NOT_RUN`。
- 环境记录操作系统、CPU 型号与逻辑核心数、进程内存、磁盘总量/用量/余量、Python、Qt、PySide6 和 `powercfg /getactivescheme` 可读取的电源模式。
- 每个负载的 `data_scale` 固定数据规模。跨报告比较前必须核对规模和环境，脚本不做环境归一化，也不隐藏环境差异。

## 4. 五类固定负载

| 负载 ID | 固定规模 | 执行范围 |
|---------|----------|----------|
| `idle` 空闲 | 新建 12 个独立 SQLite 数据库；内存采样 1 次 | 真实 `SQLiteBackend.ensure_database`，**非 GUI 启动** |
| `typical_desktop` 典型桌面 | 100 个种子键，每键 1024 字节；读、写、事件各 12 次；另执行 12 轮 × 100 键批量写入；MCP 调用 12 次 | 真实 `DataProvider`、SQLite、同步事件和本地回环 MCP；优化前批量基准回退为逐键写入，优化后为单事务写入 |
| `long_running_32` 32 个长期任务 | 32 个长期任务、12 个异步任务、4 个工作线程；关闭采样 1 次 | 真实 `BackgroundTaskManager`，长期任务等待模块级事件并协作退出 |
| `chart_1khz` 1kHz 图表 | 1000 帧 × 60 点 = 60000 输入点；每帧对最近 600 点做 100 桶 min/max 降采样 | **仅纯 Python 算法**，不创建 `QApplication`，不测量也不报告真实 fps |
| `slow_io` 慢网络/慢磁盘 | 各 12 次；网络等待 20ms；磁盘等待 10ms 后写 4096 字节并 `fsync` | 网络为本地确定性 sleeper；磁盘为 `temp/` 真实文件加受控等待 |

## 5. 负载 SLO

除内存单位为 MiB 外，以下阈值均为毫秒，判定统计项均为 `p95 <= 阈值`。

| 指标 | 阈值 | 测量内容 |
|------|------:|----------|
| `core_data_startup` | 2000ms | 新建后端并完成数据库初始化；不包含 Qt 主窗口 |
| `idle_process_rss` | 512 MiB | 空闲采集点进程工作集 |
| `sqlite_write` | 20ms | 单键私有数据写入 |
| `sqlite_read` | 5ms | 固定种子键读取 |
| `sqlite_batch_write` | 20ms | 100 键 × 1024 字节的整批写入；优化前后使用同一数据规模 |
| `batch_process_rss` | 512 MiB | 批量写入完成后的进程工作集 |
| `event_publish` | 5ms | 一个空订阅者的同步发布 |
| `mcp_startup` | 5000ms | 本地 HTTP MCP Server 启动确认 |
| `mcp_roundtrip` | 100ms | 真实 MCP SDK 经回环调用 `benchmark_echo` |
| `mcp_shutdown` | 5000ms | Server 停止并等待工作线程退出 |
| `async_task_submit` | 50ms | 异步任务注册并等待对应 Future 完成 |
| `long_task_register` | 100ms | 32 个长期任务中的单次注册 |
| `long_task_process_rss` | 512 MiB | 32 个长期任务注册后的工作集 |
| `task_manager_shutdown` | 15000ms | 协作停止 32 个长期任务并关闭管理器 |
| `chart_algorithm_update` | 1ms | 单帧追加与降采样；**不是渲染帧时间或 fps** |
| `slow_network_response` | 100ms | 本地 20ms sleeper 的墙钟时间 |
| `slow_disk_write` | 100ms | 受控等待、写盘、flush 与 fsync 总时间 |

## 6. 固定故障矩阵

严重度用于排列后续加固优先级：`P0` 涉及数据完整性或持久化成功语义，`P1` 涉及可用性、错误契约或组件隔离。`PASS` 仅适用于表中执行范围。

| 故障 ID | 严重度 | 执行范围与通过条件 |
|---------|--------|--------------------|
| `database_corruption` | P0 | 真实损坏 SQLite；检测 `p95<=200ms`，显式报错且原始损坏文件逐字节保留 |
| `database_locked` | P1 | 第二连接持有 `BEGIN IMMEDIATE`，`busy_timeout=50ms`；检测 `p95<=200ms`，公共 API 抛 `DataProviderError`，解锁后写回成功 |
| `database_readonly` | P1 | 真实文件只读位；检测 `p95<=500ms` 且公共 API 抛 `DataProviderError`。平台未强制只读、写入意外成功时为 `NOT_RUN` |
| `disk_full` | P0 | 对真实 `TaskStorage.save_data` 注入本地 `ENOSPC`；检测 `p95<=200ms`，调用者收到异常且 `_cache_dirty=True` |
| `process_kill` | P0 | 仅启动本采集器拥有的子进程；提交一行后在未提交事务中自愿 `os._exit(42)`。父进程检查退出码、`integrity_check=ok` 和已提交行数 1，整个过程 `p95<=5000ms`；不强杀任何外部进程 |
| `provider_timeout` | P1 | 隔离 `LLMProvider.check_model → chat` 真实入口下注入受控适配器；12 次超时均归类、原始 timeout 复原，随后再次探测成功且 `_health` 恢复。超时和恢复指标均 `p95<=100ms`；不代表真实外部 Provider 网络 |
| `mcp_disconnect` | P1 | 真实本地 MCP 会话中停止 Server；工具调用由 `asyncio.wait_for(1.5s)` 限制，2s 内显式异常且 Session/传输清理无异常才通过。停止前必须在 Server 所属 loop 取消并 await 全部 SSE `_shutdown_watcher`，停止后 pending=0；仅检查 `cleanup_error=None` 不足以证明清理完成。`cleanup_error` 写入观察结果与 details，存在清理异常即失败。传输进入、Session 初始化或 Server 停止等准备错误单独记为 `COLLECTION_ERROR/FAIL`，不得以空样本派生 NOT_RUN |
| `slow_subscriber` | P1 | 真实发布路径注入 50ms 慢订阅者；发布 `p95<=10ms`，快订阅者收到全部 5 次事件 |
| `plugin_exception` | P1 | 真实订阅回调抛受控异常；发布 `p95<=5ms`，异常不向外传播，正常订阅者收到全部 5 次事件 |

所有故障指标同样记录 p50/p95/p99、最大值、样本数和测量方法。故障记录另含 `expected`、`observed`、`execution_scope` 和结构化 `details`，当前失败不得因脚本继续运行而改写成通过。

## 7. 基线差异与回归规则

`--baseline` 按“来源 + 负载/故障 ID + 指标名”比较指标指定的统计项（当前均为 p95）：

- 相对增幅 `>10%` 标为回归；相对降幅 `<-10%` 标为改善；其余为无显著变化。
- 基线值为 0 时保留绝对差值，`delta_percent=null`，不猜测相对变化。
- 同名指标任一侧统计值为 `None` 时不做算术，输出 `numeric_comparable=false`、`delta=null`、`delta_percent=null`，回归和改善由项目状态迁移判定；old/new 两个方向均适用。
- 新增、缺失指标都进入 `metric_differences` 并注明无法计算；新增的 `FAIL` 项仍标为回归。
- `workload_status_changes` 与 `fault_status_changes` 列出全部状态迁移，不只列恶化项；`PASS` 退化为 `FAIL` 或 `NOT_RUN`、`FAIL` 变为 `PASS` 都计入回归/改善摘要。
- 比较摘要给出 `REGRESSION`/`NO_REGRESSION`、回归数、改善数和未变化数，计数包含指标差异与状态迁移。回归不阻止报告写出，也不改变“退出 0 只表示采集完成”的语义。

## 8. 明确未执行的验收

控制台分别输出顶层能力、负载/故障项目、指标三个层级的 NOT_RUN 数量，并逐项打印内部项目/指标明细，不能只报告顶层数量。本次报告至少包含以下顶层 `NOT_RUN`，不得由相近的算法或替身结果替代：

- `real_gui_chart`：真实 Qt 1kHz 渲染和 fps，需在有显示环境单独验收；
- `full_gui_startup_shutdown`：真实主窗口启动和关闭；
- `external_provider_network`：真实外部 Provider 网络及超时恢复；
- `physical_disk_full`：真实物理磁盘耗尽；
- `endurance_72h`：72 小时稳定性、内存趋势和长期任务运行。

此外，自愿退出子进程只验证 SQLite abrupt-exit 后的提交持久性，不宣称完整应用的任务恢复已经通过。

## 9. pytest 门禁位置与标准命令

故障矩阵 pytest 位于 `test/core/test_foundation_fault_matrix.py`。在 test 工作区以 dev 源码运行：

```powershell
PYTHONPATH=C:/Users/fuwa1/Documents/Project/InstructionX .venv/Scripts/python.exe -m pytest test/core/test_foundation_fault_matrix.py -q --tb=short -p no:cacheprovider
```

门禁要求全部断言通过，且完整 stdout/stderr 无 pending task、未清理 watcher 或其他非预期警告；最终状态以实际运行结果为准。
