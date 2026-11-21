# 基础框架可靠性验证报告

## 1. 结论与证据边界

本报告对应 Task 0–13 的代码、测试和文档交付。Task 12 代码基线为 `dev 38d5db9`，测试基线为 `test f16874e`；Task 13 仅补充文档与发布核对，不修改框架版本号或插件目录。

**结论：已执行范围内的工程可靠性门禁通过，可以作为本项目定义的通用桌面和行业辅助工程基线。真实行业生产发布仍需部署方完成场景、数据规模、外部系统和法规验证。**

以下状态严格区分：

- `PASS`：对应范围已实际执行并通过，不外推到未测环境。
- `ACCEPTED`：实际时长或环境有边界，但开发者已明确接受该次结果。
- `NOT_RUN`：没有真实执行证据，禁止写成通过。

本报告不宣称工业/医疗认证、硬实时、临床正确性、设备安全性或 72 小时长稳完成。

## 2. 当前采集与测试证据

| 证据 | 最新结果 | 文件/命令 |
|---|---|---|
| 当前基础基准 | 五类负载和九项故障全部 PASS；当前 P0/P1=0；顶层因明确未执行项为 NOT_RUN | `temp/foundation-final.json` |
| 全量 pytest | 1342/1342 通过；PYTHONUTF8=1 最终运行无警告 | `temp/foundation-final-pytest.log`；标准命令 `python -m pytest test/ -q --tb=short -p no:cacheprovider` |
| 短时调度/取消 SLO | 2/2 通过；实际执行开始与真实停止确认口径 | `test/core/task/test_timing_slo.py`、`temp/foundation-timing-slo.log` |
| 进程隔离 | 14/14 通过；真实 Windows 子进程与 watchdog | `test/core/plugin_host/test_process_isolation.py` |
| 框架自检 | 15/15 通过 | `scripts/smoke_foundation_hardening.py` |
| 固定故障矩阵 | 31/31 通过 | `test/core/test_foundation_fault_matrix.py` |
| 完整插件契约 | 签名、依赖注入、插件管理和 `legacy_pytest` 全部 PASS | `scripts/validate_plugin_contracts.py` |
| 契约专项 | 6/6 通过 | `test/core/test_plugin_contracts.py` |
| 离线 GUI | 3/3 通过；最终全量中的启动增幅≤10% | `test/ui_tests/test_startup_offline.py` |
| MCP | 28/28；stdio/HTTP 各 100 次重连，无遗留工具、进程或清理警告 | `scripts/_mcp_smoke.py` |
| 异常恢复 | 100/100，4.898612 秒，RTO<60 秒 | `InstructionX-test/temp/fault-inject-foundation.json` |
| 快速故障/网络 | GUI/契约/429/500/读超时/流中断/5 次恢复 PASS；真实 DNS NOT_RUN | `InstructionX-test/temp/fault-inject-quick-task12.json` |
| OSV | No known vulnerabilities found | CI 同款 `uv export` + `pip-audit==2.10.1 -s osv` |

`foundation-optimized.json` 是 Task 10 的历史快照，包含当时的故障与 `comparison.status=REGRESSION`，不得作为当前状态。当前采集使用 `foundation-final.json`；未用新旧报告拼接出虚假的“全面零回归”。

## 3. SLO 对照

| 验收项 | 结果 | 实测证据与限制 |
|---|---|---|
| 数据库损坏/锁定/只读/迁移保护 | PASS | 故障矩阵 31/31；既有文件保留或形成可恢复副本 |
| 故障显式化 | PASS | 无生产 MagicMock 回退；健康、错误码和关联 ID 测试通过 |
| durable 写入进程崩溃 RPO=0 | PASS（限定模型） | 已提交 SQLite 行在子进程异常退出后保留；不是物理断电证明 |
| durable 写入虚拟机断电 RPO=0 | NOT_RUN | 无安全可用真实断电环境；DataProvider 也没有 durable 开关 |
| 异常恢复 RTO≤60 秒 | PASS | 100/100，4.898612 秒 |
| 32 个长期任务下高优 p99≤100ms | PASS | 长稳 `high_task` p99=13.7283ms，4096 样本 |
| 普通短任务 p99≤1 秒 | PASS | 长稳 `normal_task` p99=11.3977ms，4096 样本 |
| 100 个定时任务 p99≤250ms | PASS | 与 32 个长期任务并存，实际开始 p99=3.011300ms，100 样本 |
| 协作停止 p99≤2 秒 | PASS | 20 次真实协作停止 p99=0.004110 秒；实际退出前保持 CANCELLING |
| 离线启动增幅≤10%、本地 p95≤100ms | PASS | 离线 GUI 3/3；最终全量通过 |
| 图表入图 p95≤16.7ms | PASS | `chart_apply_ms` p95=0.0508ms，4096 样本 |
| 图表帧间隔 p99≤33ms | PASS | `chart_interval_ms` p99=10.3870ms；真实 Qt 长稳场景 |
| 慢订阅者发布 p99≤10ms | PASS | `event_publish` p99=0.2688ms；回执不等于送达 |
| MCP 100 次重连 | PASS | stdio/HTTP 各 100 次，无泄漏和清理警告 |
| 非回环无认证阻断 | PASS | 安全回归与 MCP 冒烟；白名单读取失败关闭 |
| 插件兼容 | PASS | 完整契约与官方示例加载/卸载通过，未批准签名破坏为 0 |
| 关键插件故障隔离 | PASS | 14/14；崩溃、超时、洪水、错误协议、强杀回收和熔断 |
| 七小时混合负载 | ACCEPTED | 实测 25358.523151 秒（约 7.04 小时），开发者接受；原始 72 小时报告仍 NOT_RUN |
| 72 小时混合负载 | NOT_RUN | 未执行 72 小时，不得改写成完成 |
| OSV 无未处置 Critical/High | PASS | 本次无已知漏洞；后续发布必须重新审计 |

