# ui/dialog/llm_settings/__init__.py
"""LLM 设置界面包

新版 LLM 设置对话框的实现包，按职责拆分：
- constants.py：界面尺寸/超时等命名常量；
- theme.py：主题 token（LIGHT/DARK）+ QSS 生成 + 对话框作用域换肤；
- icons.py：品牌 SVG 图标渲染/着色（icons/ 资源目录）；
- widgets.py：通用控件（开关/徽章/Provider 列表项/模型行/表单基类）；
- workers.py：后台 Worker 线程（模型拉取/连接检查/健康检查）；
- provider_list_panel.py：左栏 Provider 列表面板；
- model_section.py：详情面板「模型」分区视图（自详情面板拆分）；
- provider_detail_panel.py：右栏 Provider 详情面板（自动保存语义）；
- provider_editor_dialog.py：Provider 实例添加/编辑对话框；
- model_edit_dialog.py：模型条目编辑对话框；
- health_check_dialog.py：模型健康检查对话框（逐模型可用性探测）；
- sync_models_dialog.py：模型同步对话框（远端 ↔ 本地对比管理）；
- dialog.py：LLM 设置主对话框（两栏协调主壳）。
"""

from .dialog import LLMSettingsDialog
from .health_check_dialog import HealthCheckDialog
from .model_edit_dialog import ModelEditDialog
from .sync_models_dialog import SyncModelsDialog
from .provider_detail_panel import ProviderDetailPanel
from .provider_editor_dialog import (
    MODE_CREATE, MODE_EDIT, ProviderEditorDialog, generate_instance_id,
)
from .provider_list_panel import ProviderListPanel
from .theme import DARK, LIGHT, THEMES, Theme, apply_dialog_theme

__all__ = [
    "DARK",
    "LIGHT",
    "MODE_CREATE",
    "MODE_EDIT",
    "THEMES",
    "Theme",
    "HealthCheckDialog",
    "LLMSettingsDialog",
    "ModelEditDialog",
    "SyncModelsDialog",
    "ProviderDetailPanel",
    "ProviderEditorDialog",
    "ProviderListPanel",
    "apply_dialog_theme",
    "generate_instance_id",
]
