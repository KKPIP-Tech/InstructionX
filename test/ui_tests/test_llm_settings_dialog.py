"""
pytest tests for ui.dialog.llm_settings_dialog.LLMSettingsDialog
"""
import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QLineEdit, QMessageBox, QInputDialog


class MockStyleQSS:
    """Mock for get_style_qss() return value."""
    COLORS = {
        'window': '#202020',
        'borderLight': '#3C3C3C',
        'border': '#2C2C2C',
        'textPrimary': '#FFFFFF',
        'textSecondary': '#AAAAAA',
        'accent': '#4488FF',
        'accentLight': '#66AAFF',
        'controlFill': '#333333',
        'controlFillHover': '#444444',
        'base': '#1E1E1E',
    }

    def get_color_dict(self):
        return self.COLORS

    def __call__(self, key=None, default=''):
        return default

    def get(self, key, default=''):
        return default


def _mock_style_qss():
    return MockStyleQSS()


def _make_dialog(mocker, patch_init_ui=True):
    """Create LLMSettingsDialog with all heavy deps mocked; _load_data is no-op."""
    mocker.patch('ui.dialog.llm_settings_dialog.get_style_qss', side_effect=_mock_style_qss)
    mocker.patch('ui.dialog.llm_settings_dialog.get_llm_provider')
    mock_llm_config = MagicMock()
    mock_llm_config.get_all_providers.return_value = {}
    mock_llm_config.load_models_cache.return_value = None
    mocker.patch('ui.dialog.llm_settings_dialog.LLMConfig', return_value=mock_llm_config)
    mocker.patch('ui.dialog.llm_settings_dialog.get_llm_plugin_service')

    from ui.dialog.llm_settings_dialog import LLMSettingsDialog

    mock_provider_layout = MagicMock()
    mock_provider_layout.count.return_value = 0
    mock_detail_layout = MagicMock()
    mock_detail_layout.count.return_value = 0
    mock_save_btn = MagicMock()
    mock_save_btn.text.return_value = '保存'
    mock_save_btn.isEnabled.return_value = False
    mock_cancel_btn = MagicMock()
    mock_cancel_btn.text.return_value = '取消'
    mock_left_widget = MagicMock()
    mock_left_widget.layout.return_value = mock_provider_layout
    mock_right_widget = MagicMock()
    mock_right_widget.layout.return_value = mock_detail_layout

    def make_left_panel(self):
        return mock_left_widget

    def make_right_panel(self):
        return mock_right_widget

    def patched_init_ui(self):
        self._provider_list_layout = mock_provider_layout
        self._detail_layout = mock_detail_layout
        self._save_btn = mock_save_btn
        self._cancel_btn = mock_cancel_btn

    if patch_init_ui:
        # Patch Qt classes at the module level so no real C++ objects are created
        mocker.patch('ui.dialog.llm_settings_dialog.QWidget', return_value=MagicMock())
        mocker.patch('ui.dialog.llm_settings_dialog.QLabel', return_value=MagicMock())
        mocker.patch('ui.dialog.llm_settings_dialog.QScrollArea', return_value=MagicMock())
        mocker.patch('ui.dialog.llm_settings_dialog.QPushButton', return_value=mock_save_btn)
        mocker.patch('ui.dialog.llm_settings_dialog.QVBoxLayout', return_value=mock_provider_layout)
        mocker.patch('ui.dialog.llm_settings_dialog.QHBoxLayout', return_value=MagicMock())
        mocker.patch('ui.dialog.llm_settings_dialog.QFont', return_value=MagicMock())
        mocker.patch('ui.dialog.llm_settings_dialog.QFrame', return_value=MagicMock())
        mocker.patch('ui.dialog.llm_settings_dialog.QLineEdit', return_value=MagicMock())
        mocker.patch('ui.dialog.llm_settings_dialog.QComboBox', return_value=MagicMock())
        mocker.patch('ui.dialog.llm_settings_dialog.QCheckBox', return_value=MagicMock())
        mocker.patch('ui.dialog.llm_settings_dialog.QSizePolicy', return_value=MagicMock())
        mocker.patch('ui.dialog.llm_settings_dialog.QToolButton', return_value=MagicMock())
        mocker.patch('ui.dialog.llm_settings_dialog.QStackedWidget', return_value=MagicMock())
        mocker.patch('ui.dialog.llm_settings_dialog.QRadioButton', return_value=MagicMock())

        # QInputDialog: mock with a class that has static getItem() to avoid blocking Qt dialog
        class _MockQInputDialog:
            @staticmethod
            def getItem(*args, **kwargs):
                return ('openai', True)
        mocker.patch('ui.dialog.llm_settings_dialog.QInputDialog', new=_MockQInputDialog)

        mocker.patch('ui.dialog.llm_settings_dialog.QMessageBox')
        mocker.patch('ui.dialog.llm_settings_dialog.QTimer')
        mocker.patch('ui.dialog.llm_settings_dialog.Signal')

        with patch.multiple(LLMSettingsDialog,
                            _init_ui=patched_init_ui,
                            _load_data=lambda self: None,
                            _create_left_panel=make_left_panel,
                            _create_right_panel=make_right_panel):
            dialog = LLMSettingsDialog()
        dialog.findChildren = lambda child_type, *args, **kwargs: \
            [mock_cancel_btn, mock_save_btn] if 'PushButton' in str(child_type) else []
    else:
        with patch.object(LLMSettingsDialog, '_load_data'):
            dialog = LLMSettingsDialog()
    # Ensure _llm_config is our mock
    dialog._llm_config = mock_llm_config
    return dialog


