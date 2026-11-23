use instructionx_setup::i18n::{I18n, Language, Preferences};

#[test]
fn english_is_the_default_language() {
    let language = Language::default();
    assert_eq!(language.code(), "en");
    assert_eq!(Language::from_code("invalid"), Language::English);
}

#[test]
fn all_four_languages_have_navigation_translations() {
    for (code, expected) in [
        ("en", "Overview"),
        ("zh", "总览"),
        ("fr", "Vue d’ensemble"),
        ("ru", "Обзор"),
    ] {
        let language = Language::from_code(code);
        let i18n = I18n::new(language);
        assert_eq!(i18n.t("menu.overview"), expected);
        assert_ne!(i18n.t("menu.install"), "");
        assert_ne!(i18n.t("menu.environment"), "");
        assert_ne!(i18n.t("menu.upgrade"), "");
        assert_ne!(i18n.t("menu.plugins"), "");
        assert_ne!(i18n.t("menu.misc"), "");
    }
}

#[test]
fn language_preference_is_saved_and_restored() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("preferences.toml");
    let initial = Preferences::load(&path).unwrap();
    assert!(initial.needs_language_selection);
    assert_eq!(initial.language, Language::English);

    let selected = Preferences {
        language: Language::Russian,
        needs_language_selection: false,
    };
    selected.save(&path).unwrap();
    let restored = Preferences::load(&path).unwrap();
    assert_eq!(restored.language, Language::Russian);
    assert!(!restored.needs_language_selection);
}

#[test]
fn legacy_language_file_is_migrated() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("preferences.toml");
    std::fs::write(directory.path().join("lang"), "ru").unwrap();

    let preferences = Preferences::load(&path).unwrap();

    assert_eq!(preferences.language, Language::Russian);
    assert!(!preferences.needs_language_selection);
}
