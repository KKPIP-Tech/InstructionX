use instructionx_setup::cli::normalize_legacy_args;
use instructionx_setup::workspace::Workspace;

#[test]
fn legacy_windows_arguments_are_normalized() {
    let normalized = normalize_legacy_args([
        "setup".to_string(),
        "-Action".to_string(),
        "upgrade".to_string(),
        "-ReleaseTag".to_string(),
        "alpha-v1.2.0".to_string(),
        "-DryRun".to_string(),
    ]);

    assert_eq!(
        normalized,
        [
            "setup",
            "--action",
            "upgrade",
            "--release-tag",
            "alpha-v1.2.0",
            "--dry-run",
        ]
    );
}

#[test]
fn dry_run_does_not_download_or_create_directories() {
    let directory = tempfile::tempdir().unwrap();
    let mut workspace = Workspace::new(directory.path());

    let message = workspace
        .run_action("upgrade", None, Some("alpha-v9.9.9"), true, false)
        .unwrap();

    assert!(message.contains("alpha-v9.9.9"));
    assert!(!directory.path().join(".tui").exists());
}
