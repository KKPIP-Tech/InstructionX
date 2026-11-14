# 工业与医疗场景基础框架可靠性优化项目 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不承接行业业务逻辑、不破坏既有插件契约的前提下，把 InstructionX 建设成可支撑工业监控、医疗辅助及高要求商业桌面应用的稳定、可靠、可验证的基础框架。

**Architecture:** 第一阶段采用“单进程受信任插件 + 分池调度 + 显式故障状态 + 可恢复持久化 + 统一生命周期”的加固路线，保持现有插件 API 兼容。第二阶段增加可选的进程外关键插件宿主与外部 watchdog；实时控制和安全联锁始终由外部实时服务或设备控制器承担，桌面框架负责配置、展示、人工交互和非实时编排。

**Tech Stack:** Python 3.14、PySide6 6.10+、SQLite WAL、ThreadPoolExecutor/asyncio、MCP 1.30+、pytest/pytest-qt、Rust 原生 Setup（仅涉及安装恢复时）。

## Global Constraints

- 工作分支为 `dev`；pytest 测试代码只提交到 `test` 分支，当前 CI 冒烟基线 `test/core/data/test_data_provider.py` 除外。
- 禁止擅自修改 `core/version.py` 的 `VERSION` 和 `setup/src/version.rs` 的 `SETUP_VERSION`。
- 面向插件的公开接口保持向后兼容；新增能力优先使用新接口、可选参数和兼容层。任何既有接口签名或行为语义变更，实施前必须单独说明影响并获得开发者同意。
- 身份认证、业务审计、领域数据加密、业务规则验证、医疗/工业合规逻辑由插件及整体应用提供；框架只提供安全的扩展点、框架自身审计事件和可靠基础设施。
- 同进程受信任插件仍是默认部署模型；不可信插件和安全关键插件使用第二阶段的可选进程隔离，不强制所有插件迁移。
- 不承诺硬实时、医疗诊断正确性或行业认证。只有验收矩阵全部通过后，才能声明达到本项目定义的工程可靠性基线。
- 新方法/函数不超过 40 行，嵌套不超过 3 层；注释、docstring、日志和提交说明使用中文；无裸 `except`、无静默吞异常、无魔法数。
- 每个功能独立测试、独立评审；`git commit` 前必须获得用户确认，提交前缀是否使用必须另行询问。
- 依赖变更必须同步 `pyproject.toml`、`requirements.txt` 和锁文件；优先使用现有依赖，不为可观测性、IPC 或测试引入不必要的新依赖。
- 临时文件只放 `temp/`；正式验证脚本放 `scripts/`；测试代码放 `test` 分支的 `test/`；文档与代码同步更新。

---

## 1. 项目范围与交付分层

### 1.1 第一阶段：Foundation Hardening（必须交付）

解决当前已确认的基础问题：

1. 既有数据库初始化失败时被删除。
2. 核心服务失败后注入 `None`/`MagicMock`，产生静默失效或假成功。
3. 长期任务、普通异步任务和定时任务共享 4 个 worker，发生调度饥饿。
4. 运行中任务标记 `CANCELLED` 后继续产生副作用。
5. 用量写盘失败后清除脏标记，`flush()` 无法发现未落盘数据。
6. Provider 模型接口失败后仍可能显示健康。
7. MCP 连接跨 Task 退出 cancel scope，退出时缺少统一清理。
8. 同步订阅者阻塞发布者，网络模型刷新阻塞启动。
9. 缺少可量化的性能、长稳、故障恢复和兼容性门禁。

### 1.2 第二阶段：Critical Plugin Isolation（行业增强交付）

- 为关键插件提供可选进程外宿主、心跳、重启预算、调用超时和崩溃隔离。
- 提供独立 watchdog，监测主进程无响应并执行安全退出/恢复策略。
- 设备安全联锁、硬实时采集和临床决策仍归外部专用系统，不迁入该宿主。

### 1.3 非目标

- 不实现用户 RBAC、医疗业务审计、患者数据加密、工业控制算法或诊断规则。
- 不把所有插件改为进程外运行，不强制插件重写。
- 不通过单纯增加线程数、隐藏错误或跳过测试来制造性能指标。
- 不在本项目中修改框架版本号或发布 Tag。

## 2. 可量化验收基线

所有绝对性能指标在项目锁定的 Windows 11 基准机上测量；基准脚本记录 CPU、内存、磁盘、Python、Qt、电源模式和数据规模。平均值不能替代 p95/p99。