## 4. 七小时长稳详情

证据文件：`temp/foundation-soak-7h-accepted.json`。命令请求参数为 72 小时，实际预热 300 秒、测量 25358.523151 秒后由开发者接受并停止，`failures=[]`、`errors=[]`、`gui_status=EXECUTED`。文件保持 `qualification_status=NOT_RUN`，这是原始命令未跑满的正确状态。

| 指标 | 实测 |
|---|---:|
| 系统采样 | 423 次 |
| 每类性能指标样本 | 4096 次 |
| 内存首样本 / 峰值 / 末样本 | 331.125 / 341.793 / 279.230 MiB |
| 内存峰值相对首样本增长 | 约 3.22%（要求≤10%） |
| 句柄首样本 / 峰值 / 末样本 | 1062 / 1072 / 1072 |
| 句柄峰值增长 | 约 0.94%（要求≤5%） |
| 队列峰值 | event=256（上限 256）；long=32；high=0；normal=0 |
| SQLite 写 / 读 p95 | 0.3053 / 0.0525ms |
| 高优 / 普通任务 p99 | 13.7283 / 11.3977ms |
| 事件发布 p99 | 0.2688ms |
| MCP p95 | 9.9477ms |
| 图表入图 p95 / 帧间隔 p99 | 0.0508 / 10.3870ms |

最大值高于 p99 的样本保留在原始 JSON 中，没有被删除或替换为平均值。验收以各指标声明的 p95/p99 为准。

## 5. balanced/durable、事件与取消边界

- DataProvider 固定 WAL + `synchronous=NORMAL`，只有 balanced；进程崩溃结果不能外推为断电保证。
- LLM 用量和会话默认 durable（显式事务 + FULL）；`durable=False` 才是 balanced。真实断电未测。
- 异步公开数据先持久化，再进入有界内存邮箱；回执不是送达确认，合并/丢弃只用于显式允许的场景。
- 新协作取消只有实际退出才为 CANCELLED；旧取消 API 的兼容状态语义未改变。
- `ApplicationLifecycle` 的关闭报告反映等待与清理结果，不保证不配合函数已停止，也不代表外部设备安全。

## 6. NOT_RUN 与发布限制

1. 真实物理磁盘满未执行；ENOSPC 注入只证明错误处理，不证明真实介质行为。
2. 真实虚拟机断电未执行；不能声明 durable 断电 RPO=0。
3. 真实外部 Provider 网络未执行；受控适配器只证明框架超时与恢复逻辑。
4. 当前 DNS 环境使保留 `.invalid` 域名返回地址，真实 DNS 失败为 NOT_RUN；回环网络用例已执行。
5. 72 小时长稳未执行；只有约 7.04 小时的开发者接受结果。
6. 真实行业灰度尚未执行；部署指南中的阶段 1–3 是待执行流程，不是上线记录。
7. 默认编码的历史运行曾有 6 个 subprocess GBK 解码警告；最终 `PYTHONUTF8=1` 全量运行无警告。日志保存于 `temp/foundation-final-pytest.log`，后续默认环境发布仍应复核编码行为。

任何依赖上述未执行项的声明都必须保持阻塞。发布方不得以“基本可用”替代这些限制，也不得把模拟结果写成真实环境验收。

## 7. 发布核对清单

- [x] 当前 P0/P1 数据删除、静默假成功、无界队列、未授权非回环暴露和资源泄漏失败为 0（已测范围）。
- [x] 完整 pytest、GUI、MCP、插件管理、公开契约和进程隔离通过。
- [x] 100 次恢复、各 100 次 MCP 重连、当前基准与约 7.04 小时长稳有证据。
- [x] OSV 无已知漏洞；凭据脱敏和 MCP 失败关闭回归通过。
- [x] 三种部署档位、灰度回滚和外部实时/行业插件职责已写入文档。
- [x] 所有未执行项目及历史相对性能回归均明确披露。

**最终门禁意见：允许按部署指南进入内部工具灰度；非关键行业辅助灰度须先完成对应数据规模复测；关键行业生产发布须另行完成本报告 NOT_RUN 中与其安全论证相关的项目。**
