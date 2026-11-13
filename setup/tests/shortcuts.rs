use std::path::PathBuf;

use instructionx_setup::shortcuts::ShortcutManager;

#[test]
fn launcher_uses_uv_and_never_opens_a_terminal() {
    let manager = ShortcutManager::new(
        PathBuf::from("C:/InstructionX"),
        PathBuf::from("C:/Tools/uv.exe"),
    );
    let launcher = manager.launcher_text();

    assert!(launcher.contains("run --frozen"));
    assert!(launcher.contains("main.py"));
    assert!(!manager.shortcut_path().as_os_str().is_empty());
    if cfg!(windows) {
        assert!(launcher.contains("pythonw"));
        assert!(launcher.contains(", 0, False"));
    } else if cfg!(target_os = "macos") {
        assert!(launcher.contains("python main.py"));
    } else {
        assert!(launcher.contains("Terminal=false"));
        assert!(launcher.contains("ui/logo.png"));
    }
}

#[test]
fn dry_run_does_not_create_launcher_files() {
    let directory = tempfile::tempdir().unwrap();
    let manager = ShortcutManager::new(directory.path().to_path_buf(), PathBuf::from("uv"));

    let path = manager.create(true).unwrap();

    assert_eq!(path, manager.shortcut_path());
    assert!(!directory.path().join(".tui/launchers").exists());
}
