use std::error::Error;
use std::fmt::Write as _;
use std::fs;
use std::io::Write as _;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::mpsc::{self, Receiver, Sender};
use std::thread;

use chrono::Local;

use crate::actions::{
    ArchiveAction, InstallReport, ToolPreflight, current_framework_version, install_archive,
};
use crate::github::{FrameworkVersion, Release, ReleaseCatalog, ReleaseClient};
use crate::plugins::{
    DependencyResult, PluginInventory, PluginUpdateResult, check_plugin_updates,
    install_plugin_dependencies,
};
use crate::shortcuts::ShortcutManager;
use crate::uv::{PackageInfo, UvClient, uv_program};

const GITHUB_API_URL: &str = "https://api.github.com";
const LOG_RELATIVE_PATH: &str = "logs/tui_setup.log";
const ARCHIVE_STEPS: usize = 7;
const VERIFY_IMPORTS: &str = "import PySide6, numpy, requests, orjson, mcp, packaging";
const UNINSTALL_DIRECTORIES: &[&str] = &[".venv", "config", "data", "logs", ".tui"];

#[derive(Debug)]
pub enum OperationRequest {
    Archive {
        root: PathBuf,
        action: ArchiveAction,
        selected_release: Option<Release>,
        archive: Option<PathBuf>,
        release_tag: Option<String>,
        auto_install: bool,
    },
    LoadReleases {
        root: PathBuf,
    },
    LoadPackages {
        root: PathBuf,
    },
    UpdatePackages {
        root: PathBuf,
        packages: Vec<String>,
    },
    RemovePackages {
        root: PathBuf,
        packages: Vec<String>,
    },
    RebuildEnvironment {
        root: PathBuf,
    },
    RefreshPlugins {
        root: PathBuf,
    },
    CheckPluginUpdates {
        root: PathBuf,
    },
    InstallPluginDependencies {
        root: PathBuf,
    },
    CreateShortcut {
        root: PathBuf,
    },
    InstallGit {
        root: PathBuf,
    },
    InstallUv {
        root: PathBuf,
    },
    CleanTemp {
        root: PathBuf,
    },
    Uninstall {
        root: PathBuf,
        confirmed: bool,
    },
}

impl OperationRequest {
    pub fn name(&self) -> &'static str {
        match self {
            Self::Archive {
                action: ArchiveAction::Install,
                ..
            } => "Install InstructionX",
            Self::Archive {
                action: ArchiveAction::Repair,
                ..
            } => "Repair InstructionX",
            Self::Archive {
                action: ArchiveAction::Upgrade,
                ..
            } => "Upgrade InstructionX",
            Self::LoadReleases { .. } => "Check GitHub Releases",
            Self::LoadPackages { .. } => "Query package list",
            Self::UpdatePackages { .. } => "Update selected packages",
            Self::RemovePackages { .. } => "Remove selected packages",
            Self::RebuildEnvironment { .. } => "Rebuild environment",
            Self::RefreshPlugins { .. } => "Refresh plugin list",
            Self::CheckPluginUpdates { .. } => "Check plugin updates",
            Self::InstallPluginDependencies { .. } => "Install plugin dependencies",
            Self::CreateShortcut { .. } => "Create desktop shortcut",
            Self::InstallGit { .. } => "Install Git",
            Self::InstallUv { .. } => "Install uv",
            Self::CleanTemp { .. } => "Clean temporary files",
            Self::Uninstall { .. } => "Uninstall environment",
        }
    }

    pub fn root(&self) -> &Path {
        match self {
            Self::Archive { root, .. }
            | Self::LoadReleases { root }
            | Self::LoadPackages { root }
            | Self::UpdatePackages { root, .. }
            | Self::RemovePackages { root, .. }
            | Self::RebuildEnvironment { root }
            | Self::RefreshPlugins { root }
            | Self::CheckPluginUpdates { root }
            | Self::InstallPluginDependencies { root }
            | Self::CreateShortcut { root }
            | Self::InstallGit { root }
            | Self::InstallUv { root }
            | Self::CleanTemp { root }
            | Self::Uninstall { root, .. } => root,
        }
    }
}

