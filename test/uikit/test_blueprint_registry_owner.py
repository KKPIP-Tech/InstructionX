"""UIKit Blueprint 节点注册表 owner 命名空间测试。

覆盖 owner 命名空间隔离能力（对应实现位于
``ui/InstructionX_UIKit/blueprint/`` 的 registry/canvas/menu/node_widget）：

- 兼容性：无 owner 的旧式注册 / 查询 / 创建行为不变，内置 start 全空间可用；
- 隔离性：同名类型跨 owner 各得各的，画布创建菜单 / ``add_node_at`` /
  ``body_builder`` 均按 owner 解析；
- 冲突告警：同空间异定义覆盖记 WARNING，同定义幂等静默；
- 跨空间兜底：``owner=None`` 全局未命中时跨空间查找，多命中记 WARNING
  并返回注册顺序的首个；
- 序列化：owner 画布 ``to_dict`` / ``from_dict`` 往返后引脚保持 owner 定义。

注意：NodeRegistry 是单例，内置节点（start）在模块导入时注册进首个实例，
因此用例隔离采用「快照 / 恢复 ``_specs``」而非重置 ``_instance``
（重置会丢失内置注册，导致 start 相关断言失败）。
"""

import logging

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QLabel

import ui.uikit_bootstrap  # noqa: F401  扩展 sys.path 使 InstructionX_UIKit 可导入
from ui.uikit_theme import apply_uikit_theme

from InstructionX_UIKit.blueprint import (
    BlueprintCanvas,
    BlueprintGraph,
    NodeRegistry,
    NodeSpec,
    register_node_type,
)
from InstructionX_UIKit.blueprint.menu import NodeCreationMenu

#: 注册表模块日志器名（标准库 logging，WARNING 断言用）
_REGISTRY_LOGGER = "InstructionX_UIKit.blueprint.registry"
#: 测试用两个 owner 标识
OWNER_A = "test_plugin_a"
OWNER_B = "test_plugin_b"


def _pin_ids(pins) -> list:
    """取节点引脚 id 列表（保持顺序）。"""
    return [p.id for p in pins]


def _registry_warnings(caplog) -> list:
    """从 caplog 中筛出注册表模块的 WARNING+ 记录。"""
    return [r for r in caplog.records
            if r.name == _REGISTRY_LOGGER and r.levelno >= logging.WARNING]


@pytest.fixture()
def registry():
    """返回全局 NodeRegistry，测试后恢复注册内容以保证用例间隔离。"""
    reg = NodeRegistry.instance()
    saved_specs = dict(reg._specs)
    yield reg
    reg._specs.clear()
    reg._specs.update(saved_specs)


@pytest.fixture(scope="module")
def uikit_theme(qapp):
    """应用全局 UIKit 主题（蓝图节点 Widget 依赖主题令牌）。"""
    apply_uikit_theme(qapp, "light")


# ---------------------------------------------------------------------------
# 兼容性：无 owner 旧行为
# ---------------------------------------------------------------------------

class TestCompatibility:
    """无 owner 时注册 / 查询 / 创建 / 注销行为与引入命名空间前一致。"""

    def test_register_without_owner_goes_global(self, registry):
        """无 owner 注册归入全局命名空间。"""
        spec = register_node_type("ns_compat_node", "兼容节点", "测试")
        assert spec.owner is None

    def test_spec_and_create_without_owner(self, registry):
        """spec() / create() 无 owner 时命中全局定义并按其建引脚。"""
        spec = register_node_type(
            "ns_compat_node", "兼容节点", "测试",
            inputs=[{"id": "in", "data_type": "any"}],
            outputs=[{"id": "out", "data_type": "any"}])
        assert registry.spec("ns_compat_node") is spec
        node = registry.create("ns_compat_node")
        assert _pin_ids(node.inputs) == ["in"]
        assert _pin_ids(node.outputs) == ["out"]

    def test_unregister_without_owner(self, registry):
        """unregister() 无 owner 注销全局定义，注销后 spec() 返回 None。"""
        register_node_type("ns_compat_node", "兼容节点", "测试")
        assert registry.unregister("ns_compat_node") is True
        assert registry.spec("ns_compat_node") is None

    def test_builtin_start_available_in_all_namespaces(self, registry):
        """内置 start 全局注册，无 owner 与任意 owner 下均解析到同一定义。"""
        global_start = registry.spec("start")
        assert global_start is not None
        assert registry.spec("start", owner=OWNER_A) is global_start
        node = registry.create("start", owner=OWNER_B)
        assert _pin_ids(node.outputs) == ["out"]


