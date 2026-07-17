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

# b) QSS 注释移除不截断 url 中的 ://
from utils.style_qss.styles import _remove_comments

sample = (
    "QWidget { image: url(http://example.com/a.png); } // 尾部注释\n"
    "// 行首注释整行\n"
    "QFrame { background: url(data://x//y); }\n"
    "QLabel { color: red; }  // 前置空白行内注释\n"
)
out = _remove_comments(sample)
check("b1 url(http://...) 不被截断", "url(http://example.com/a.png)" in out)
check("b2 url 内 // 保留", "url(data://x//y)" in out)
check("b3 行首注释被移除", "行首注释整行" not in out)
check("b4 行内注释被移除且声明保留", "尾部注释" not in out and "color: red;" in out)

# b5 聚合 QSS 可用且包含 :focus 焦点样式与箭头 url
from utils.style_qss import create_qss
qss = create_qss('light')
check("b5 聚合 QSS 非空且变量已替换", len(qss) > 100 and '{accent}' not in qss)
check("b6 :focus 焦点边框存在", 'QLineEdit:focus' in qss and ':focus-visible' not in qss)
check("b7 箭头 url 指向实际 PNG", 'url(' in qss and 'spinBoxArrowUp_light.png' in qss)

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
