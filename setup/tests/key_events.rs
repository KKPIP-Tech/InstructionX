use crossterm::event::{KeyCode, KeyEvent, KeyEventKind, KeyModifiers};
use instructionx_setup::app::{App, Page};
use instructionx_setup::i18n::{Language, Preferences};

fn app() -> App {
    let directory = tempfile::tempdir().unwrap();
    App::new(
        Preferences {
            language: Language::English,
            needs_language_selection: false,
        },
        directory.path().join(".tui/preferences.toml"),
    )
}

fn release(code: KeyCode) -> KeyEvent {
    KeyEvent::new_with_kind(code, KeyModifiers::empty(), KeyEventKind::Release)
}

#[test]
fn menu_supports_arrows_and_release_does_not_move_twice() {
    let mut app = app();
    assert_eq!(app.page, Page::Overview);

    app.handle_key_event(KeyEvent::from(KeyCode::Down)).unwrap();
    app.handle_key_event(release(KeyCode::Down)).unwrap();
    assert_eq!(app.page, Page::Install);

    app.handle_key_event(KeyEvent::from(KeyCode::Up)).unwrap();
    app.handle_key_event(release(KeyCode::Up)).unwrap();
    assert_eq!(app.page, Page::Overview);
}

#[test]
fn release_event_does_not_select_two_items() {
    let mut app = app();
    app.page = Page::Install;
    app.handle_key(KeyCode::Right).unwrap();

    app.handle_key_event(KeyEvent::from(KeyCode::Down)).unwrap();
    app.handle_key_event(release(KeyCode::Down)).unwrap();

    assert_eq!(app.workspace.action_index, 1);
}

#[test]
fn enter_release_does_not_execute_pending_action() {
    let mut app = app();
    app.page = Page::Install;
    app.handle_key(KeyCode::Right).unwrap();

    app.handle_key_event(KeyEvent::from(KeyCode::Enter))
        .unwrap();
    app.handle_key_event(release(KeyCode::Enter)).unwrap();

    assert!(app.workspace.has_pending_action());
}
