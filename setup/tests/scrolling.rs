use crossterm::event::{KeyCode, MouseEventKind};
use instructionx_setup::app::{App, Focus, Page};
use instructionx_setup::github::{FrameworkVersion, ReleaseCatalog};
use instructionx_setup::i18n::{Language, Preferences};

fn app() -> App {
    let directory = tempfile::tempdir().unwrap();
    let root = directory.path().to_path_buf();
    App::new(
        Preferences {
            language: Language::English,
            needs_language_selection: false,
        },
        root.join(".tui/preferences.toml"),
    )
}

fn many_releases() -> ReleaseCatalog {
    let releases = (0..40)
        .map(|id| {
            serde_json::json!({
                "id": id,
                "name": format!("Release {id}"),
                "tag_name": format!("alpha-v1.{id}.0"),
                "published_at": "2026-01-01T00:00:00Z",
                "prerelease": true,
                "draft": false,
                "body": "notes",
                "html_url": "https://example/release"
            })
        })
        .collect();
    ReleaseCatalog::from_api(releases, FrameworkVersion::parse("alpha-v1.1.2").unwrap())
}

#[test]
fn startup_uses_bios_menu_selection_and_right_enters_content() {
    let mut app = app();
    assert_eq!(app.focus, Focus::Navigation);
    assert_eq!(app.page, Page::Overview);

    app.handle_key(KeyCode::Down).unwrap();
    assert_eq!(app.page, Page::Install);
    app.handle_key(KeyCode::Up).unwrap();
    assert_eq!(app.page, Page::Overview);
    app.handle_key(KeyCode::Right).unwrap();
    assert_eq!(app.focus, Focus::Content);
    assert_eq!(app.page, Page::Overview);
}

#[test]
fn list_items_move_highlight_and_auto_scroll_without_shift() {
    let mut app = app();
    app.workspace.set_release_catalog(many_releases());
    app.page = Page::Upgrade;
    app.render_text(80, 20).unwrap();
    app.handle_key(KeyCode::Right).unwrap();
    app.handle_key(KeyCode::Tab).unwrap();

    app.handle_key(KeyCode::Down).unwrap();

    assert_eq!(app.workspace.release_index, 1);
    assert!(app.content_scroll > 0);
    app.handle_key(KeyCode::Left).unwrap();
    assert_eq!(app.focus, Focus::Navigation);
}

#[test]
fn plain_text_up_down_scroll_content() {
    let mut app = app();
    app.render_text(80, 20).unwrap();
    app.handle_key(KeyCode::Right).unwrap();

    app.handle_key(KeyCode::Down).unwrap();
    assert!(app.content_scroll > 0);
    app.handle_key(KeyCode::Up).unwrap();
    assert_eq!(app.content_scroll, 0);
}

#[test]
fn install_page_uses_plain_arrows_for_action_selection() {
    let mut app = app();
    app.page = Page::Install;
    app.handle_key(KeyCode::Right).unwrap();

    app.handle_key(KeyCode::Down).unwrap();

    assert_eq!(app.workspace.action_index, 1);
}

#[test]
fn page_and_mouse_scroll_are_supported() {
    let mut app = app();
    app.handle_key(KeyCode::Right).unwrap();
    app.render_text(80, 20).unwrap();

    app.handle_key(KeyCode::PageDown).unwrap();
    assert!(app.content_scroll > 0);
    let before = app.content_scroll;
    app.handle_mouse(MouseEventKind::ScrollUp);
    assert!(app.content_scroll < before);
    app.handle_key(KeyCode::Home).unwrap();
    assert_eq!(app.content_scroll, 0);
    app.handle_key(KeyCode::End).unwrap();
    assert!(app.content_scroll > 0);
}