| 类别 | 验收指标 |
|---|---|
| 数据正确性 | 既有数据库在损坏、锁定、权限不足和迁移失败时均不得被删除；100% 故障用例保留原文件或生成可恢复隔离副本 |
| 故障显式化 | 核心服务不可用时不得出现 `MagicMock` 或无日志 `None` 假成功；所有失败均带模块、操作、错误类别和关联 ID |
| 持久化 | 进程崩溃后，已确认的 durable 写入 RPO=0；测试虚拟机断电模型下 durable 模式已确认事务 RPO=0；普通模式不得宣称同等保证 |
| 恢复 | 应用异常退出后可启动并完成自动恢复，RTO≤60 秒；不可恢复数据必须进入明确的人工恢复状态，不得静默重建成空库 |
| 调度 | 32 个阻塞长期任务并发时，高优先级短任务派发 p99≤100ms；普通短任务在声明负载下 p99≤1 秒 |
| 定时任务 | 100 个快速定时任务与长期任务并存时，调度延迟 p99≤250ms；重叠策略和 missed-run 策略可观测 |
| 取消 | 新取消 API 在函数实际停止前不得报告 `CANCELLED`；协作式任务停止确认 p99≤2 秒；遗留 API 保持兼容并明确标为状态取消 |
| UI 响应 | 网络全部离线时主窗口可交互时间相对在线冷启动增幅≤10%；常规本地操作 p95≤100ms |
| 流式图表 | 基准数据规模 1kHz 输入、20,000 点窗口时目标 60fps，帧耗时 p95≤16.7ms、p99≤33ms；队列有界，丢点只发生在显式策略中且可计数 |
| 事件分发 | 新异步发布 API 在 500ms 慢订阅者下，发布者返回 p99≤10ms；队列满时按声明策略拒绝、合并或丢弃并计数 |
| MCP | 连续 100 次 stdio/HTTP 连接、调用、断开无跨 Task 警告、无孤儿进程、无遗留工具；非回环无认证配置必须启动失败 |
| 长稳 | 72 小时混合负载无崩溃、无未处理异常、无死锁；预热后内存增长≤10%，句柄增长≤5%，队列无无界增长 |
| 兼容性 | 既有插件契约测试和官方示例插件加载/卸载测试 100% 通过；未获批准的公开签名变更为 0 |
| 安全回归 | 非回环 MCP 无认证阻断率 100%；核心密钥不写入明文配置、日志、崩溃转储和测试产物 |
| 自动化 | 核心故障矩阵通过率 100%；pytest、真实 GUI 测试、MCP 冒烟、插件管理冒烟全部通过；OSV 无未处置 Critical/High 漏洞 |

## 3. 目标文件结构

### 3.1 持久化与恢复

- 修改 `core/data/sqlite_backend.py`：只负责连接、事务和 CRUD，不再自行决定删除既有库。
- 新建 `core/data/recovery.py`：数据库存在性判定、损坏隔离、备份、恢复和错误分类。
- 修改 `core/data/data_provider.py`：增加统一 `close()`、批量写入和持久化模式配置；保留现有调用方式。
- 新建 `core/llm/usage_sqlite_store.py`：增量用量持久化；`UsageRecordStore` 保持外观兼容。
- 新建 `core/llm/conversation_sqlite_store.py`：增量会话持久化；JSON 仅作迁移来源和应急导出。
- 扩展 `core/data/schema_migrations.py`：所有 schema 变化必须有向前迁移与备份，不直接改旧库结构。

### 3.2 执行与生命周期

- 保留 `core/task/background_task.py` 作为兼容门面，避免继续增加职责。
- 新建 `core/task/executor_pools.py`：长期、普通、高优先级执行池及有界队列。
- 新建 `core/task/cancellation.py`：协作式取消令牌、取消状态和实际停止确认。
- 新建 `core/task/supervisor.py`：心跳、重启预算、熔断和调度指标。
- 新建 `core/application_lifecycle.py`：插件、MCP、LLM、任务、DataProvider 的统一关闭顺序和全局截止期。
- 修改 `core/plugin/manager.py`：显式服务健康、按插件清理资源，不再使用生产 `MagicMock`。
- 修改 `main.py`：只调用统一生命周期协调器，不继续堆叠零散关闭逻辑。

### 3.3 事件、LLM 与 MCP

- 新建 `core/data/event_dispatcher.py`：每订阅者有界邮箱、异步分发、合并/拒绝/丢弃策略和指标。
- 修改 `core/data/data_provider.py`：新增异步发布接口；既有同步 `publish()` 默认不变。
- 修改 `core/llm/llm_provider.py`：惰性网络初始化、真实健康状态、不可变单次请求配置。
- 修改 `core/llm/providers/base.py`：异常向上传递、请求级超时、流式取消、连接并发边界。
- 修改 `core/mcp/client.py`：单个连接由单一 coroutine owner 管理完整生命周期。
- 修改 `core/mcp/server.py`、`core/mcp/manager.py`：非回环失败关闭、Host 校验、TLS 配置和统一关停。
- 新建 `core/observability/`：关联 ID、结构化指标、健康聚合和脱敏；不引入外部服务作为运行前提。

