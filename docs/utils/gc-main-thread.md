# 主线程 GC 守卫（utils/gc_main_thread.py）

> 目的：缓解 2026-11-04 复现的原生闪退（`python314.dll` / `0xc0000005` /
> 偏移 `0x91cc9`）。它是**缓解措施**，不是已证实的原生根因修复。

## 1. 现场证据

- 2026-11-04 两次长时间运行闪退，均为 `python.exe` → `python314.dll`，
  `0xc0000005`，偏移 `0x91cc9`；与历史记录中的 paint 崩溃签名一致；
- 应用崩溃日志的三段转储：
  - 两段当前线程在 Qt 图表 `axes.py::paint_axes` / 状态控件绘制；
  - 一段当前线程为后台任务 **`Garbage-collecting`**（在事件快照生成器分配
    对象时触发），同进程主线程正在 `paint_axes`。
- 结论性推断：CPython 循环 GC 会在任意分配线程触发；若回收的是 PySide6/Qt
  包装对象，其 C++ 析构会在非 GUI 线程执行，可能造成原生访问违例。绘制线程
  是受害者，不是唯一原因。

## 2. 设计

`MainThreadGcGuard`（`utils/gc_main_thread.py`）：

1. `gc.collect(2)`：先完整回收一次启动期垃圾；
2. `gc.freeze()`：把启动期对象移出后续扫描（主窗口、已加载的常驻对象）；
3. `gc.disable()`：禁止任意线程自动触发循环回收；
4. 主线程 `QTimer` 每 `COLLECT_INTERVAL_MS`（2s）执行年轻代回收，
   每 `MIDDLE_COLLECT_INTERVAL_MS`（30s）执行中代回收，每
   `FULL_COLLECT_INTERVAL_MS`（300s）执行一次完整回收；完整回收覆盖较低代际，
   同一拍不重复执行多个代际；
5. 手动 `collect_now()` 保持完整回收语义，并重置中代与完整回收的时间基准；
6. 每次分代回收的代际、耗时与对象数记 DEBUG；单次超过
   `SLOW_COLLECT_WARN_MS`（100ms）另记 WARNING，便于评估节拍；
7. `shutdown()` 停止节拍并 `gc.enable()`，进程退出前调用。

`main.py` 在 `QApplication.exec()` 之前 `install()`，`exec()` 返回后
`shutdown()`。只接管**循环垃圾**；引用计数回收（绝大多数 Qt 对象）不受影响。

## 3. 代价与边界

- 年轻代引用环通常最多暂存 2s；熬过年轻代的对象可能等到 30s 中代回收，
  需要完整扫描才能发现的引用环最长可能暂存 5 分钟；
- 分代调度降低的是常规回收的扫描范围，**完整回收仍可能产生明显停顿**；
  若 WARNING 仍集中在 `generation=2`，应继续减少循环垃圾或调整完整回收节拍，
  不得把回收移到后台线程；
- 若主线程被长绘制阻塞，回收节拍顺延；
- `gc.freeze()` 后启动期已存在的环不再回收（换来稳定，不用于长期热插拔）；
- **不保证**消除 Qt C++ 内部或驱动层的绘制缺陷：若长时间运行仍闪退，
  下一步需按 §4 取原生 dump。

## 4. 后续排查（若仍闪退）

1. 配置 WER LocalDumps（管理员）保留 `python.exe` 完整 dump：
   `HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\python.exe`
   → `DumpFolder`（本地目录）、`DumpType=2`；
2. 复现后用 WinDbg `!analyze -v` / `!heap` 查看 C 层栈与堆状态；
3. 对照变量：减少后台任务负载、关闭图表 GL 视口、更新/回退 Intel 显卡驱动；
4. 若根因转为 Qt/PySide 版本问题，再做版本回退对照。

## 5. 验证

- 临时冒烟脚本：安装后 `gc.isenabled()==False`、定时器激活、循环对象可被
  `collect_now()` 回收、重复安装幂等、`shutdown()` 恢复 GC；分代调度另需验证
  年轻代/中代/完整回收的到期顺序，以及手动完整回收后不会立即重复完整回收；
- 启动日志出现 `主线程GC守卫已启用：young=2000ms，middle=30000ms，full=300000ms`；
- 长测要求：与闪退相同的业务场景（长时间运行 + 后台任务 + 图表持续刷新）
  连续运行 ≥10 分钟，不出现原生退出，并观察 `主线程GC回收耗时` 告警与内存增长。
