# 系统托盘与关闭行为

> InstructionX 主窗口关闭行为与系统托盘运行机制的完整说明
>
> 实现位置：`ui/tray/`（托盘子系统）、`ui/dialog/close_confirm_dialog.py`（确认对话框）、
> `ui/main_window.py`（关闭编排）、`main.py`（退出时机控制）

---

## 1. 关闭行为总览

`main.py` 在创建 `QApplication` 后调用 `setQuitOnLastWindowClosed(False)`，
「最后一个窗口关闭即退出事件循环」的隐式链路被切断，退出时机完全由代码显式控制。

主窗口 `InstructionXMainWindow.closeEvent` 统一拦截全部关闭路径：

| 触发路径 | 来源 |
|---|---|
| 自绘关闭按钮（叉子） | `ui/title_bar.py` → `window.close()` |
| 标题栏右键菜单「关闭(C)」 | `ui/title_bar.py` → `window.close()` |
| Alt+F4 | Windows WM_CLOSE → Qt `closeEvent` |
| 任务栏图标右键「关闭窗口」 | 同上 |

拦截后的分发逻辑：

```
closeEvent
  ├─ _force_quit 已置位（托盘菜单「退出」/ 系统关机）→ accept + QApplication.quit()
  ├─ _close_dialog_showing（确认框已弹出，防重入）→ ignore
  └─ 弹出 CloseConfirmDialog（每次必问，无记忆选项）
       ├─ 退出程序      → _force_quit 置位 + accept + QApplication.quit()
       ├─ 最小化到托盘  → ignore + _minimize_to_tray()
       └─ 取消          → ignore（窗口保持原状）
```

标题栏的最小化按钮（—）保持原语义：最小化到任务栏、不弹窗、不进托盘；
只有「关闭」语义才触发询问（与微信、QQ 等 Windows 惯例一致）。

## 2. 系统托盘

### 2.1 包结构（ui/tray/）

```
ui/tray/
  __init__.py            # re-export TrayIconManager
  manager.py             # TrayIconManager：平台无关门面（QObject，持有 QSystemTrayIcon）
  backend.py             # TrayBackend 抽象基类 + TrayCapabilities + 注册表与工厂
  backends/
    __init__.py          # 装配点：向注册表登记各平台后端
    windows.py           # WindowsTrayBackend：双击恢复 + Toast 通知
    generic.py           # GenericTrayBackend：保守兜底（仅菜单恢复、不弹通知）
```

平台差异收敛在 `TrayBackend` 后端实现中，门面不出现任何 `sys.platform` 判断
（注册表/工厂模式，与 `core/llm/providers/` 的 `PROVIDER_REGISTRY` 同一思路）。
新增平台支持的改动面为「一个后端文件 + 一行注册」，macOS/Linux 为预留扩展点。

### 2.2 托盘菜单（四项）

```
├─ 显示主窗口
├─ 正在运行的插件 ▸      （子菜单，aboutToShow 时动态重建）
│    ├─ ✓ 当前激活插件（勾选标记，点击恢复主窗口并切换）
│    ├─ 其他已加载插件…
│    └─ （无已加载插件时置灰显示「无已加载插件」）
├─ 后台正在运行的任务 ▸  （子菜单，aboutToShow 时动态重建，只读展示）
│    ├─ 任务名（插件名）
│    └─ （无运行中任务时置灰显示「无运行中的任务」）
└─ 退出                  （不再询问，直接退出）
```

- 两个状态子菜单在 `aboutToShow` 时动态重建，保证状态最新；数据来源由主窗口经
  `TrayIconManager.set_status_providers()` 注入两个回调，门面不直接依赖
  PluginManager / BackgroundTaskManager；查询异常记 WARNING 并降级为占位项，
  不影响托盘菜单弹出。
- 任务条目合并一次性任务（RUNNING/PENDING）与运行中的长期任务
  （`LongRunningTask.current_status == "running"`）。
- Windows 上**双击托盘图标**同样恢复主窗口（`DoubleClick` 激活原因由后端声明）。

### 2.3 恢复与退出

- **恢复主窗口**（菜单项或双击）：`showNormal()` + `raise_()` + `activateWindow()`；
  恢复后托盘图标移除（下次最小化时再驻留）。
- **退出**：托盘菜单「退出」置 `_force_quit` 后 `QApplication.quit()`，不再弹确认框；
  `aboutToQuit` 中隐藏托盘图标，避免通知区域残留「幽灵图标」。
- 托盘不可用时（如裸 GNOME 桌面），「最小化到托盘」降级为普通最小化
  （`showMinimized()`，任务栏保留图标）并记 WARNING 日志。

### 2.4 通知提示

**每次**最小化到托盘都尝试弹出通知提示（「程序已最小化到系统托盘，仍在后台继续运行」）。
Windows 10/11 上走系统 Toast 通知，可能被「专注助手」或通知设置屏蔽——提示不作为
功能正确性依赖，发送失败仅记 INFO 日志，托盘图标本身仍在。

### 2.5 托盘运行 ≠ 休眠

最小化到托盘后，后台任务管理器、MCP Server、LLM 流式请求等照常全量运行。

## 3. Windows 注销 / 关机不阻塞

Windows 注销/关机要求各进程快速响应结束会话；若此时弹出模态确认框无人点击，
系统关机会被本程序阻塞。主窗口接线 `QApplication.commitDataRequest`
（QGuiApplication 的会话结束信号，Windows 上对应 WM_QUERYENDSESSION）：
回调中直接置 `_force_quit = True` 并 `QApplication.quit()` **静默退出，不弹任何对话框**；
随后系统下发的 `closeEvent` 因 `_force_quit` 已置位而直接 accept，不阻塞系统关机。

## 4. 相关文档

- [主窗口](main-window.md)
- [对话框组件](dialogs.md)（CloseConfirmDialog 章节）
- [后台任务概述](../core/background-task/overview.md)