### 3.4 第二阶段隔离

- 新建 `core/plugin_host/protocol.py`：版本化长度帧 JSON-RPC 消息契约。
- 新建 `core/plugin_host/supervisor.py`：子进程心跳、重启预算、调用超时和资源清理。
- 新建 `core/plugin_host/proxy.py`：与现有 `PluginServices` 对齐的进程外代理。
- 新建 `scripts/plugin_host_entry.py`：进程外插件入口。
- 新建 `core/external_watchdog.py` 与 `scripts/external_watchdog.py`：独立 watchdog，仅执行配置明确的恢复动作。

## 4. 分阶段实施任务

### Task 0：建立基线、负载模型和故障矩阵

**Files:**
- Create: `scripts/benchmark_foundation.py`
- Create: `scripts/smoke_foundation_hardening.py`
- Create: `docs/architecture/foundation-slo.md`
- Test（仅 `test` 分支）: `test/core/test_foundation_fault_matrix.py`

**验收产出:** 当前启动、调度、SQLite、事件、MCP、内存和关闭基线；每项后续优化都能与同一数据规模比较。

- [ ] 固定五类负载：空闲、典型桌面、32 个长期任务、1kHz 图表、慢网络/慢磁盘。
- [ ] 固定故障：数据库损坏/锁定/只读、磁盘满、进程强杀、Provider 超时、MCP 断连、慢订阅者、插件异常。
- [ ] 先运行未加固代码并记录失败项，禁止把失败基线改写成通过。
- [ ] 为每项指标定义 p50/p95/p99、最大值、样本数和测量方法。

Run: `.venv\Scripts\python.exe scripts\benchmark_foundation.py --output temp/foundation-baseline.json`
Expected: 生成基线报告，并明确列出当前 P0/P1 失败，不以脚本退出 0 代表系统合格。

### Task 1：修复既有数据库删除与恢复语义（最高优先级）

**Files:**
- Modify: `core/data/sqlite_backend.py:336-435`
- Create: `core/data/recovery.py`
- Modify: `core/data/data_provider.py`
- Test（仅 `test` 分支）: `test/core/data/test_database_recovery.py`

**Interfaces:**
- Produces: `DatabaseRecovery.classify_existing_database(path) -> DatabaseState`
- Produces: `DatabaseRecovery.quarantine(path, reason) -> RecoveryReport`
- Produces: `DataProvider.close() -> None`

- [ ] 写失败测试：预建非空数据库并写入损坏字节，初始化失败后断言主库和伴生文件仍存在。
- [ ] 写失败测试：模拟 `_has_core_tables()` 抛出锁定、权限和 I/O 错误，不得进入“新建并失败删除”路径。
- [ ] 将“本次新建”与“启动前已存在”作为两个不可混淆的状态；只有本次新建且从未包含用户数据的临时库才允许清理。
- [ ] 对损坏既有库采用同目录时间戳隔离副本；隔离失败时停止启动并给出人工恢复指引。
- [ ] 加入启动前备份、恢复点校验、`PRAGMA integrity_check` 和统一 `close()`。

Run: `python -m pytest test/core/data/test_database_recovery.py -q --tb=short -p no:cacheprovider`
Expected: 所有既有文件保留测试通过；当前未修复代码至少损坏库用例 FAIL。

**门禁:** 任何 P0 数据删除用例未通过，后续任务不得作为“可靠性完成”交付。

### Task 2：消除静默降级并建立统一健康模型

**Files:**
- Create: `core/interfaces/health.py`
- Create: `core/plugin/service_health.py`
- Modify: `core/plugin/manager.py:137-193,1014-1033`
- Modify: `ui/main_window.py`（只展示状态，不写业务逻辑）
- Test（仅 `test` 分支）: `test/core/plugin/test_service_health.py`

**Interfaces:**
- Produces: `HealthStatus = {UNKNOWN, HEALTHY, DEGRADED, UNAVAILABLE}`
- Produces: `HealthSnapshot(status, error_code, message, timestamp, correlation_id)`
- Produces: `PluginManager.get_service_health(plugin_id) -> HealthSnapshot`