# ---------------------------------------------------------------------------
# 隔离性：同名异定义跨 owner 共存
# ---------------------------------------------------------------------------

def _register_load_image_pair() -> None:
    """在 owner A / B 下各注册一个同名异定义的 load_image。"""
    register_node_type(
        "load_image", "载入图像A", "输入", owner=OWNER_A,
        outputs=[{"id": "img", "data_type": "image"}])
    register_node_type(
        "load_image", "加载图片B", "IO", owner=OWNER_B,
        outputs=[{"id": "mat", "data_type": "tensor"}])


class TestIsolation:
    """同名类型在不同 owner 命名空间下互不覆盖、各自解析。"""

    def test_same_type_different_owners_independent(self, registry):
        """spec() 按 owner 各得各的定义，两个定义互不覆盖。"""
        _register_load_image_pair()
        spec_a = registry.spec("load_image", owner=OWNER_A)
        spec_b = registry.spec("load_image", owner=OWNER_B)
        assert spec_a is not None and spec_a.title == "载入图像A"
        assert spec_b is not None and spec_b.title == "加载图片B"
        assert spec_a is not spec_b

    @pytest.mark.ui
    def test_creation_menu_filters_by_owner(self, registry, qapp, uikit_theme):
        """A 画布创建菜单含全局 start 与 A 的 load_image，不含 B 的定义。"""
        _register_load_image_pair()
        canvas = BlueprintCanvas(BlueprintGraph(), owner=OWNER_A)
        menu = NodeCreationMenu(canvas, owner=OWNER_A)
        menu._rebuild()
        types = menu.matching_types()
        assert "start" in types
        assert "load_image" in types
        leaked = [t for t in types
                  if registry.spec(t, owner=OWNER_A).owner not in (None, OWNER_A)]
        assert not leaked
        menu.deleteLater()
        canvas.deleteLater()
        qapp.processEvents()

    @pytest.mark.ui
    def test_add_node_at_resolves_pins_per_owner(self, registry, qapp, uikit_theme):
        """A / B 画布 add_node_at 同名节点分别得到各自 owner 的引脚定义。"""
        _register_load_image_pair()
        canvas_a = BlueprintCanvas(BlueprintGraph(), owner=OWNER_A)
        canvas_b = BlueprintCanvas(BlueprintGraph(), owner=OWNER_B)
        node_a = canvas_a.add_node_at("load_image", QPointF(10, 10))
        node_b = canvas_b.add_node_at("load_image", QPointF(10, 10))
        assert _pin_ids(node_a.outputs) == ["img"]
        assert _pin_ids(node_b.outputs) == ["mat"]
        canvas_a.deleteLater()
        canvas_b.deleteLater()
        qapp.processEvents()


# ---------------------------------------------------------------------------
# 冲突告警：同空间异定义覆盖 WARNING / 同定义幂等
# ---------------------------------------------------------------------------

class TestConflictWarning:
    """同 owner 重复注册：定义相同静默幂等，引脚定义不同记 WARNING。"""

    def _register_warn_node(self, registry, inputs):
        """按给定输入引脚注册 ns_warn_node 到 owner A。"""
        registry.register(NodeSpec(
            type_name="ns_warn_node", title="告警节点", category="测试",
            inputs=inputs), owner=OWNER_A)

    def test_same_definition_reregister_is_silent(self, registry, caplog):
        """同 owner 同定义重复注册静默幂等（无 WARNING）。"""
        pins = [{"id": "a", "data_type": "any"}]
        self._register_warn_node(registry, pins)
        with caplog.at_level(logging.WARNING, logger=_REGISTRY_LOGGER):
            self._register_warn_node(registry, list(pins))
        assert not _registry_warnings(caplog)

    def test_different_definition_reregister_warns(self, registry, caplog):
        """同 owner 异定义重复注册产生 WARNING 且覆盖旧定义。"""
        self._register_warn_node(registry, [{"id": "a", "data_type": "any"}])
        with caplog.at_level(logging.WARNING, logger=_REGISTRY_LOGGER):
            self._register_warn_node(registry, [{"id": "b", "data_type": "int"}])
        warnings = _registry_warnings(caplog)
        assert any("ns_warn_node" in r.getMessage() for r in warnings)
        spec = registry.spec("ns_warn_node", owner=OWNER_A)
        assert [p["id"] for p in spec.inputs] == ["b"]


