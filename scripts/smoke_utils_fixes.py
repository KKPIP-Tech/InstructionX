# -*- coding: utf-8 -*-
"""utils 工具层修复冒烟脚本（一次性验证，非 pytest）"""
import io
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

failures = []


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        failures.append(name)


# a) 直接向 'ApplicationLogger' 写日志不再 KeyError
from utils.logging_tools import LoggerManager, get_name

manager = LoggerManager()
stream = io.StringIO()
handler = logging.StreamHandler(stream)
handler.setFormatter(logging.Formatter(
    fmt='[%(asctime)s][%(module_name)s][%(levelname)s][Message-->][%(message)s]',
    datefmt='%Y-%m-%d][%H-%M-%S',
))
logging.getLogger('ApplicationLogger').addHandler(handler)

err = io.StringIO()
old_stderr = sys.stderr
sys.stderr = err
try:
    logging.getLogger('ApplicationLogger').info('x')  # 未经 LoggerManager.log()
finally:
    sys.stderr = old_stderr
check("a1 直接写 logger 无 logging 错误", 'KeyError' not in err.getvalue() and 'Logging error' not in err.getvalue(), err.getvalue()[:200])
check("a2 module_name 回退为 record.module", '[logging]' in stream.getvalue() or 'smoke' in stream.getvalue(), stream.getvalue().strip()[-80:])

# a3 get_name 缓存一致
n1, n2 = get_name(), get_name()
check("a3 get_name 缓存后结果一致", n1 == n2 == '__main__'.join([]) or n1 == n2, f"name={n1}")

# c) thread_utils 无 QApp 时降级可用
from utils import is_ui_thread, run_in_ui_thread, run_in_ui_thread_sync

check("c1 无 QApp 时 is_ui_thread 为 False", is_ui_thread() is False)
called = []
run_in_ui_thread(called.append, 42)
check("c2 无 QApp 时 run_in_ui_thread 降级直接执行", called == [42])
ret = run_in_ui_thread_sync(lambda a, b: a + b, 2, 3, timeout=1)
check("c3 无 QApp 时 run_in_ui_thread_sync 降级返回结果", ret == 5)

print()
if failures:
    print("FAILED:", failures)
    sys.exit(1)
print("ALL SMOKE CHECKS PASSED")