- [ ] 写失败测试：DataProvider 初始化抛错时，插件状态必须为 `UNAVAILABLE`，不得实例化 `MagicMock`。
- [ ] 移除生产代码中的 `MagicMock` 回退；测试替身只允许存在于测试目录。
- [ ] 保留 `PluginServices` 字段兼容，但服务不可用时访问必须抛出带明确错误码的异常或返回既有 Optional 并触发可见失败状态。
- [ ] 将错误分为配置、资源、网络、权限、持久化、插件代码和未知内部错误，禁止统一转成“成功但为空”。
- [ ] 启动失败提示列出受影响插件、不可用能力和恢复建议，不暴露密钥或敏感数据。

Run: `python -m pytest test/core/plugin/test_service_health.py -q --tb=short -p no:cacheprovider`
Expected: 所有核心服务失败均显式可见，源码生产路径不再导入 `MagicMock`。

### Task 3：分离执行池、引入背压和真实取消 API

**Files:**
- Create: `core/task/executor_pools.py`
- Create: `core/task/cancellation.py`
- Create: `core/task/supervisor.py`
- Modify: `core/task/background_task.py`
- Modify: `core/interfaces/i_task_manager.py`（只新增契约，不改既有签名）
- Test（仅 `test` 分支）: `test/core/task/test_executor_isolation.py`, `test/core/task/test_cancellation.py`

**Interfaces:**
- Produces: `register_priority_task(plugin_id, name, func, priority=TaskPriority.HIGH, args=(), kwargs=None) -> Optional[str]`
- Produces: `request_task_cancellation(task_id, timeout=None) -> CancellationResult`
- Produces: `CancellationToken.raise_if_cancelled()`
- Produces: `ScheduledOverlapPolicy = {SKIP, QUEUE_ONE, COALESCE}`
- Consumes: 既有 `register_async_task()`、`register_long_running_task()` 和 `register_scheduled_task()` 保持可调用。

- [ ] 写失败测试：32 个长期任务阻塞时，高优先级任务仍在 100ms 预算内开始执行。
- [ ] 将长期任务从短任务池中物理分离；短任务池设置有界队列、插件配额和拒绝原因。
- [ ] 新增协作式取消 API；函数未实际退出前状态只能是 `CANCELLING`，只有确认停止后才进入 `CANCELLED`。
- [ ] 遗留 `cancel_task()` 暂保留状态取消语义并标记废弃；是否改变其语义另行取得开发者同意。
- [ ] 定时任务增加重叠策略，禁止慢任务无限堆积；调度使用 monotonic 时钟并记录延迟。
- [ ] 关闭等待改为全局截止期，不能随长期任务数量线性增加。

Run: `python -m pytest test/core/task/test_executor_isolation.py test/core/task/test_cancellation.py -q --tb=short -p no:cacheprovider`
Expected: 长期任务不阻塞短任务；协作取消在副作用停止前不报告完成；队列满时有明确背压结果。

### Task 4：统一插件与应用生命周期

**Files:**
- Create: `core/application_lifecycle.py`
- Modify: `core/plugin/manager.py`
- Modify: `main.py:98-113`
- Modify: `core/task/background_task.py`
- Test（仅 `test` 分支）: `test/core/test_application_lifecycle.py`

**Interfaces:**
- Produces: `ApplicationLifecycle.shutdown(timeout=15.0) -> ShutdownReport`
- Produces: `PluginManager.release_plugin_resources(plugin_id) -> ResourceReleaseReport`

- [ ] 固定关闭顺序：停止接收外部调用→停止新任务→取消插件任务→关闭 MCP→插件卸载→关闭 LLM→冲刷存储→关闭 DataProvider→释放 UI。
- [ ] 每一步独立记录耗时、成功、超时和异常；单步失败不得跳过后续清理。
- [ ] 插件卸载时取消其拥有的定时器、任务、订阅和 MCP 工具；遗留资源必须有日志和回收结果。
- [ ] 写测试覆盖插件不响应、MCP 不响应、磁盘写失败和重复调用 `shutdown()`。
- [ ] `main.py` 仅保留生命周期协调器调用，禁止继续散落新增关闭步骤。

Run: `python -m pytest test/core/test_application_lifecycle.py -q --tb=short -p no:cacheprovider`
Expected: 全局关闭请求≤15 秒返回，关闭报告无遗漏步骤，重复关闭幂等。

### Task 5：修复用量和会话持久化，移除全量重写瓶颈

**Files:**
- Create: `core/llm/usage_sqlite_store.py`
- Create: `core/llm/conversation_sqlite_store.py`
- Modify: `core/llm/usage_record_store.py`
- Modify: `core/llm/conversation_manager.py`
- Modify: `core/data/schema_migrations.py`
- Test（仅 `test` 分支）: `test/core/llm/test_usage_store_recovery.py`, `test/core/llm/test_conversation_store_recovery.py`

