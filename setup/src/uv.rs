use std::error::Error;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::process::Command;

use crate::actions::tool_available;

const UV_DOWNLOAD_BASE_URL: &str = "https://github.com/astral-sh/uv/releases/latest/download";

#[derive(Debug, Clone)]
pub struct CommandOutput {
    pub code: i32,
    pub stdout: String,
    pub stderr: String,
}

pub trait CommandRunner {
    fn run(&self, program: &str, args: &[String], root: &Path) -> io::Result<CommandOutput>;
}

struct ProcessRunner;

impl CommandRunner for ProcessRunner {
    fn run(&self, program: &str, args: &[String], root: &Path) -> io::Result<CommandOutput> {
        let output = Command::new(program)
            .args(args)
            .current_dir(root)
            .output()?;
        Ok(CommandOutput {
            code: output.status.code().unwrap_or(-1),
            stdout: String::from_utf8_lossy(&output.stdout).to_string(),
            stderr: String::from_utf8_lossy(&output.stderr).to_string(),
        })
    }
}

#[derive(Debug, Clone, PartialEq, serde::Deserialize)]
pub struct PackageInfo {
    pub name: String,
    pub version: String,
    pub latest_version: Option<String>,
}

pub struct UvClient {
    program: PathBuf,
    root: PathBuf,
    runner: Box<dyn CommandRunner>,
}

pub fn uv_program(root: &Path) -> PathBuf {
    let name = if cfg!(windows) { "uv.exe" } else { "uv" };
    let local = root.join(".tui/tools").join(name);
    if local.is_file() {
        local
    } else {
        PathBuf::from("uv")
    }
}

impl UvClient {
    pub fn new(root: &Path) -> Self {
        Self::with_runner(
            uv_program(root),
            Box::new(ProcessRunner),
            root.to_path_buf(),
        )
    }

    pub fn program(&self) -> &Path {
        &self.program
    }

    pub fn with_runner(program: PathBuf, runner: Box<dyn CommandRunner>, root: PathBuf) -> Self {
        Self {
            program,
            root,
            runner,
        }
    }

    pub fn list_packages(&self) -> Result<Vec<PackageInfo>, Box<dyn Error>> {
        let installed = self.run_json(&["pip", "list", "--format", "json"])?;
        let outdated = self.run_json(&["pip", "list", "--outdated", "--format", "json"])?;
        let mut packages = installed;
        for package in &mut packages {
            package.latest_version = outdated
                .iter()
                .find(|candidate| candidate.name == package.name)
                .and_then(|candidate| candidate.latest_version.clone());
        }
        Ok(packages)
    }

    pub fn update_packages(&mut self, packages: &[String]) -> Result<(), Box<dyn Error>> {
        for package in packages {
            self.run_checked(&["pip", "install", "--upgrade-package", package])?;
        }
        Ok(())
    }

    pub fn remove_packages(&mut self, packages: &[String]) -> Result<(), Box<dyn Error>> {
        for package in packages {
            self.run_checked(&["pip", "uninstall", package])?;
        }
        Ok(())
    }

    pub fn sync_environment(&mut self) -> Result<(), Box<dyn Error>> {
        let locked = self.run(&["sync", "--locked", "--no-dev", "--no-install-project"])?;
        if locked.code == 0 {
            return Ok(());
        }
        self.run_checked(&["pip", "install", "-r", "requirements.txt"])?;
        Ok(())
    }

    pub fn rebuild_environment(&mut self) -> Result<(), Box<dyn Error>> {
        let environment = self.root.join(".venv");
        if environment.exists() {
            fs::remove_dir_all(environment)?;
        }
        self.sync_environment()
    }

    fn run_json(&self, arguments: &[&str]) -> Result<Vec<PackageInfo>, Box<dyn Error>> {
        let output = self.run_checked(arguments)?;
        Ok(serde_json::from_str(&output.stdout)?)
    }

    fn run_checked(&self, arguments: &[&str]) -> Result<CommandOutput, Box<dyn Error>> {
        let output = self.run(arguments)?;
        if output.code != 0 {
            return Err(format!("uv {} failed: {}", arguments.join(" "), output.stderr).into());
        }
        Ok(output)
    }

    fn run(&self, arguments: &[&str]) -> Result<CommandOutput, Box<dyn Error>> {
        let arguments: Vec<String> = arguments.iter().map(|value| value.to_string()).collect();
        let program = self.program.to_string_lossy().to_string();
        Ok(self.runner.run(&program, &arguments, &self.root)?)
    }
}

