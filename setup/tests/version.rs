use std::process::Command;

use instructionx_setup::version::{SETUP_VERSION, setup_build_version};

fn setup_command() -> Command {
    Command::new(env!("CARGO_BIN_EXE_instructionx-setup"))
}

#[test]
fn setup_version_uses_date_and_daily_package_sequence() {
    let (date, sequence) = SETUP_VERSION.split_once('-').unwrap();
    assert_eq!(date.len(), 8);
    assert!(date.bytes().all(|byte| byte.is_ascii_digit()));
    assert_eq!(sequence.len(), 2);
    assert!(sequence.bytes().all(|byte| byte.is_ascii_digit()));
    assert!(sequence.parse::<u8>().unwrap() >= 1);
}

#[test]
fn build_version_includes_target_platform_and_architecture() {
    let build_version = setup_build_version();
    let suffix = build_version
        .strip_prefix(&format!("{SETUP_VERSION}."))
        .unwrap();
    assert_eq!(suffix.split('.').count(), 2);
    #[cfg(all(windows, target_arch = "x86_64"))]
    assert_eq!(build_version, format!("{SETUP_VERSION}.win.x86_64"));
    #[cfg(all(windows, target_arch = "aarch64"))]
    assert_eq!(build_version, format!("{SETUP_VERSION}.win.aarch64"));
}

#[test]
fn version_option_reports_the_full_build_version() {
    for flag in ["--version", "-V"] {
        let output = setup_command().arg(flag).output().unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8(output.stdout).unwrap();
        assert_eq!(
            stdout.trim(),
            format!("instructionx-setup {}", setup_build_version())
        );
    }
}

#[test]
fn interactive_header_displays_version_without_bios_label() {
    let directory = tempfile::tempdir().unwrap();
    let output = setup_command()
        .args(["--preview", "overview", "--lang", "en", "--project-root"])
        .arg(directory.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8(output.stdout).unwrap();
    assert!(stdout.contains(&setup_build_version()));
    assert!(!stdout.contains("BIOS"));
}

#[test]
fn state_output_includes_the_full_build_version() {
    let directory = tempfile::tempdir().unwrap();
    let output = setup_command()
        .arg("--state")
        .arg("--project-root")
        .arg(directory.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8(output.stdout).unwrap();
    assert!(stdout.contains(&format!("setup_version={}", setup_build_version())));
}