#[derive(Debug)]
pub enum OperationData {
    None,
    Releases(ReleaseCatalog),
    Packages(Vec<PackageInfo>),
    Plugins(PluginInventory),
    PluginUpdates(Vec<PluginUpdateResult>),
    Dependencies(Vec<DependencyResult>),
}

#[derive(Debug)]
pub struct OperationSuccess {
    pub summary: String,
    pub details: Vec<String>,
    pub data: OperationData,
}

impl OperationSuccess {
    fn new(summary: String, data: OperationData) -> Self {
        Self {
            summary,
            details: Vec::new(),
            data,
        }
    }

    fn with_details(summary: String, details: Vec<String>) -> Self {
        Self {
            summary,
            details,
            data: OperationData::None,
        }
    }
}

#[derive(Debug, Clone)]
pub struct OperationUpdate {
    pub current: usize,
    pub total: usize,
    pub message: String,
}

#[derive(Debug)]
pub enum OperationEvent {
    Update(OperationUpdate),
    Finished(Result<OperationSuccess, String>),
}

pub struct RunningOperation {
    pub name: &'static str,
    receiver: Receiver<OperationEvent>,
}

impl RunningOperation {
    pub fn start(request: OperationRequest) -> Self {
        let name = request.name();
        let (sender, receiver) = mpsc::channel();
        thread::spawn(move || run_in_background(request, sender));
        Self { name, receiver }
    }

    pub fn try_recv(&self) -> Result<OperationEvent, mpsc::TryRecvError> {
        self.receiver.try_recv()
    }
}

struct OperationLogger {
    file: fs::File,
}

impl OperationLogger {
    fn new(root: &Path) -> std::io::Result<Self> {
        let path = root.join(LOG_RELATIVE_PATH);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        let file = fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)?;
        Ok(Self { file })
    }

    fn append(&mut self, message: &str) -> std::io::Result<()> {
        writeln!(
            self.file,
            "[{}] {message}",
            Local::now().format("%Y-%m-%d %H:%M:%S")
        )
    }
}

struct Reporter<'a> {
    callback: &'a mut dyn FnMut(OperationUpdate),
    logger: Option<OperationLogger>,
}

impl<'a> Reporter<'a> {
    fn step(&mut self, current: usize, total: usize, message: &str) {
        self.emit(OperationUpdate {
            current,
            total,
            message: message.to_string(),
        });
    }

    fn message(&mut self, message: &str) {
        self.emit(OperationUpdate {
            current: 0,
            total: 0,
            message: message.to_string(),
        });
    }

    fn log(&mut self, message: &str) {
        if let Some(logger) = &mut self.logger
            && let Err(error) = logger.append(message)
        {
            self.message(&format!("Could not write Setup log: {error}"));
        }
    }

    fn emit(&mut self, update: OperationUpdate) {
        let mut log_line = String::new();
        if update.total > 0 {
            let _ = write!(log_line, "[{}/{}] ", update.current, update.total);
        }
        log_line.push_str(&update.message);
        if let Some(logger) = &mut self.logger {
            let _ = logger.append(&log_line);
        }
        (self.callback)(update);
    }
}

pub fn request_for_action(
    root: &Path,
    action: &str,
    archive: Option<&Path>,
    release_tag: Option<&str>,
    auto_install: bool,
) -> Result<OperationRequest, Box<dyn Error>> {
    let root = root.to_path_buf();
    match action {
        "install" | "repair" | "upgrade" => Ok(archive_request(
            root,
            action,
            archive,
            release_tag,
            auto_install,
        )?),
        "environment-repair" => Ok(OperationRequest::RebuildEnvironment { root }),
        "check-updates" => Ok(OperationRequest::LoadReleases { root }),
        "create-shortcut" => Ok(OperationRequest::CreateShortcut { root }),
        "clean-temp" => Ok(OperationRequest::CleanTemp { root }),
        "uninstall" => Ok(OperationRequest::Uninstall {
            root,
            confirmed: auto_install,
        }),
        _ => Err(format!("Unknown action: {action}").into()),
    }
}