**Interfaces:**
- Consumes: 既有 `UsageRecordStore.record/get_records/aggregate/flush` 外观不变。
- Produces: `flush_detailed(timeout=2.0) -> FlushReport`；旧 `flush(timeout=2.0) -> None` 外观不变，并在超时路径记录明确的未落盘警告。
- Produces: `ConversationStore.append_turn(conversation_id, turn) -> WriteReceipt`

- [ ] 先修复 JSON 写线程：异常时保留 `_cache_dirty=True`，`flush()` 超时必须报告未落盘，添加故障测试。
- [ ] 用量改为追加式 SQLite 写入，保留查询和聚合接口；启动时从 JSON 原子迁移并保留备份。
- [ ] 会话按轮次增量提交，不再每次全量序列化；同会话并发发送必须串行化或明确拒绝并发。
- [ ] durable 模式使用显式事务和满足断电语义的同步级别；balanced 模式在文档中明确风险窗口。
- [ ] 损坏文件不得自动按空数据覆盖；进入恢复状态并保留原文件。

Run: `python -m pytest test/core/llm/test_usage_store_recovery.py test/core/llm/test_conversation_store_recovery.py -q --tb=short -p no:cacheprovider`
Expected: 写盘失败可重试且 flush 不假成功；10,000 条记录场景不再全量重写 JSON；并发同会话历史顺序正确。

### Task 6：提供异步事件分发和有界背压

**Files:**
- Create: `core/data/event_dispatcher.py`
- Modify: `core/data/data_provider.py`
- Test（仅 `test` 分支）: `test/core/data/test_async_event_dispatcher.py`

**Interfaces:**
- Produces: `publish_async(publisher_id, key, value, policy=BackpressurePolicy.REJECT) -> PublishReceipt`
- Produces: `EventDeliveryStats(queued, delivered, coalesced, dropped, failed, lag_ms)`
- Consumes: 既有同步 `publish()` 和 `subscribe()` 默认行为不变。

- [ ] 每个订阅者使用独立有界邮箱和分发 worker，慢订阅者不得阻塞其他订阅者。
- [ ] 支持 `REJECT`、`COALESCE`、`DROP_OLDEST` 三种显式策略；禁止隐式丢事件。
- [ ] 为事件增加单调序号、发布时间和目标插件；插件卸载后取消邮箱并停止回调。
- [ ] 写 500ms 慢订阅者测试，异步发布返回 p99≤10ms；队列满结果与策略一致。
- [ ] 文档明确：可视化可合并，关键业务必须使用持久化/确认机制，不得把内存事件总线当作可靠消息队列。

Run: `python -m pytest test/core/data/test_async_event_dispatcher.py -q --tb=short -p no:cacheprovider`
Expected: 慢订阅者隔离、背压、顺序、卸载清理和指标测试全部通过。

### Task 7：修复 LLM 健康、启动阻塞和调用并发

**Files:**
- Modify: `core/llm/llm_provider.py`
- Modify: `core/llm/providers/base.py`
- Create: `core/llm/provider_supervisor.py`
- Test（仅 `test` 分支）: `test/core/llm/test_provider_health.py`, `test/core/llm/test_provider_concurrency.py`

**Interfaces:**
- Produces: `ProviderSupervisor.refresh_models_async(provider_id) -> Future`
- Produces: `check_provider_detailed(provider_id) -> ProviderCheckResult`；旧 `check_provider(name) -> Tuple[bool, Optional[str], int]` 保持签名，失败时返回 `(False, 错误信息, 0)`。
- Produces: 请求级 `request_timeout` 和 `request_id`，不修改共享 Provider 的 `timeout` 属性。

- [ ] 模型请求失败必须向上传递失败；空列表只在接口真实成功且无模型时返回。
- [ ] 启动只加载磁盘缓存，远程刷新进入后台；UI 可先交互并显示“刷新中/未知/失败”。
- [ ] `check_model()` 不再临时修改共享 `provider.timeout`；并发探测不得互相恢复错误超时。
- [ ] 增加熔断和退避，故障恢复后自动半开探测；失败不得覆盖为健康。
- [ ] 重试默认仅用于安全操作；非幂等请求使用请求 ID，自动故障转移必须显式开启并提示重复计费风险。
- [ ] 流式生成器在取消和异常路径关闭响应，记录首 token、总时长和中断原因。

