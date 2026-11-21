# 关键插件进程隔离与外部 Watchdog

## 1. 能力边界

`core/plugin_host/` 是**可选**的单插件进程外宿主。既有 `PluginManager` 仍默认在同进程加载受信任插件；只有应用明确调用 `PluginHost.start()` 的插件才进入独立进程。本能力不修改既有插件目录结构、`IPlugin`、`IPluginInfo`、`PluginServices` 或自动 API 注册契约。

适用对象是满足以下条件的 Service/API：

- 不需要创建或返回 Qt Widget、QIcon 等 GUI 对象；
- 公开方法已通过 `information.py.service_api` 声明，参数和返回值均可严格 JSON 序列化；
- 能接受 Service 在子进程内串行执行，以及崩溃重启后的内存状态丢失；
- 能接受子进程拥有独立的框架单例和 DataProvider 连接，不同进程间的内存缓存与发布订阅不自动同步。

进程隔离用于限制插件崩溃、死循环和协议故障的影响范围，**不是安全沙箱**。子进程仍以当前用户权限运行，不能防御恶意插件主动访问用户文件、网络或其他进程。插件自行创建的孙进程也由插件负责回收，框架只保证直接插件子进程的回收。

硬实时采集、设备控制、安全联锁、临床决策与行业业务验证仍由外部专用系统或插件负责。心跳仅表示宿主进程仍能发送协议消息，不代表业务数据正确或服务调用一定成功。

## 2. 协议与调用

协议为四字节大端长度前缀加 UTF-8 JSON 对象，版本固定为 `1`。默认单消息上限为 1 MiB，可配置但绝不超过 16 MiB。接收端拒绝：

- 不支持的消息版本、类型、字段集合、请求 ID 或错误码；
- 重复 JSON 字段、非有限数值、截断帧和超长消息；
- 未登记且也不是已超时请求的响应 ID。

```python
from pathlib import Path

from core.plugin_host import HostConfig, PluginHost, RemotePluginProxy

host = PluginHost()
handle = host.start(
    Path("custom_plugin/example-critical-service"),
    HostConfig(
        startup_timeout=10.0,
        heartbeat_interval=1.0,
        heartbeat_timeout=3.0,
        max_restarts=2,
        max_pending_calls=16,
    ),
)
proxy = RemotePluginProxy(host, default_timeout=0.5)
result = proxy.read_status({"channel": "local-monitor"})
if result.error is not None:
    # 调用方必须显式处理错误码，不得把空值当作业务成功。
    print(result.error.code, result.error.message)
report = host.stop(timeout=3.0)
```

`PluginHost.call(method, args, timeout)` 的 `args` 为位置参数数组或命名参数对象，返回 `RpcResult`。`RemotePluginProxy` 提供同名方法转发，同样返回 `RpcResult`，不会把异常隐藏为空结果。

## 3. 故障与重启语义

- 调用等待时间、在途请求数和写入队列均有上限；饱和返回 `HOST_BUSY`，超时返回 `CALL_TIMEOUT`。
- 进程退出、stdin/stdout 中断或协议故障使在途请求收到 `PLUGIN_UNAVAILABLE`，不会导致主进程退出。
- 插件异常返回 `PLUGIN_ERROR`，未注册方法返回 `METHOD_NOT_FOUND`，非法参数或不可序列化结果分别返回明确错误。
- 心跳缺失或进程失效后按 `max_restarts` 执行有限重启。该预算是宿主单次启动后的**累计次数**，不会因多次就绪而自动重置；耗尽进入 `CIRCUIT_OPEN`。
- 熔断后的调用返回 `CIRCUIT_OPEN`。运维人员检查原因后可先 `stop()` 再显式 `start()`，框架不会无限重启。
- 请求登记时固定进程代际。崩溃后残留在旧写入队列的请求会被丢弃，**绝不自动重放到新进程**。调用方无法确认崩溃前是否已产生副作用，非幂等操作必须由业务层通过对账或幂等键处理。
- `snapshot()` 提供状态、PID、累计重启数、在途数、最近心跳与脱敏错误摘要，不包含调用参数和返回值。

正常停止先发送 shutdown，并复用 `ApplicationLifecycle` 清理插件、任务、MCP、LLM 与数据层。插件不合作时，在截止期后强制终止直接子进程；`StopReport.forced` 会标记该情况。主进程正常退出由 `atexit` 回收宿主；主进程被强杀时，子进程通过 stdin 断开和父 PID 监测兜底退出。

## 4. 外部 Watchdog

`core/external_watchdog.py` 提供无全局状态的 `Watchdog.check_once()`，`scripts/external_watchdog.py` 是用户手动启动的独立入口。应用侧由 `HeartbeatFile` 原子写入版本、PID 和时间戳。

仅支持三种显式动作：

| 动作 | 行为 |
|---|---|
| `none` | 只报告健康、过期或退出状态，不操作进程 |
| `exit` | 终止配置的目标 PID，并在截止期内确认退出 |
| `restart` | 终止失效目标后，仅执行配置的 `restart_command`；缺命令时配置校验失败 |

心跳损坏、字段缺失、版本/PID 不匹配或时间戳异常时返回 `INVALID_HEARTBEAT`，**不执行动作**。Windows 使用原生退出码和进程等待句柄确认终止，不以 `os.kill(pid, 0)` 或忽略权限错误冒充回收成功。

示例配置（路径需替换为实际绝对路径）：

```json
{
  "heartbeat_path": "C:/ProgramData/InstructionX/heartbeat.json",
  "target_pid": 12345,
  "stale_after": 10.0,
  "action": "restart",
  "restart_command": ["C:/path/to/python.exe", "C:/path/to/main.py"],
  "termination_timeout": 3.0
}
```

```powershell
.venv\Scripts\python.exe scripts\external_watchdog.py --config config\watchdog.json --once
.venv\Scripts\python.exe scripts\external_watchdog.py --config config\watchdog.json --interval 1
```

Watchdog 必须由用户或系统服务显式启动，pytest 和 CI 不会启动持续监测循环。重启仅表示新进程已创建，不代表应用已恢复业务健康；业务就绪仍需后续健康检查。心跳文件不是身份认证机制，不能抵御同权限恶意篡改。

## 5. 验证范围

`test` 分支的 `test/core/plugin_host/test_process_isolation.py` 使用 `tmp_path` 中的真实插件和真实 Windows 子进程验证：协议边界、正常/异常调用、代理、死循环超时、等效段错误的进程退出、消息洪水、错误协议、有限重启、熔断、有界并发、启动失败、正常/强制停止、主进程强杀回收，以及 watchdog 健康、损坏心跳、退出和重启动作。测试不会修改 `plugin/` 或 `custom_plugin/`。