fn archive_request(
    root: PathBuf,
    action: &str,
    archive: Option<&Path>,
    release_tag: Option<&str>,
    auto_install: bool,
) -> Result<OperationRequest, Box<dyn Error>> {
    let action = match action {
        "install" => ArchiveAction::Install,
        "repair" => ArchiveAction::Repair,
        "upgrade" => ArchiveAction::Upgrade,
        _ => return Err(format!("Unknown archive action: {action}").into()),
    };
    Ok(OperationRequest::Archive {
        root,
        action,
        selected_release: None,
        archive: archive.map(Path::to_path_buf),
        release_tag: release_tag.map(str::to_string),
        auto_install,
    })
}

pub fn execute_operation<F>(
    request: OperationRequest,
    mut callback: F,
) -> Result<OperationSuccess, Box<dyn Error>>
where
    F: FnMut(OperationUpdate),
{
    let name = request.name();
    let logger = OperationLogger::new(request.root()).ok();
    let mut reporter = Reporter {
        callback: &mut callback,
        logger,
    };
    if reporter.logger.is_none() {
        reporter.message("Could not open logs/tui_setup.log; continuing without file logging");
    }
    reporter.log(&format!("Operation started: {name}"));
    let result = execute_request(&request, &mut reporter);
    match &result {
        Ok(success) => {
            for detail in &success.details {
                reporter.log(detail);
            }
            reporter.log(&format!("Operation completed: {}", success.summary));
        }
        Err(error) => reporter.log(&format!("Operation failed: {error}")),
    }
    result
}

fn execute_request(
    request: &OperationRequest,
    reporter: &mut Reporter,
) -> Result<OperationSuccess, Box<dyn Error>> {
    match request {
        OperationRequest::Archive {
            root,
            action,
            selected_release,
            archive,
            release_tag,
            auto_install,
        } => execute_archive(
            root,
            *action,
            selected_release.as_ref(),
            archive.as_deref(),
            release_tag.as_deref(),
            *auto_install,
            reporter,
        ),
        OperationRequest::LoadReleases { root } => load_releases(root, reporter),
        OperationRequest::LoadPackages { root } => load_packages(root, reporter),
        OperationRequest::UpdatePackages { root, packages } => {
            update_packages(root, packages, reporter)
        }
        OperationRequest::RemovePackages { root, packages } => {
            remove_packages(root, packages, reporter)
        }
        OperationRequest::RebuildEnvironment { root } => rebuild_environment(root, reporter),
        OperationRequest::RefreshPlugins { root } => refresh_plugins(root, reporter),
        OperationRequest::CheckPluginUpdates { root } => check_updates(root, reporter),
        OperationRequest::InstallPluginDependencies { root } => {
            install_dependencies(root, reporter)
        }
        OperationRequest::CreateShortcut { root } => create_shortcut(root, reporter),
        OperationRequest::InstallGit { .. } => install_git(reporter),
        OperationRequest::InstallUv { root } => install_uv(root, reporter),
        OperationRequest::CleanTemp { root } => clean_temp(root, reporter),
        OperationRequest::Uninstall { root, confirmed } => uninstall(root, *confirmed, reporter),
    }
}

fn execute_archive(
    root: &Path,
    action: ArchiveAction,
    selected: Option<&Release>,
    archive: Option<&Path>,
    release_tag: Option<&str>,
    auto_install: bool,
    reporter: &mut Reporter,
) -> Result<OperationSuccess, Box<dyn Error>> {
    ensure_uv(root, auto_install, reporter)?;
    let archive = resolve_archive(root, action, selected, archive, release_tag, reporter)?;
    reporter.step(
        4,
        ARCHIVE_STEPS,
        "Validate, extract and copy the Release archive",
    );
    let mut uv = UvClient::new(root);
    let report = install_archive(&archive, root, action, || {
        configure_archive_environment(root, action, &mut uv, reporter)
    })?;
    reporter.step(
        ARCHIVE_STEPS,
        ARCHIVE_STEPS,
        "Installation and verification completed",
    );
    Ok(archive_success(action, report))
}

fn ensure_uv(
    root: &Path,
    auto_install: bool,
    reporter: &mut Reporter,
) -> Result<(), Box<dyn Error>> {
    reporter.step(1, ARCHIVE_STEPS, "Check the uv package manager");
    if ToolPreflight::detect_for_root(root).uv_present {
        reporter.message(&format!("Using uv: {}", uv_program(root).display()));
        return Ok(());
    }
    if !auto_install {
        return Err("uv is missing; use --yes to allow automatic installation".into());
    }
    let path = crate::uv::install_uv(root)?;
    if !path.is_file() {
        return Err("uv installation finished without a usable executable".into());
    }
    reporter.message(&format!("uv installed: {}", path.display()));
    Ok(())
}

