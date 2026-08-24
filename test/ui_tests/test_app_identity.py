"""应用标识与启动接线测试。

覆盖点（对应 dev 分支两个提交）：

- 「组织名由 LumenThread 改为 KKPIP-Tech」：
  - ``QSETTINGS_ORG_NAME`` 常量为 ``KKPIP-Tech``（与 GitHub 组织一致）；
  - ``main.py`` 的 ``setOrganizationName`` 字面量与 QSettings 组织名一致
    （防止两处组织名漂移——QSettings 键路径由组织名决定，不一致会导致
    「上次选中的实例」记忆写入与读取落在不同注册表位置）；
  - 应用名为 ``InstructionX - CE``。
- 「main.py 统一顶层窗口图形 API 为 OpenGL」：
  - ``main()`` 中 ``QQuickWindow.setGraphicsApi(...OpenGL)`` 调用必须先于
    ``QApplication(...)`` 实例化（UIKit Mermaid WebEngine 与蓝图 GL 视口
    同窗口混用的前置条件）。

通过 AST 静态解析 ``main.py`` 实现，不启动应用、不触注册表。
"""

import ast
from pathlib import Path

from ui.dialog.llm_settings.constants import (
    QSETTINGS_APP_NAME,
    QSETTINGS_ORG_NAME,
)

#: 当前组织名（与 GitHub 组织 KKPIP-Tech 一致；变更时需同步更新本常量）
EXPECTED_ORG_NAME = "KKPIP-Tech"
#: 应用名（QApplication.setApplicationName / QSettings 应用名）
EXPECTED_APP_NAME_DASHED = "InstructionX-CE"
#: 项目根目录（本文件位于 test/ui_tests/ 下）
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _main_function_calls() -> list:
    """解析 main.py，返回 main() 函数体内顶层表达式调用节点列表（按源码顺序）。"""
    tree = ast.parse((PROJECT_ROOT / "main.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return [
                stmt.value for stmt in node.body
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
            ]
    raise AssertionError("main.py 中未找到 main() 函数")


def _find_call(calls: list, attr_name: str):
    """在调用列表中查找 obj.attr(...) 形式、方法名为 attr_name 的调用节点。"""
    for call in calls:
        func = call.func
        if isinstance(func, ast.Attribute) and func.attr == attr_name:
            return call
    return None


class TestOrganizationName:
    """组织名常量的值与一致性。"""

    def test_qsettings_org_name_is_kkpip_tech(self):
        """QSettings 组织名为 KKPIP-Tech（与 GitHub 组织一致）。"""
        assert QSETTINGS_ORG_NAME == EXPECTED_ORG_NAME

    def test_main_py_organization_name_matches_qsettings(self):
        """main.py setOrganizationName 字面量必须与 QSETTINGS_ORG_NAME 一致。"""
        calls = _main_function_calls()
        call = _find_call(calls, "setOrganizationName")
        assert call is not None, "main() 中未找到 setOrganizationName 调用"
        assert len(call.args) == 1 and isinstance(call.args[0], ast.Constant)
        assert call.args[0].value == QSETTINGS_ORG_NAME

    def test_main_py_application_name(self):
        """main.py setApplicationName 为 'InstructionX - CE'。"""
        calls = _main_function_calls()
        call = _find_call(calls, "setApplicationName")
        assert call is not None, "main() 中未找到 setApplicationName 调用"
        assert call.args[0].value == "InstructionX - CE"

    def test_qsettings_app_name(self):
        """QSettings 应用名常量（连字符形式，与注册表路径一致）。"""
        assert QSETTINGS_APP_NAME == EXPECTED_APP_NAME_DASHED


class TestGraphicsApiUnification:
    """main() 中 OpenGL 图形 API 统一必须先于 QApplication 实例化。"""

    def test_set_graphics_api_called_with_opengl(self):
        """存在 QQuickWindow.setGraphicsApi(...GraphicsApi.OpenGL) 调用。"""
        calls = _main_function_calls()
        call = _find_call(calls, "setGraphicsApi")
        assert call is not None, "main() 中未找到 setGraphicsApi 调用"
        # 参数应为 QSGRendererInterface.GraphicsApi.OpenGL 属性链
        attr = call.args[0]
        assert isinstance(attr, ast.Attribute) and attr.attr == "OpenGL"

    def test_graphics_api_set_before_qapplication(self):
        """setGraphicsApi 在源码顺序上先于 QApplication(...) 实例化。"""
        tree = ast.parse((PROJECT_ROOT / "main.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "main":
                main_func = node
                break
        else:
            raise AssertionError("main.py 中未找到 main() 函数")

        order = []
        for stmt in main_func.body:
            if not (isinstance(stmt, (ast.Expr, ast.Assign))):
                continue
            value = stmt.value
            if not isinstance(value, ast.Call):
                continue
            func = value.func
            if isinstance(func, ast.Attribute) and func.attr == "setGraphicsApi":
                order.append("setGraphicsApi")
            elif isinstance(func, ast.Name) and func.id == "QApplication":
                order.append("QApplication")
        assert order == ["setGraphicsApi", "QApplication"], (
            f"main() 调用顺序非法: {order}（setGraphicsApi 必须先于 QApplication）"
        )