pub fn uv_asset_name(os: &str, architecture: &str) -> Result<String, String> {
    match (os, architecture) {
        ("windows", "x86_64") => Ok("uv-x86_64-pc-windows-msvc.zip".to_string()),
        ("macos", "x86_64") => Ok("uv-x86_64-apple-darwin.tar.gz".to_string()),
        ("macos", "aarch64") => Ok("uv-aarch64-apple-darwin.tar.gz".to_string()),
        ("linux", "x86_64") => Ok("uv-x86_64-unknown-linux-gnu.tar.gz".to_string()),
        ("linux", "aarch64") => Ok("uv-aarch64-unknown-linux-gnu.tar.gz".to_string()),
        _ => Err(format!("Unsupported uv platform: {os}/{architecture}")),
    }
}

pub fn install_uv(root: &Path) -> Result<PathBuf, Box<dyn Error>> {
    let asset = uv_asset_name(std::env::consts::OS, std::env::consts::ARCH)?;
    let work = root.join(".tui/work/uv-install");
    fs::create_dir_all(&work)?;
    let archive = work.join(&asset);
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(60))
        .user_agent("InstructionX-Setup")
        .build()?;
    let response = client
        .get(format!("{UV_DOWNLOAD_BASE_URL}/{asset}"))
        .send()?
        .error_for_status()?;
    fs::write(&archive, response.bytes()?)?;
    let extracted = work.join("extracted");
    fs::create_dir_all(&extracted)?;
    extract_uv_archive(&archive, &extracted)?;
    let binary_name = if cfg!(windows) { "uv.exe" } else { "uv" };
    let source = find_binary(&extracted, binary_name)?;
    let target = root.join(".tui/tools").join(binary_name);
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::copy(source, &target)?;
    set_executable(&target)?;
    let status = Command::new(&target).arg("--version").status()?;
    if !status.success() {
        return Err("Downloaded uv failed verification".into());
    }
    Ok(target)
}

fn extract_uv_archive(archive: &Path, destination: &Path) -> Result<(), Box<dyn Error>> {
    if archive.extension().and_then(|value| value.to_str()) == Some("zip") {
        let mut zip = zip::ZipArchive::new(fs::File::open(archive)?)?;
        return Ok(zip.extract(destination)?);
    }
    let file = fs::File::open(archive)?;
    let decoder = flate2::read::GzDecoder::new(file);
    let mut tar = tar::Archive::new(decoder);
    Ok(tar.unpack(destination)?)
}

fn find_binary(root: &Path, name: &str) -> Result<PathBuf, Box<dyn Error>> {
    for entry in fs::read_dir(root)? {
        let entry = entry?;
        if entry.file_type()?.is_dir() {
            if let Ok(found) = find_binary(&entry.path(), name) {
                return Ok(found);
            }
        } else if entry.file_name() == name {
            return Ok(entry.path());
        }
    }
    Err(format!("uv binary not found: {name}").into())
}

#[cfg(unix)]
fn set_executable(path: &Path) -> Result<(), Box<dyn Error>> {
    use std::os::unix::fs::PermissionsExt;
    let mut permissions = fs::metadata(path)?.permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(path, permissions)?;
    Ok(())
}

#[cfg(windows)]
fn set_executable(_path: &Path) -> Result<(), Box<dyn Error>> {
    Ok(())
}

pub fn install_git() -> Result<(), Box<dyn Error>> {
    let (program, arguments) = git_install_command()?;
    let status = Command::new(program).args(arguments).status()?;
    if !status.success() {
        return Err("Git installation failed".into());
    }
    if !tool_available("git") {
        return Err("Git is still unavailable after installation".into());
    }
    Ok(())
}

fn git_install_command() -> Result<(String, Vec<String>), String> {
    if cfg!(windows) {
        return windows_git_command();
    }
    if cfg!(target_os = "macos") {
        return macos_git_command();
    }
    linux_git_command()
}

fn windows_git_command() -> Result<(String, Vec<String>), String> {
    if !tool_available("winget") {
        return Err("winget is required to install Git automatically".to_string());
    }
    Ok(command_spec(
        "winget",
        &[
            "install",
            "--id",
            "Git.Git",
            "-e",
            "--source",
            "winget",
            "--accept-package-agreements",
            "--accept-source-agreements",
            "--silent",
        ],
    ))
}

fn macos_git_command() -> Result<(String, Vec<String>), String> {
    if !tool_available("brew") {
        return Err("Homebrew is required to install Git automatically".to_string());
    }
    Ok(command_spec("brew", &["install", "git"]))
}

fn linux_git_command() -> Result<(String, Vec<String>), String> {
    for (package_manager, arguments) in [
        ("apt-get", vec!["install", "-y", "git"]),
        ("dnf", vec!["install", "-y", "git"]),
        ("pacman", vec!["-Sy", "--noconfirm", "git"]),
    ] {
        if tool_available(package_manager) {
            let mut command = vec![package_manager];
            command.extend(arguments);
            return Ok(command_spec("sudo", &command));
        }
    }
    Err("No supported Linux package manager was found".to_string())
}

fn command_spec(program: &str, arguments: &[&str]) -> (String, Vec<String>) {
    (
        program.to_string(),
        arguments.iter().map(|value| value.to_string()).collect(),
    )
}