fn resolve_archive(
    root: &Path,
    action: ArchiveAction,
    selected: Option<&Release>,
    archive: Option<&Path>,
    release_tag: Option<&str>,
    reporter: &mut Reporter,
) -> Result<PathBuf, Box<dyn Error>> {
    reporter.step(2, ARCHIVE_STEPS, "Resolve the requested Release");
    if let Some(path) = archive {
        reporter.message(&format!("Using local archive: {}", path.display()));
        return Ok(path.to_path_buf());
    }
    if let Some(tag) = release_tag {
        return download_archive(root, tag, reporter);
    }
    let release = select_release(root, action, selected, reporter)?;
    download_archive(root, &release.tag_name, reporter)
}

fn select_release(
    root: &Path,
    action: ArchiveAction,
    selected: Option<&Release>,
    reporter: &mut Reporter,
) -> Result<Release, Box<dyn Error>> {
    if let Some(release) = selected {
        return Ok(release.clone());
    }
    reporter.message("Fetch the published Release timeline");
    let catalog = fetch_release_catalog(root)?;
    let current = current_framework_version(root).ok();
    let release = match action {
        ArchiveAction::Repair => catalog
            .releases
            .iter()
            .find(|release| release.version == current),
        _ => catalog.latest(),
    };
    release
        .cloned()
        .ok_or("No matching Release was found".into())
}

fn download_archive(
    root: &Path,
    tag: &str,
    reporter: &mut Reporter,
) -> Result<PathBuf, Box<dyn Error>> {
    reporter.step(3, ARCHIVE_STEPS, &format!("Download Release {tag}"));
    let client = ReleaseClient::new(GITHUB_API_URL)?;
    let destination = root.join(".tui/work").join(format!("{tag}.zip"));
    let checksum = client.download_archive(tag, &destination)?;
    reporter.message(&format!("Download complete; SHA-256: {checksum}"));
    Ok(destination)
}

fn configure_archive_environment(
    root: &Path,
    action: ArchiveAction,
    uv: &mut UvClient,
    reporter: &mut Reporter,
) -> Result<(), Box<dyn Error>> {
    reporter.step(5, ARCHIVE_STEPS, "Install framework dependencies");
    if action == ArchiveAction::Install {
        uv.sync_environment()?;
    } else {
        uv.install_requirements()?;
    }
    reporter.step(6, ARCHIVE_STEPS, "Verify required Python components");
    verify_environment(root)
}

fn verify_environment(root: &Path) -> Result<(), Box<dyn Error>> {
    let python = crate::plugins::framework_python(root);
    let output = Command::new(python)
        .args(["-c", VERIFY_IMPORTS])
        .current_dir(root)
        .output()?;
    if !output.status.success() {
        let detail = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Installation verification failed: {detail}").into());
    }
    Ok(())
}

fn archive_success(action: ArchiveAction, report: InstallReport) -> OperationSuccess {
    let name = match action {
        ArchiveAction::Install => "Installation",
        ArchiveAction::Repair => "Repair",
        ArchiveAction::Upgrade => "Upgrade",
    };
    OperationSuccess::with_details(
        format!("{name} completed; {} files copied", report.copied_files),
        vec![format!("Backup: {}", report.backup_dir.display())],
    )
}

fn fetch_release_catalog(root: &Path) -> Result<ReleaseCatalog, Box<dyn Error>> {
    let current =
        current_framework_version(root).or_else(|_| FrameworkVersion::parse("alpha-v0.0.0"))?;
    let client = ReleaseClient::new(GITHUB_API_URL)?;
    client.list_all_releases(current)
}

fn load_releases(root: &Path, reporter: &mut Reporter) -> Result<OperationSuccess, Box<dyn Error>> {
    reporter.step(1, 1, "Fetch the complete GitHub Release timeline");
    let catalog = fetch_release_catalog(root)?;
    let count = catalog.releases.len();
    let details = catalog
        .releases
        .iter()
        .map(|release| {
            format!(
                "{} | {} | {}",
                release.name,
                release.tag_name,
                release.published_at.format("%Y-%m-%d")
            )
        })
        .collect();
    let mut success = OperationSuccess::new(
        format!("Loaded {count} Releases"),
        OperationData::Releases(catalog),
    );
    success.details = details;
    Ok(success)
}

