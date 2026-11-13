use crossterm::event::KeyCode;
use instructionx_setup::app::{App, Page};
use instructionx_setup::i18n::{Language, Preferences};

#[test]
fn first_launch_renders_language_selection_before_overview() {
    let directory = tempfile::tempdir().unwrap();
    let app = App::new(
        Preferences::default(),
        directory.path().join("preferences.toml"),
    );
    let text = app.render_text(100, 30).unwrap();

    assert!(text.contains("InstructionX Setup"));
    assert!(text.contains("English"));
    assert!(text.replace(' ', "").contains("中文"));
    assert!(text.contains("Français"));
    assert!(text.contains("Русский"));
    assert!(!text.contains("0 Overview"));
}

#[test]
fn confirming_language_saves_preference_and_enters_overview() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("preferences.toml");
    let mut app = App::new(Preferences::default(), path.clone());

    app.handle_key(KeyCode::Enter).unwrap();

    assert!(!app.preferences.needs_language_selection);
    assert_eq!(app.page, Page::Overview);
    assert!(!Preferences::load(&path).unwrap().needs_language_selection);
    let text = app.render_text(100, 30).unwrap();
    assert!(text.contains("0 Overview"));
    assert!(text.contains("1 Install & Repair"));
    assert!(text.contains("2 Environment"));
    assert!(text.contains("3 Upgrade Management"));
    assert!(text.contains("4 Plugins"));
    assert!(text.contains("5 Miscellaneous"));
}

#[test]
fn number_keys_switch_pages_and_q_requests_exit() {
    let directory = tempfile::tempdir().unwrap();
    let mut app = App::new(
        Preferences {
            language: Language::Chinese,
            needs_language_selection: false,
        },
        directory.path().join("preferences.toml"),
    );

    app.handle_key(KeyCode::Char('3')).unwrap();
    assert_eq!(app.page, Page::Upgrade);
    assert!(
        app.render_text(100, 30)
            .unwrap()
            .replace(' ', "")
            .contains("升级管理")
    );
    app.handle_key(KeyCode::Char('q')).unwrap();
    assert!(app.should_quit);
}
