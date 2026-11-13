use std::collections::VecDeque;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use instructionx_setup::uv::{CommandOutput, CommandRunner, UvClient, uv_asset_name};

type Calls = Arc<Mutex<Vec<(String, Vec<String>)>>>;

#[derive(Clone)]
struct MockRunner {
    outputs: Arc<Mutex<VecDeque<CommandOutput>>>,
    calls: Calls,
}

impl MockRunner {
    fn new(outputs: Vec<CommandOutput>) -> Self {
        Self {
            outputs: Arc::new(Mutex::new(outputs.into())),
            calls: Arc::new(Mutex::new(Vec::new())),
        }
    }
}

impl CommandRunner for MockRunner {
    fn run(&self, program: &str, args: &[String], _root: &Path) -> std::io::Result<CommandOutput> {
        self.calls
            .lock()
            .unwrap()
            .push((program.to_string(), args.to_vec()));
        self.outputs
            .lock()
            .unwrap()
            .pop_front()
            .ok_or_else(|| std::io::Error::new(std::io::ErrorKind::UnexpectedEof, "no output"))
    }
}

fn output(code: i32, stdout: &str) -> CommandOutput {
    CommandOutput {
        code,
        stdout: stdout.to_string(),
        stderr: String::new(),
    }
}

fn client(runner: MockRunner) -> UvClient {
    UvClient::with_runner(PathBuf::from("uv"), Box::new(runner), PathBuf::from("."))
}

#[test]
fn combines_installed_and_latest_package_versions() {
    let runner = MockRunner::new(vec![
        output(0, r#"[{"name":"requests","version":"2.31.0"}]"#),
        output(
            0,
            r#"[{"name":"requests","version":"2.31.0","latest_version":"2.32.0"}]"#,
        ),
    ]);
    let uv = client(runner);

    let packages = uv.list_packages().unwrap();

    assert_eq!(packages.len(), 1);
    assert_eq!(packages[0].version, "2.31.0");
    assert_eq!(packages[0].latest_version.as_deref(), Some("2.32.0"));
}

#[test]
fn update_and_remove_use_explicit_package_names() {
    let runner = MockRunner::new(vec![output(0, ""), output(0, "")]);
    let calls = runner.calls.clone();
    let mut uv = client(runner);

    uv.update_packages(&["requests".to_string()]).unwrap();
    uv.remove_packages(&["demo".to_string()]).unwrap();

    let calls = calls.lock().unwrap();
    assert!(calls[0].1.contains(&"--upgrade-package".to_string()));
    assert!(calls[0].1.contains(&"requests".to_string()));
    assert!(calls[1].1.contains(&"uninstall".to_string()));
    assert!(calls[1].1.contains(&"demo".to_string()));
}

#[test]
fn environment_sync_falls_back_to_requirements() {
    let runner = MockRunner::new(vec![output(1, ""), output(0, "")]);
    let calls = runner.calls.clone();
    let mut uv = client(runner);

    uv.sync_environment().unwrap();

    let calls = calls.lock().unwrap();
    assert!(calls[0].1.contains(&"sync".to_string()));
    assert!(calls[1].1.contains(&"requirements.txt".to_string()));
}

#[test]
fn uv_assets_cover_windows_macos_and_linux() {
    assert_eq!(
        uv_asset_name("windows", "x86_64").unwrap(),
        "uv-x86_64-pc-windows-msvc.zip"
    );
    assert_eq!(
        uv_asset_name("macos", "aarch64").unwrap(),
        "uv-aarch64-apple-darwin.tar.gz"
    );
    assert_eq!(
        uv_asset_name("linux", "x86_64").unwrap(),
        "uv-x86_64-unknown-linux-gnu.tar.gz"
    );
}
