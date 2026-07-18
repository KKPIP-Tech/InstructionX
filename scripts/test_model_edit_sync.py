#!/usr/bin/env python3
r"""验证编辑模型（模型类型/能力标签）后，Model List 同步显示修改.

用法:
    .venv\Scripts\python.exe scripts\test_model_edit_sync.py
"""
import os
import sys
import time
from pathlib import Path

project_root = Path(__file__).parent.parent
os.chdir(project_root)
sys.path.insert(0, str(project_root))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def get_first_model_item(dialog):
    """获取模型列表中第一个 ModelItemWidget."""
    if not dialog._model_groups_layout or dialog._model_groups_layout.count() == 0:
        return None
    group = dialog._model_groups_layout.itemAt(0).widget()
    if not hasattr(group, '_content'):
        return None
    content_layout = group._content.layout()
    for i in range(content_layout.count()):
        w = content_layout.itemAt(i).widget()
        if hasattr(w, '_model') and hasattr(w, 'editClicked'):
            return w
    return None


CAP_NAMES = ('vision', 'web', 'reasoning', 'tools', 'rerank', 'embedding', 'chat')


def get_tag_texts(item_widget):
    """获取模型项上显示的能力标签文本."""
    from PySide6.QtWidgets import QLabel
    return [
        child.text() for child in item_widget.findChildren(QLabel)
        if child.text() in CAP_NAMES
    ]


def main():
    from PySide6.QtWidgets import QApplication

    app = QApplication([])

    from utils.style_qss import set_style_qss_theme
    set_style_qss_theme(app, "light")

    from ui.dialog.llm_settings_dialog import LLMSettingsDialog
    dialog = LLMSettingsDialog()
    dialog.resize(1200, 800)
    dialog.show()
    time.sleep(0.5)
    app.processEvents()

    provider_name = dialog._current_provider_name
    print(f"当前 Provider: {provider_name}")

    out_dir = Path("scripts/screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 编辑前：获取第一个模型项及其标签
    item = get_first_model_item(dialog)
    assert item is not None, "未找到模型项"
    model = dict(item._model)
    print(f"编辑前模型: {model['id']}, capabilities={model.get('capabilities')}")
    tags_before = get_tag_texts(item)
    print(f"编辑前标签: {tags_before}")
    dialog.grab().save(str(out_dir / "edit_sync_before.png"))

    # 模拟编辑对话框保存：修改能力标签为 vision + reasoning
    new_caps = ['vision', 'reasoning']
    model_data = {
        'id': model['id'],
        'name': model.get('name', model['id']),
        'group': model.get('group', ''),
        'capabilities': new_caps,
        'support_streaming': True,
        'currency': '$',
        'input_price_per_1m': 0.0,
        'output_price_per_1m': 0.0,
    }
    dialog._update_model_data(provider_name, model['id'], model_data)
    dialog._populate_model_groups(
        provider_name, dialog._llm_config.get_provider(provider_name)
    )
    app.processEvents()

    # 编辑后：重新获取同一个模型项
    item_after = None
    for gi in range(dialog._model_groups_layout.count()):
        group = dialog._model_groups_layout.itemAt(gi).widget()
        if not hasattr(group, '_content'):
            continue
        content_layout = group._content.layout()
        for i in range(content_layout.count()):
            w = content_layout.itemAt(i).widget()
            if hasattr(w, '_model') and w._model.get('id') == model['id']:
                item_after = w
                break

    assert item_after is not None, f"编辑后未找到模型 {model['id']}"
    print(f"编辑后模型: {item_after._model['id']}, capabilities={item_after._model.get('capabilities')}")
    tags_after = get_tag_texts(item_after)
    print(f"编辑后标签: {tags_after}")
    dialog.grab().save(str(out_dir / "edit_sync_after.png"))

    # 验证
    assert item_after._model.get('capabilities') == new_caps, \
        f"capabilities 未同步: {item_after._model.get('capabilities')} != {new_caps}"
    assert sorted(tags_after) == sorted(new_caps), \
        f"界面标签未同步: {tags_after} != {new_caps}"

    # 恢复原始数据，避免污染用户配置
    config = dialog._llm_config.get_provider(provider_name)
    config.extra['custom_models'] = [
        m for m in config.extra.get('custom_models', [])
        if m.get('id') != model['id']
    ]
    dialog._llm_config.add_provider(provider_name, config)
    dialog._populate_model_groups(provider_name, config)
    app.processEvents()

    print("\n✅ 测试通过：编辑模型类型后 Model List 已同步显示")
    return 0


if __name__ == "__main__":
    sys.exit(main())