# ---------------------------------------------------------------------------
# 跨空间兜底：owner=None 全局未命中时跨空间查找
# ---------------------------------------------------------------------------

class TestCrossNamespaceFallback:
    """owner=None 查询在全局未命中时跨空间兜底，多命中记 WARNING。"""

    def test_fallback_returns_first_hit_and_warns(self, registry, caplog):
        """多命中时按注册顺序返回首个（A 先注册）并记 WARNING。"""
        _register_load_image_pair()
        with caplog.at_level(logging.WARNING, logger=_REGISTRY_LOGGER):
            spec = registry.spec("load_image")
        assert spec is not None
        assert spec.type_name == "load_image"
        assert spec.owner == OWNER_A
        warnings = _registry_warnings(caplog)
        assert any("load_image" in r.getMessage() for r in warnings)

    def test_fallback_single_hit_no_warning(self, registry, caplog):
        """唯一命中时直接返回且不记 WARNING。"""
        register_node_type(
            "ns_unique_node", "唯一节点", "测试", owner=OWNER_A,
            outputs=[{"id": "out", "data_type": "any"}])
        with caplog.at_level(logging.WARNING, logger=_REGISTRY_LOGGER):
            spec = registry.spec("ns_unique_node")
        assert spec is not None and spec.owner == OWNER_A
        assert not _registry_warnings(caplog)


# ---------------------------------------------------------------------------
# body_builder 按 owner 解析
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestBodyBuilder:
    """owner 画布上节点体区按该 owner 的 body_builder 定义构建。"""

    def test_body_builder_resolved_per_owner(self, registry, qapp, uikit_theme):
        """A 画布节点体区内容为 owner A 的 body_builder 产物。"""

        def build_a(node, container):
            """注入带对象名的标记标签，供断言体区构建者身份。"""
            label = QLabel("A 的节点体", container)
            label.setObjectName("ns_body_marker_a")
            container.layout().addWidget(label)

        register_node_type(
            "ns_body_node", "体节点", "测试", owner=OWNER_A,
            outputs=[{"id": "out", "data_type": "any"}],
            body_builder=build_a)
        canvas = BlueprintCanvas(BlueprintGraph(), owner=OWNER_A)
        node = canvas.add_node_at("ns_body_node", QPointF(0, 0))
        widget = canvas.node_widget(node.id)
        assert widget is not None and widget._body is not None
        marker = widget._body.findChild(QLabel, "ns_body_marker_a")
        assert marker is not None
        canvas.deleteLater()
        qapp.processEvents()


# ---------------------------------------------------------------------------
# 序列化往返
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestSerialization:
    """owner 画布序列化往返后节点引脚保持 owner 定义。"""

    def test_roundtrip_preserves_owner_pins(self, registry, qapp, uikit_theme):
        """to_dict / from_dict 往返后节点数量一致、引脚为 A 的定义、Widget 重建。"""
        _register_load_image_pair()
        canvas = BlueprintCanvas(BlueprintGraph(), owner=OWNER_A)
        node = canvas.add_node_at("load_image", QPointF(20, 30))
        data = canvas.to_dict()
        assert _pin_ids(node.outputs) == ["img"]

        canvas2 = BlueprintCanvas(BlueprintGraph(), owner=OWNER_A)
        canvas2.from_dict(data)
        nodes = canvas2.graph.nodes()
        assert len(nodes) == 1
        assert _pin_ids(nodes[0].outputs) == ["img"]
        assert canvas2.node_widget(nodes[0].id) is not None
        canvas.deleteLater()
        canvas2.deleteLater()
        qapp.processEvents()