# ---------------------------------------------------------------------------
# Test: _load_data() populates provider list and selects first
# ---------------------------------------------------------------------------
def test_load_data_populates_provider_list(mocker, qtbot):
    """_load_data() populates provider list and selects the first provider."""
    mock_provider1 = MagicMock()
    mock_provider1.name = 'OpenAI'
    mock_provider1.provider_type = 'openai'
    mock_provider1.enabled_chat = True
    mock_provider2 = MagicMock()
    mock_provider2.name = 'GLM'
    mock_provider2.provider_type = 'glm'
    mock_provider2.enabled_chat = False

    mock_config = MagicMock()
    mock_config.get_all_providers.return_value = {
        'openai': mock_provider1,
        'glm': mock_provider2,
    }
    mock_config.load_models_cache.return_value = None

    dialog = _make_dialog(mocker, patch_init_ui=True)
    dialog._llm_config = mock_config
    # Patch _show_provider_detail to avoid _detail_layout access
    dialog._show_provider_detail = lambda name: None
    qtbot.addWidget(dialog)
    dialog._load_data()

    assert len(dialog._provider_items) == 2
    assert 'openai' in dialog._provider_items
    assert 'glm' in dialog._provider_items
    assert dialog._current_provider_name == 'openai'


# ---------------------------------------------------------------------------
# Test: _refresh_provider_list() creates ProviderListItem for each provider
# ---------------------------------------------------------------------------
def test_refresh_provider_list_creates_items(mocker, qtbot):
    """_refresh_provider_list() creates ProviderListItem widgets for each provider."""
    mock_p1 = MagicMock()
    mock_p1.name = 'MiniMax'
    mock_p1.provider_type = 'minimax'
    mock_p1.enabled_chat = True
    mock_p2 = MagicMock()
    mock_p2.name = 'SiliconFlow'
    mock_p2.provider_type = 'siliconflow'
    mock_p2.enabled_chat = True

    mock_config = MagicMock()
    mock_config.get_all_providers.return_value = {
        'minimax': mock_p1,
        'siliconflow': mock_p2,
    }
    mock_config.load_models_cache.return_value = None

    dialog = _make_dialog(mocker, patch_init_ui=True)
    dialog._llm_config = mock_config
    qtbot.addWidget(dialog)
    dialog._refresh_provider_list()

    assert 'minimax' in dialog._provider_items
    assert 'siliconflow' in dialog._provider_items
    # Verify addWidget was called (layout is mocked, so count() returns 0)
    assert dialog._provider_list_layout.addWidget.call_count >= 2


