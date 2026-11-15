# 故障、兼容性与长稳验证

## 1. 验证入口

```powershell
# 完整 pytest（含真实 GUI）
python -m pytest test/ -q --tb=short -p no:cacheprovider

# 插件公开契约、官方插件生命周期和旧格式
.venv\Scripts\python.exe scripts\validate_plugin_contracts.py

# 快速故障、网络、恢复、契约和真实 GUI 子集
.venv\Scripts\python.exe scripts\fault_inject_foundation.py --quick --allow-not-run

# 完整 100 次异常启动恢复和 MCP 重连
.venv\Scripts\python.exe scripts\fault_inject_foundation.py

# 仅限用户手动触发，禁止 pytest 或 CI/CD 启动
.venv\Scripts\python.exe scripts\soak_foundation.py --hours 7 --sample-interval 60 --output temp/foundation-soak.json
```

`--allow-not-run` 只允许环境相关未执行项在 CI 快速门禁中退出 0，JSON 中的 `NOT_RUN` 保持不变。完整验收不得用它把未执行能力视为通过。

## 2. 当前自动化证据

| 项目 | 结果 | 范围 |
|---|---|---|
| 全量 pytest | 1340/1340 通过，既有 6 个 GBK 警告 | 单元、集成、真实 GUI、旧格式、公开契约与进程隔离 |
| 进程隔离与 watchdog | 14/14 通过 | 真实插件进程、严格协议、死循环、崩溃、洪水、熔断、主进程强杀回收与显式恢复动作 |
| 固定故障矩阵 | 31/31 通过 | 损坏、锁定、只读、ENOSPC、进程异常退出、Provider 超时、MCP 断连、慢订阅者、插件异常 |
| 契约测试 | 6/6 通过 | 签名、可选扩展、依赖注入、IDataProvider 不被扩大、真实恢复点启动 |
| 离线 GUI | 3/3 通过 | 全 Provider 离线可交互、启动增幅≤10%、本地 p95≤100ms、50 次对话框开关 |
| 异常启动恢复 | 100/100，4.711343 秒 | 真实备份恢复点替换和 SQLite 重新启动，RTO<60 秒 |
| MCP 冒烟 | 28/28 | 各 100 次 stdio/HTTP 连接、调用、断开，无遗留工具、进程或清理警告 |
| 快速 CI 故障 | 除 DNS 外全部通过 | 契约、故障、429、5xx、读超时、流中断、5 次恢复 |
| 长稳采集器短窗 | 预热 300 秒 + 测量 123.038821 秒通过 | 无失败项；内存/句柄峰值和全部性能门槛合格，不作为长稳证据 |
| 手动长稳验收 | 实际测量 25358.523151 秒（约 7.04 小时），开发者确认接受 | 最近报告失败项与错误均为空；`temp/foundation-soak-7h-accepted.json`；不宣称完成 72 小时 |

`TaskStorage.save_data()` 现在返回布尔回执：原子替换成功为 `True`，失败为 `False` 并保留 `_cache_dirty=True`。旧调用方可以忽略返回值，但要求 durable 确认的调用方必须检查。

DataProvider 在公共边界把原生 `sqlite3.Error` 统一转换为 `DataProviderError`，锁释放后可恢复写入。异步慢订阅者测量使用 `publish_async` 和实际送达计数，不把同步阻塞或入队回执混入新 API 指标。

## 3. 环境相关 NOT_RUN

- 当前 DNS 环境对保留的 `does-not-exist.invalid` 域名返回地址，无法证明真实 DNS 失败语义，因此 `dns_failure=NOT_RUN`。不通过本地抛出 `gaierror` 冒充真实 DNS 结果。
- 真实物理磁盘满和虚拟机断电没有安全可用环境，不能用 ENOSPC 注入或自愿 `os._exit` 替代。
- 真实外部 Provider 网络未用于验证；受控适配器只证明框架的超时和恢复逻辑。

## 4. 手动长稳验收

长稳负载只允许用户在基准机上通过以下专用命令手动触发，**禁止由 pytest、GitHub Actions 或其他 CI/CD 定时/推送任务启动**。工作流只执行完整 pytest 和快速故障/契约门禁；`test/utils/test_soak_foundation.py` 仅用替代组件验证采集逻辑，不执行真实长稳负载。

```powershell
.venv\Scripts\python.exe scripts\soak_foundation.py --hours 7 --warmup-seconds 300 --sample-interval 60 --output temp/foundation-soak.json
```

采集器默认先以同样的混合负载预热 300 秒，再独立计时。报告分别记录 `warmup_completed`、测量期 `elapsed_seconds` 和总运行 `total_elapsed_seconds`，未达到命令指定时长时保持 `NOT_RUN`。测量期间周期性输出：

- SQLite、异步事件、普通/高优任务和 MCP 的 p50/p95/p99；
- 真实 Qt 20,000 点窗口、1kHz 突发输入的入图耗时与活跃帧间隔；
- 进程内存、句柄、任务和事件队列；
- 清理警告和组件错误。

长稳图表使用 UIKit 既有 `gpuDirect` 原生系列管线、120Hz 调度和 `auto_scale=False` 直接流式入口，后台磁盘/任务/MCP 操作在单 worker 中按每秒最多 10 轮混合操作串行执行，避免人为制造 GIL 饱和，GUI 主线程持续处理事件。长稳 MCP 使用独立的每分钟 100000 次有限上限，避免将高频 soak 误当成生产限流攻击；生产默认每分钟 60 次不变。错误证据同时记录异常类型，空 `TimeoutError` 不再失去分类。

采集器短窗测试只验证采集方法，不构成正式长稳证据。任何 SLO 越界、资源泄漏、未处理异常或清理警告均为 `FAIL`。内存、句柄和队列检查测量期全部采样的峰值，结束清理后的回落不会清除越界证据。空闲期不计入活跃 GUI 突发帧间隔，报告直接使用每帧原始间隔和实际入图耗时，而非每次突发的平均值。

本次开发者明确接受实际测量 25358.523151 秒（约 7.04 小时）的结果，并停止剩余时长。证据保存为 `temp/foundation-soak-7h-accepted.json`；原始报告因参数为 72 小时而保持 `NOT_RUN`，不得改写成完成 72 小时。