fn load_packages(root: &Path, reporter: &mut Reporter) -> Result<OperationSuccess, Box<dyn Error>> {
    reporter.step(1, 1, "Read installed and outdated Python packages");
    let packages = UvClient::new(root).list_packages()?;
    Ok(OperationSuccess::new(
        format!("Package list updated; {} packages", packages.len()),
        OperationData::Packages(packages),
    ))
}

fn update_packages(
    root: &Path,
    packages: &[String],
    reporter: &mut Reporter,
) -> Result<OperationSuccess, Box<dyn Error>> {
    if packages.is_empty() {
        return Err("No packages were selected for update".into());
    }
    let mut client = UvClient::new(root);
    for (index, package) in packages.iter().enumerate() {
        reporter.step(index + 1, packages.len() + 1, &format!("Update {package}"));
        client.update_packages(std::slice::from_ref(package))?;
    }
    reporter.step(
        packages.len() + 1,
        packages.len() + 1,
        "Refresh the package list",
    );
    let refreshed = client.list_packages()?;
    Ok(OperationSuccess::new(
        format!("Updated {} packages", packages.len()),
        OperationData::Packages(refreshed),
    ))
}

fn remove_packages(
    root: &Path,
    packages: &[String],
    reporter: &mut Reporter,
) -> Result<OperationSuccess, Box<dyn Error>> {
    if packages.is_empty() {
        return Err("No removable packages were selected".into());
    }
    let mut client = UvClient::new(root);
    for (index, package) in packages.iter().enumerate() {
        reporter.step(index + 1, packages.len() + 1, &format!("Remove {package}"));
        client.remove_packages(std::slice::from_ref(package))?;
    }
    reporter.step(
        packages.len() + 1,
        packages.len() + 1,
        "Refresh the package list",
    );
    let refreshed = client.list_packages()?;
    Ok(OperationSuccess::new(
        format!("Removed {} packages", packages.len()),
        OperationData::Packages(refreshed),
    ))
}

fn rebuild_environment(
    root: &Path,
    reporter: &mut Reporter,
) -> Result<OperationSuccess, Box<dyn Error>> {
    reporter.step(
        1,
        2,
        "Delete .venv and reinstall locked framework dependencies",
    );
    UvClient::new(root).rebuild_environment()?;
    reporter.step(2, 2, "Install dependencies for every plugin");
    dependency_success(root)
}

fn refresh_plugins(
    root: &Path,
    reporter: &mut Reporter,
) -> Result<OperationSuccess, Box<dyn Error>> {
    reporter.step(1, 1, "Read plugin descriptors and registry");
    let inventory = PluginInventory::load(root)?;
    let count = inventory.plugins.len();
    let mut success = OperationSuccess::new(
        format!("Plugin list refreshed; {count} plugins"),
        OperationData::Plugins(inventory),
    );
    success.details = success_details(&success.data);
    Ok(success)
}

fn check_updates(root: &Path, reporter: &mut Reporter) -> Result<OperationSuccess, Box<dyn Error>> {
    reporter.step(1, 1, "Check each plugin's published versions");
    let results = check_plugin_updates(root)?;
    let updates = results
        .iter()
        .filter(|result| result.update_available)
        .count();
    Ok(OperationSuccess::new(
        format!("Plugin updates checked; {updates} updates available"),
        OperationData::PluginUpdates(results),
    ))
}

fn install_dependencies(
    root: &Path,
    reporter: &mut Reporter,
) -> Result<OperationSuccess, Box<dyn Error>> {
    reporter.step(1, 1, "Install plugin dependencies one plugin at a time");
    dependency_success(root)
}

fn dependency_success(root: &Path) -> Result<OperationSuccess, Box<dyn Error>> {
    let results = install_plugin_dependencies(root)?;
    let failed = results.iter().filter(|result| !result.success).count();
    let details = results
        .iter()
        .map(|result| {
            format!(
                "{}: {} {}",
                result.plugin_name,
                if result.success { "OK" } else { "FAILED" },
                result.detail
            )
        })
        .collect();
    let mut success = OperationSuccess::new(
        format!("Plugin dependency installation finished; {failed} failed"),
        OperationData::Dependencies(results),
    );
    success.details = details;
    Ok(success)
}