Run: `python -m pytest test/core/llm/test_provider_health.py test/core/llm/test_provider_concurrency.py -q --tb=short -p no:cacheprovider`
Expected: 网络失败不再返回健康；全部 Provider 离线不阻塞 UI；并发超时配置和流式清理正确。

### Task 8：重构 MCP 生命周期并收紧暴露边界

**Files:**
- Modify: `core/mcp/client.py`
- Modify: `core/mcp/server.py`
- Modify: `core/mcp/manager.py`
- Modify: `core/mcp/config.py`
- Modify: `scripts/_mcp_smoke.py`
- Test（仅 `test` 分支）: `test/core/mcp/test_connection_lifecycle.py`, `test/core/mcp/test_server_security.py`

**Interfaces:**
- Produces: 单连接 `ConnectionActor`，其唯一 coroutine owner 负责 enter、call、disconnect 和 close。
- Produces: `MCPManager.shutdown() -> ShutdownReport`，由统一应用生命周期调用。
- Produces: `ServerSecurityPolicy.validate(config) -> None`；非法配置抛出明确异常。

- [ ] 将 `AsyncExitStack` 的进入和退出固定在同一个 coroutine Task；命令通过队列发送给连接 owner。
- [ ] 调用超时必须取消远端等待并清理会话，不得只吞掉 `future.result()` 异常。
- [ ] 非回环 HTTP 且无 token 直接拒绝启动；启用 `allowed_hosts`，增加按工具白名单和速率限制。
- [ ] 对外 HTTP 支持 TLS 证书配置；token 使用与 GitHub PAT 同级的系统安全存储，不采用 Base64 作为安全边界。
- [ ] 冒烟脚本将任何 cancel scope 警告、遗留子进程和未注销工具视为失败。

Run: `PYTHONIOENCODING=utf-8 .venv\Scripts\python.exe scripts\_mcp_smoke.py`
Expected: 23 项既有检查及新增清理/安全断言全部通过，输出无跨 Task cancel scope 警告。

### Task 9：建立可观测性与框架自身审计事件

**Files:**
- Create: `core/observability/context.py`
- Create: `core/observability/metrics.py`
- Create: `core/observability/health_registry.py`
- Modify: `utils/logging_tools.py`
- Create: `docs/core/observability/overview.md`
- Test（仅 `test` 分支）: `test/core/test_observability.py`

**Interfaces:**
- Produces: `CorrelationContext(plugin_id, task_id, request_id, conversation_id)`
- Produces: `MetricsRegistry.counter(name, labels)`、`histogram(name, labels)`、`gauge(name, labels)`
- Produces: `HealthRegistry.snapshot() -> dict`
- Produces: 框架事件 `PLUGIN_LOADED`、`TASK_CANCELLED`、`DATA_RECOVERED`、`MCP_EXPOSED`，不包含领域业务审计语义。

- [ ] 日志自动携带关联 ID、插件、任务和耗时；脱敏规则覆盖 Authorization、API Key、token 和患者/业务自定义敏感字段标记。
- [ ] 指标覆盖队列深度、调度延迟、任务重启、DB 写延迟/失败、事件丢弃、MCP 会话和 UI 入图耗时。
- [ ] 提供本地只读健康快照，不要求外部监控系统才能运行。
- [ ] 插件可通过稳定接口上报自身健康和指标，但业务审计格式仍由插件定义。
- [ ] 日志轮转、磁盘满和写日志失败不能拖垮主流程；诊断失败自身必须有限降级。

Run: `python -m pytest test/core/test_observability.py -q --tb=short -p no:cacheprovider`
Expected: 关联 ID 贯通、标签 cardinality 有上限、敏感字段不出现在日志和快照中。

### Task 10：按基准实施性能优化，而非盲目调参

**Files:**
- Modify: `core/data/data_provider.py`
- Modify: `core/data/sqlite_backend.py`
- Modify: `core/llm/conversation_manager.py`
- Modify: `ui/usage_panel/trend_chart.py`（仅在基准证明必要时）
- Modify: `scripts/benchmark_foundation.py`
- Test（仅 `test` 分支）: `test/core/data/test_batch_write.py`, `test/core/test_performance_contract.py`

- [ ] 新增批量事务写入，避免逐键多次查询；保留单键 API。
- [ ] 消除正常点查路径对全量 `_cache` 的依赖；全量字典只用于兼容 `load_data()`。
- [ ] 大数据查询使用分页和数据库聚合，避免先复制全部记录再 Python 过滤。
- [ ] 网络模型列表并行刷新并设置总截止期，单 Provider 故障不拖住其他 Provider。
- [ ] UIKit 继续使用环形缓冲、帧合并、采样金字塔和 GL/软件回退；只在 profile 证明瓶颈后修改。
- [ ] 每项优化必须给出同机前后 p50/p95/p99、内存和正确性结果；无收益或回归的优化不合并。