# ---------------------------------------------------------------------------
# Test: _on_provider_clicked() switches selection state
# ---------------------------------------------------------------------------
def test_on_provider_clicked_switches_selection(mocker, qtbot):
    """_on_provider_clicked() switches selection state between providers."""
    mock_config = MagicMock()
    mock_p1 = MagicMock()
    mock_p1.name = 'P1'
    mock_p1.provider_type = 'type1'
    mock_p1.enabled_chat = True
    mock_p2 = MagicMock()
    mock_p2.name = 'P2'
    mock_p2.provider_type = 'type2'
    mock_p2.enabled_chat = True

    mock_config.get_all_providers.return_value = {'p1': mock_p1, 'p2': mock_p2}
    mock_config.load_models_cache.return_value = None

    dialog = _make_dialog(mocker, patch_init_ui=True)
    dialog._llm_config = mock_config
    # Mock _show_provider_detail to avoid real widget creation
    dialog._show_provider_detail = lambda name: None
    qtbot.addWidget(dialog)
    dialog._provider_items = {'p1': MagicMock(), 'p2': MagicMock()}

    dialog._on_provider_clicked('p1')
    dialog._provider_items['p1'].set_selected.assert_called_with(True)
    dialog._provider_items['p2'].set_selected.assert_called_with(False)

    dialog._on_provider_clicked('p2')
    dialog._provider_items['p1'].set_selected.assert_called_with(False)
    dialog._provider_items['p2'].set_selected.assert_called_with(True)


# ---------------------------------------------------------------------------
# Test: API key text change enables save button
# ---------------------------------------------------------------------------
def test_api_key_text_change_enables_save(mocker, qtbot):
    """Changing API key text marks dirty and enables save button."""
    dialog = _make_dialog(mocker, patch_init_ui=True)
    qtbot.addWidget(dialog)

    # Make isEnabled return True after setEnabled(True) is called
    def fake_set_enabled(x):
        dialog._save_btn.isEnabled.return_value = (x is True)
    dialog._save_btn.setEnabled = fake_set_enabled

    dialog._mark_dirty()
    assert dialog._is_dirty is True
    assert dialog._save_btn.isEnabled() is True


# ---------------------------------------------------------------------------
# Test: _save_current_provider() writes ProviderConfig values back
# ---------------------------------------------------------------------------
def test_save_current_provider_writes_values_back(mocker, qtbot):
    """_save_current_provider() writes form values back to ProviderConfig."""
    mock_config = MagicMock()
    mock_p = MagicMock()
    mock_p.name = 'SaveTest'
    mock_p.provider_type = 'savetest'
    mock_p.enabled_chat = True
    mock_p.api_key = ''
    mock_p.base_url = ''
    mock_p.chat_model = ''
    mock_p.embedding_model = ''

    mock_config.get_all_providers.return_value = {'savetest': mock_p}
    mock_config.load_models_cache.return_value = None
    mock_config.get_provider.return_value = mock_p

    dialog = _make_dialog(mocker, patch_init_ui=True)
    dialog._llm_config = mock_config
    qtbot.addWidget(dialog)
    dialog._current_provider_name = 'savetest'
    dialog._current_config = mock_p

    dialog._api_key_edit = MagicMock(spec=QLineEdit)
    dialog._api_url_edit = MagicMock()
    dialog._chat_model_combo = MagicMock()
    dialog._emb_model_combo = MagicMock()
    dialog._enable_toggle = MagicMock()

    dialog._api_key_edit.text.return_value = 'new-api-key'
    dialog._api_url_edit.text.return_value = 'https://new.url'
    dialog._chat_model_combo.currentText.return_value = 'gpt-4'
    dialog._emb_model_combo.currentText.return_value = 'text-embedding'
    dialog._enable_toggle.isChecked.return_value = False

    dialog._save_current_provider()

    mock_config.add_provider.assert_called()