fn create_shortcut(
    root: &Path,
    reporter: &mut Reporter,
) -> Result<OperationSuccess, Box<dyn Error>> {
    reporter.step(1, 1, "Create and verify the desktop shortcut");
    let manager = ShortcutManager::new(root.to_path_buf(), uv_program(root));
    let path = manager.create(false)?;
    Ok(OperationSuccess::with_details(
        "Desktop shortcut created".to_string(),
        vec![format!("Shortcut: {}", path.display())],
    ))
}

fn install_git(reporter: &mut Reporter) -> Result<OperationSuccess, Box<dyn Error>> {
    reporter.step(1, 1, "Install Git with the platform package manager");
    crate::uv::install_git()?;
    Ok(OperationSuccess::with_details(
        "Git installed successfully".to_string(),
        Vec::new(),
    ))
}

fn install_uv(root: &Path, reporter: &mut Reporter) -> Result<OperationSuccess, Box<dyn Error>> {
    reporter.step(1, 1, "Download and verify the uv executable");
    let path = crate::uv::install_uv(root)?;
    Ok(OperationSuccess::with_details(
        "uv installed successfully".to_string(),
        vec![format!("uv: {}", path.display())],
    ))
}

fn clean_temp(root: &Path, reporter: &mut Reporter) -> Result<OperationSuccess, Box<dyn Error>> {
    reporter.step(1, 1, "Clean temporary files");
    let work = root.join(".tui/work");
    if work.exists() {
        fs::remove_dir_all(work)?;
    }
    Ok(OperationSuccess::with_details(
        "Temporary files cleaned".to_string(),
        Vec::new(),
    ))
}

fn uninstall(
    root: &Path,
    confirmed: bool,
    reporter: &mut Reporter,
) -> Result<OperationSuccess, Box<dyn Error>> {
    if !confirmed {
        return Err("Uninstall requires --yes".into());
    }
    reporter.step(1, 2, "Remove the virtual environment and runtime data");
    for name in UNINSTALL_DIRECTORIES {
        remove_directory(root.join(name))?;
    }
    reporter.step(2, 2, "Remove the desktop shortcut");
    remove_shortcut(root)?;
    Ok(OperationSuccess::with_details(
        "Environment and shortcuts removed; program files and plugins were kept".to_string(),
        Vec::new(),
    ))
}

fn remove_directory(path: PathBuf) -> Result<(), Box<dyn Error>> {
    if path.exists() {
        fs::remove_dir_all(path)?;
    }
    Ok(())
}

fn remove_shortcut(root: &Path) -> Result<(), Box<dyn Error>> {
    let shortcut = ShortcutManager::new(root.to_path_buf(), PathBuf::from("uv")).shortcut_path();
    if shortcut.is_dir() {
        fs::remove_dir_all(shortcut)?;
    } else if shortcut.is_file() {
        fs::remove_file(shortcut)?;
    }
    Ok(())
}

fn success_details(data: &OperationData) -> Vec<String> {
    match data {
        OperationData::Plugins(inventory) => inventory.warnings.clone(),
        _ => Vec::new(),
    }
}

fn run_in_background(request: OperationRequest, sender: Sender<OperationEvent>) {
    let result = execute_operation(request, |update| {
        let _ = sender.send(OperationEvent::Update(update));
    })
    .map_err(|error| error.to_string());
    let _ = sender.send(OperationEvent::Finished(result));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_documented_cli_action_has_an_operation_request() {
        let root = Path::new(".");
        for action in [
            "install",
            "repair",
            "upgrade",
            "environment-repair",
            "check-updates",
            "create-shortcut",
            "clean-temp",
            "uninstall",
        ] {
            let request = request_for_action(root, action, None, None, true);
            assert!(request.is_ok(), "操作 {action} 应生成执行请求");
        }
    }

    #[test]
    fn unknown_cli_action_is_rejected_before_execution() {
        let result = request_for_action(Path::new("."), "unknown", None, None, false);
        assert!(result.is_err());
    }
}