Run: `.venv\Scripts\python.exe scripts\benchmark_foundation.py --baseline temp/foundation-baseline.json --output temp/foundation-optimized.json`
Expected: 达到第 2 节指标；任何性能提升不得伴随正确性测试失败或持久化级别暗中降低。

### Task 11：完成故障注入、长稳和兼容性验证

**Files:**
- Create: `scripts/soak_foundation.py`
- Create: `scripts/fault_inject_foundation.py`
- Create: `scripts/validate_plugin_contracts.py`
- Test（仅 `test` 分支）: `test/core/test_plugin_contracts.py`, `test/ui_tests/test_startup_offline.py`
- Modify: `.github/workflows/test.yml`（只增加可自动化的快速门禁，不把 72 小时长稳塞进每次 PR）

**验证矩阵:**
- 存储：损坏、锁定、只读、磁盘满、迁移中断、进程强杀、虚拟机断电。
- 调度：长期任务占满、定时任务重叠、取消竞态、关闭竞态、插件异常。
- 网络：DNS 失败、连接超时、读超时、429、5xx、流中断、MCP 反复断连。
- UI：全部 Provider 离线启动、插件加载失败、图表 1kHz、反复开关对话框。
- 兼容：现有官方示例插件、旧 DataProvider 数据、旧任务 JSON、旧会话/用量 JSON、旧 MCP 配置。

- [ ] 每次 PR 运行单元、集成、真实 GUI 和故障矩阵快速子集。
- [ ] 发布候选运行 72 小时混合负载，记录内存、句柄、队列、p95/p99 和错误日志。
- [ ] 进行 100 次异常启动恢复和 100 次 MCP 重连，所有资源计数回到基线。
- [ ] 通过插件契约测试证明无未经批准的公开接口破坏。
- [ ] 将清理警告纳入失败条件，避免“功能断言通过但资源泄漏”。

Run: `python -m pytest test/ -q --tb=short -p no:cacheprovider`
Expected: 全部通过。

Run: `.venv\Scripts\python.exe scripts\soak_foundation.py --hours 72 --output temp/foundation-soak.json`
Expected: 达到第 2 节长稳指标；未实际执行 72 小时前不得标记长稳验收完成。

### Task 12（第二阶段）：提供可选关键插件进程隔离与 watchdog

**Files:**
- Create: `core/plugin_host/protocol.py`
- Create: `core/plugin_host/supervisor.py`
- Create: `core/plugin_host/proxy.py`
- Create: `core/external_watchdog.py`
- Create: `scripts/plugin_host_entry.py`
- Create: `scripts/external_watchdog.py`
- Test（仅 `test` 分支）: `test/core/plugin_host/test_process_isolation.py`

**Interfaces:**
- Produces: `PluginHost.start(plugin_path, config) -> PluginHandle`
- Produces: `PluginHost.call(method, args, timeout) -> RpcResult`
- Produces: `PluginHost.stop(timeout) -> StopReport`
- Produces: `Watchdog.check_once() -> WatchdogReport`

- [ ] 使用带版本和长度帧的 JSON-RPC；校验消息大小、类型、请求 ID 和错误码，拒绝无效消息。
- [ ] 进程崩溃只影响对应代理；调用方收到明确 `PLUGIN_UNAVAILABLE`，不得拖死 UI。
- [ ] 心跳、调用超时、最大重启次数和熔断状态可观测；禁止无限重启。
- [ ] 主进程退出时回收子进程；watchdog 只执行用户配置的退出/重启动作，不执行设备控制。
- [ ] 写故障测试：插件死循环、段错误等效进程退出、消息洪水、错误协议、主进程强杀。
- [ ] 默认仍加载受信任同进程插件；只有明确配置的关键插件进入进程外宿主。

Run: `python -m pytest test/core/plugin_host/test_process_isolation.py -q --tb=short -p no:cacheprovider`
Expected: 插件进程故障不使主进程退出，调用有界返回，子进程和句柄全部可回收。

### Task 13：文档、灰度与发布门禁

**Files:**
- Modify: `docs/architecture/overview.md`
- Modify: `docs/architecture/module-dependencies.md`
- Modify: `docs/core/background-task/overview.md`
- Modify: `docs/core/data-provider/overview.md`
- Modify: `docs/core/mcp/overview.md`
- Modify: `AGENTS.md`（仅当目录结构或约定实际变化时）
- Create: `docs/architecture/foundation-deployment-guide.md`
- Create: `docs/architecture/foundation-verification-report.md`

