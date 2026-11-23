use crossterm::event::KeyCode;
use instructionx_setup::app::{App, Page};
use instructionx_setup::i18n::{Language, Preferences};
use instructionx_setup::workspace::Workspace;

#[test]
fn every_page_has_visible_actions_instead_of_hidden_c_shortcut() {
    let directory = tempfile::tempdir().unwrap();
    let workspace = Workspace::new(directory.path());

    assert!(
        workspace
            .render(Page::Install)
            .contains("Install InstructionX")
    );
    assert!(
        workspace
            .render(Page::Install)
            .contains("Repair InstructionX")
    );
    assert!(
        workspace
            .render(Page::Install)
            .contains("Check GitHub Releases")
    );
    assert!(
        workspace
            .render(Page::Environment)
            .contains("Query package list")
    );
    assert!(
        workspace
            .render(Page::Upgrade)
            .contains("Check for updates")
    );
    assert!(
        workspace
            .render(Page::Plugins)
            .contains("Refresh plugin list")
    );
    assert!(
        workspace
            .render(Page::Misc)
            .contains("Create desktop shortcut")
    );
    assert!(workspace.render(Page::Misc).contains("TUI language"));
}

#[test]
fn enter_selects_named_action_without_needing_c() {
    let directory = tempfile::tempdir().unwrap();
    let mut workspace = Workspace::new(directory.path());

    workspace.handle_key(Page::Upgrade, KeyCode::Enter).unwrap();
    assert_eq!(workspace.pending_action_name(), Some("CheckUpdates"));

    workspace.reset_region();
    workspace
        .handle_key(Page::Environment, KeyCode::Enter)
        .unwrap();
    assert_eq!(workspace.pending_action_name(), Some("QueryPackages"));

    workspace.reset_region();
    workspace.handle_key(Page::Plugins, KeyCode::Enter).unwrap();
    assert_eq!(workspace.pending_action_name(), Some("RefreshPlugins"));
}

#[test]
fn tab_moves_from_actions_to_data_and_arrows_select_data() {
    let directory = tempfile::tempdir().unwrap();
    let mut app = App::new(
        Preferences {
            language: Language::English,
            needs_language_selection: false,
        },
        directory.path().join(".tui/preferences.toml"),
    );
    app.workspace.set_release_catalog(
        instructionx_setup::github::ReleaseCatalog::from_api(
            vec![
                serde_json::json!({"id":1,"name":"A","tag_name":"alpha-v1.1.2","published_at":"2026-01-01T00:00:00Z"}),
                serde_json::json!({"id":2,"name":"B","tag_name":"alpha-v1.2.0","published_at":"2026-01-02T00:00:00Z"}),
            ],
            instructionx_setup::github::FrameworkVersion::parse("alpha-v1.1.2").unwrap(),
        ),
    );
    app.page = Page::Upgrade;
    app.handle_key(KeyCode::Right).unwrap();

    app.handle_key(KeyCode::Tab).unwrap();
    app.handle_key(KeyCode::Down).unwrap();

    assert_eq!(app.workspace.release_index, 1);
    assert!(!app.workspace.has_pending_action());
}

#[test]
fn misc_language_is_an_independent_executable_option() {
    let directory = tempfile::tempdir().unwrap();
    let mut app = App::new(
        Preferences {
            language: Language::English,
            needs_language_selection: false,
        },
        directory.path().join(".tui/preferences.toml"),
    );
    app.page = Page::Misc;
    app.handle_key(KeyCode::Right).unwrap();
    app.handle_key(KeyCode::Down).unwrap();

    app.handle_key(KeyCode::Enter).unwrap();
    app.handle_key(KeyCode::Enter).unwrap();

    assert!(
        app.render_text(100, 20)
            .unwrap()
            .contains("Select interface language")
    );
}