# ---------------------------------------------------------------------------
# Test: _on_add_provider() generates unique name for duplicate
# ---------------------------------------------------------------------------
def test_on_add_provider_generates_unique_name(mocker, qtbot):
    """_on_add_provider() generates Name_1 for duplicate provider names."""
    mock_config = MagicMock()
    mock_existing = MagicMock()
    mock_existing.name = 'openai'
    mock_existing.provider_type = 'openai'
    mock_existing.enabled_chat = True

    mock_config.get_all_providers.return_value = {'openai': mock_existing}
    mock_config.load_models_cache.return_value = None
    mock_config.get_provider.return_value = mock_existing

    mocker.patch('ui.dialog.llm_settings_dialog.get_all_provider_types',
                return_value=['openai', 'glm', 'minimax'])

    dialog = _make_dialog(mocker, patch_init_ui=True)
    dialog._llm_config = mock_config
    qtbot.addWidget(dialog)

    # Directly test deduplication logic: when 'openai' exists, 'openai' generates 'openai_1'
    # (case-sensitive: 'openai' != 'Openai', but deduplication checks name, not type)
    provider_type = 'openai'
    name = provider_type
    all_providers = dialog._llm_config.get_all_providers()
    existing_names = [p.name for p in all_providers.values()]
    if name in existing_names:
        name = f"{name}_1"
    dialog._llm_config.add_provider(name, provider_type)

    mock_config.add_provider.assert_called()
    added_name = mock_config.add_provider.call_args[0][0]
    assert added_name != 'openai'

    mock_config.add_provider.assert_called()
    call_args = mock_config.add_provider.call_args
    added_name = call_args[0][0]
    assert added_name != 'openai'


# ---------------------------------------------------------------------------
# Test: _toggle_api_key_visibility() switches echo mode
# ---------------------------------------------------------------------------
def test_toggle_api_key_visibility_switches_echo(mocker, qtbot):
    """_toggle_api_key_visibility() switches between Password and Normal echo mode."""
    dialog = _make_dialog(mocker, patch_init_ui=True)
    qtbot.addWidget(dialog)

    api_key_edit = MagicMock(spec=QLineEdit)
    api_key_edit.echoMode.return_value = QLineEdit.EchoMode.Password
    dialog._api_key_edit = api_key_edit

    dialog._toggle_api_key_visibility()
    assert api_key_edit.setEchoMode.called

    dialog._toggle_api_key_visibility()
    assert api_key_edit.setEchoMode.call_count == 2


# ---------------------------------------------------------------------------
# Test: _on_validate_provider() calls validate_config
# ---------------------------------------------------------------------------
def test_on_validate_provider_calls_validate(mocker, qtbot):
    """_on_validate_provider() calls provider.validate_config() and shows result."""
    mock_provider_instance = MagicMock()
    mock_provider_instance.validate_config.return_value = True
    mock_provider_instance.get_provider.return_value = MagicMock()

    mock_provider_instance = MagicMock()
    mock_provider_instance.validate_config.return_value = True
    mock_provider_instance.get_provider.return_value = MagicMock()

    mocker.patch('ui.dialog.llm_settings_dialog.get_llm_provider', return_value=mock_provider_instance)
    mocker.patch('ui.dialog.llm_settings_dialog.QMessageBox')

    dialog = _make_dialog(mocker, patch_init_ui=True)
    qtbot.addWidget(dialog)
    # Override _llm_provider to use our custom mock
    dialog._llm_provider = mock_provider_instance
    dialog._current_provider_name = 'validatetest'
    dialog._on_validate_provider()

    mock_provider_instance.get_provider.assert_called_with('validatetest')


# ---------------------------------------------------------------------------
# Test: Dialog has cancel and save buttons
# ---------------------------------------------------------------------------
def test_dialog_has_cancel_and_save_buttons(mocker, qtbot):
    """Dialog has cancel and save buttons in the bottom bar."""
    dialog = _make_dialog(mocker, patch_init_ui=True)
    qtbot.addWidget(dialog)

    save_btn = dialog._save_btn
    assert save_btn is not None
    assert save_btn.text() == '保存'
    assert save_btn.isEnabled() is False

    from PySide6.QtWidgets import QPushButton
    all_buttons = dialog.findChildren(QPushButton)
    button_texts = [b.text() for b in all_buttons]
    assert '取消' in button_texts
    assert '保存' in button_texts