- [ ] 明确三种部署档位：通用桌面、行业增强、关键插件隔离；列出每档能力与限制。
- [ ] 明确 balanced/durable 持久化语义、异步事件非持久化边界、取消契约和关闭报告。
- [ ] 给插件开发者提供健康上报、协作取消、批量持久化、异步事件、进程外宿主示例。
- [ ] 先灰度内部工具，再灰度非关键工业/医疗辅助场景；每个阶段保留可回滚的兼容开关和迁移备份。
- [ ] 发布前核对所有 SLO 实测证据、未解决缺陷、依赖安全和插件契约报告。
- [ ] 若某项未通过，发布说明必须列出限制，不得以“基本可用”替代未通过的验收项。

## 5. 里程碑与依赖关系

| 里程碑 | 内容 | 建议周期 | 退出条件 |
|---|---|---:|---|
| M0 基线冻结 | Task 0 | 1 周 | 负载模型、故障矩阵、基线报告完成 |
| M1 数据与故障正确性 | Task 1–2 | 2 周 | 无整库删除、无生产 MagicMock、故障显式化 |
| M2 执行与生命周期 | Task 3–4 | 3 周 | 无调度饥饿、真实取消 API、统一关闭 |
| M3 数据与通信能力 | Task 5–8 | 4 周 | 增量存储、异步事件、真实 LLM 健康、MCP 清理与安全 |
| M4 可观测与性能 | Task 9–10 | 2 周 | 指标贯通，性能达到基准门槛 |
| M5 发布候选 | Task 11、13 第一阶段部分 | 2–3 周 | 72 小时长稳、故障恢复、兼容性和文档全部通过 |
| M6 行业隔离增强 | Task 12、13 完整部分 | 4–6 周 | 关键插件可进程隔离，watchdog 故障测试通过 |

第一阶段建议投入 2 名框架工程师和 1 名测试/验证工程师，约 14–16 周；第二阶段约 4–6 周。周期以任务依赖为准，M1 未通过不得通过压缩故障测试来追赶进度。

## 6. 每个任务的统一执行与提交流程

1. 在 `test` 分支先写正常、边界、异常和并发测试，并在未修复代码上确认测试确实失败。
2. 在 `dev` 分支实施最小代码改动；需要拆分时先建立小模块，不继续扩大巨型文件。
3. 运行本任务测试、既有 `python -m pytest test/ -q --tb=short -p no:cacheprovider` 和相关 `scripts/smoke_*.py`。
4. 对照公开接口清单运行插件契约检查，更新文档和过期注释。
5. 独立代码评审重点检查：错误是否被吞掉、状态是否真实、资源是否有界、兼容是否保持、测试是否覆盖原始故障。
6. 测试通过后按功能颗粒度提交；提交前获得用户确认，并确认提交信息前缀。
7. 测试代码只进入 `test` 分支，框架代码只进入 `dev`；发布分支不直接开发。

## 7. 风险与控制

| 风险 | 控制措施 |
|---|---|
| 为追求可靠性破坏旧插件 | 新 API 优先、旧接口适配层、插件契约测试、灰度开关 |
| 为追求性能降低持久化安全 | balanced/durable 显式分档，禁止通过测试时偷偷降低同步级别 |
| 协作取消被插件忽略 | 真实状态保持 `CANCELLING`，关键插件进入进程宿主，由 supervisor 实施进程级停止 |
| 内存事件被误当可靠消息 | API 命名、回执和文档明确边界；关键业务由插件实现持久化确认 |
| 指标基数膨胀导致新性能问题 | 标签白名单和 cardinality 上限，不为每个用户输入创建标签 |
| 72 小时测试流于形式 | 固定负载脚本、原始指标留档、内存/句柄趋势和警告门禁 |
| 医疗/工业要求被过度承诺 | 只声明框架工程基线；领域验证、认证和安全决策由整体应用独立完成 |

## 8. 最终完成定义（Definition of Done）

项目只有同时满足以下条件才可宣告完成：

- 第 2 节所有适用指标均有真实输出文件和可重复命令支撑。
- 当前评审发现的 P0/P1 问题均有回归测试，且原始故障在修复前可复现、修复后通过。
- 没有已知未处置的数据删除、静默假成功、无界队列、未授权非回环暴露和资源泄漏问题。
- 既有插件兼容契约通过；所有语义变更均有开发者批准、迁移指南和兼容层。
- 72 小时长稳、异常恢复、MCP 重连和基准性能报告全部完成。
- 文档明确框架能力边界，未把行业插件职责或外部实时系统职责包装成框架原生保证。
