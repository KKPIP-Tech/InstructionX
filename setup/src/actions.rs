use std::error::Error;
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Stdio};

use crate::github::FrameworkVersion;

const PRESERVED_DIRECTORIES: &[&str] = &[
    "config",
    "data",
    "logs",
    "plugin",
    "custom_plugin",
    ".venv",
    ".tui",
    "temp",
    ".git",
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ArchiveAction {
    Install,
    Repair,
    Upgrade,
}

#[derive(Debug)]
pub struct InstallReport {
    pub copied_files: usize,
    pub backup_dir: PathBuf,
}

#[derive(Debug)]
pub struct ToolPreflight {
    pub git_present: bool,
    pub uv_present: bool,
}

impl ToolPreflight {
    pub fn detect() -> Self {
        Self::detect_with(tool_available)
    }

    pub fn detect_with<F>(available: F) -> Self
    where
        F: Fn(&str) -> bool,
    {
        Self {
            git_present: available("git"),
            uv_present: available("uv"),
        }
    }

    pub fn missing_tools(&self) -> Vec<&'static str> {
        let mut missing = Vec::new();
        if !self.git_present {
            missing.push("git");
        }
        if !self.uv_present {
            missing.push("uv");
        }
        missing
    }
}

pub fn tool_available(name: &str) -> bool {
    Command::new(name)
        .arg("--version")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .is_ok_and(|status| status.success())
}

#[derive(Debug)]
struct CopiedFile {
    destination: PathBuf,
    relative: PathBuf,
    existed_before: bool,
}

pub fn install_archive<F>(
    archive: &Path,
    root: &Path,
    action: ArchiveAction,
    after_copy: F,
) -> Result<InstallReport, Box<dyn Error>>
where
    F: FnOnce() -> Result<(), Box<dyn Error>>,
{
    validate_action(root, archive, action)?;
    let staging = root.join(".tui/work/staging");
    remove_if_exists(&staging)?;
    fs::create_dir_all(&staging)?;
    extract_archive(archive, &staging)?;
    let source = single_archive_root(&staging)?;
    validate_versions(root, &source, action)?;
    let backup_dir = root.join(".tui/backups").join(unique_backup_name());
    let mut copied = Vec::new();
    let result = copy_and_verify(&source, root, &backup_dir, &mut copied, after_copy);
    if let Err(error) = result {
        rollback(&backup_dir, copied)?;
        return Err(error);
    }
    remove_if_exists(&staging)?;
    Ok(InstallReport {
        copied_files: copied.len(),
        backup_dir,
    })
}

fn validate_action(
    root: &Path,
    archive: &Path,
    action: ArchiveAction,
) -> Result<(), Box<dyn Error>> {
    if !archive.is_file() {
        return Err(format!("Archive does not exist: {}", archive.display()).into());
    }
    let installed = root.join("main.py").is_file()
        && root.join("core/version.py").is_file()
        && root.join("pyproject.toml").is_file();
    if action == ArchiveAction::Install && installed {
        return Err("InstructionX is already installed".into());
    }
    if action != ArchiveAction::Install && !installed {
        return Err("InstructionX is not installed".into());
    }
    Ok(())
}

fn validate_versions(
    root: &Path,
    source: &Path,
    action: ArchiveAction,
) -> Result<(), Box<dyn Error>> {
    if action == ArchiveAction::Install {
        return Ok(());
    }
    let current = current_framework_version(root)?;
    let target = current_framework_version(source)?;
    if action == ArchiveAction::Repair && current != target {
        return Err("Repair requires the Release matching the installed version".into());
    }
    if action == ArchiveAction::Upgrade && target <= current {
        return Err("The selected Release is not newer than the installed version".into());
    }
    Ok(())
}

fn extract_archive(archive: &Path, destination: &Path) -> Result<(), Box<dyn Error>> {
    let file = fs::File::open(archive)?;
    let mut zip = zip::ZipArchive::new(file)?;
    for index in 0..zip.len() {
        let mut entry = zip.by_index(index)?;
        let Some(relative) = entry.enclosed_name() else {
            return Err("Archive contains an unsafe path".into());
        };
        let output = destination.join(relative);
        if entry.is_dir() {
            fs::create_dir_all(&output)?;
            continue;
        }
        if let Some(parent) = output.parent() {
            fs::create_dir_all(parent)?;
        }
        let mut target = fs::File::create(output)?;
        std::io::copy(&mut entry, &mut target)?;
    }
    Ok(())
}

fn single_archive_root(staging: &Path) -> Result<PathBuf, Box<dyn Error>> {
    let entries: Vec<_> = fs::read_dir(staging)?.collect::<Result<_, _>>()?;
    if entries.len() != 1 || !entries[0].file_type()?.is_dir() {
        return Err("Archive must contain exactly one root directory".into());
    }
    Ok(entries[0].path())
}

fn copy_and_verify<F>(
    source: &Path,
    root: &Path,
    backup_dir: &Path,
    copied: &mut Vec<CopiedFile>,
    after_copy: F,
) -> Result<(), Box<dyn Error>>
where
    F: FnOnce() -> Result<(), Box<dyn Error>>,
{
    copy_directory(source, root, root, backup_dir, copied)?;
    after_copy()
}

fn copy_directory(
    source: &Path,
    destination: &Path,
    root: &Path,
    backup_dir: &Path,
    copied: &mut Vec<CopiedFile>,
) -> Result<(), Box<dyn Error>> {
    for entry in fs::read_dir(source)? {
        let entry = entry?;
        let name = entry.file_name();
        let name_text = name.to_string_lossy();
        if PRESERVED_DIRECTORIES.contains(&name_text.as_ref()) || name_text == "__pycache__" {
            continue;
        }
        let target = destination.join(&name);
        if entry.file_type()?.is_dir() {
            fs::create_dir_all(&target)?;
            copy_directory(&entry.path(), &target, root, backup_dir, copied)?;
        } else {
            copy_file(&entry.path(), &target, root, backup_dir, copied)?;
        }
    }
    Ok(())
}

fn copy_file(
    source: &Path,
    destination: &Path,
    root: &Path,
    backup_dir: &Path,
    copied: &mut Vec<CopiedFile>,
) -> Result<(), Box<dyn Error>> {
    if let Some(parent) = destination.parent() {
        fs::create_dir_all(parent)?;
    }
    let relative = destination.strip_prefix(root)?.to_path_buf();
    let existed_before = destination.exists();
    if existed_before {
        let backup = backup_dir.join(&relative);
        if let Some(parent) = backup.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::copy(destination, backup)?;
    }
    fs::copy(source, destination)?;
    copied.push(CopiedFile {
        destination: destination.to_path_buf(),
        relative,
        existed_before,
    });
    Ok(())
}

fn rollback(backup_dir: &Path, copied: Vec<CopiedFile>) -> Result<(), Box<dyn Error>> {
    for file in &copied {
        if !file.existed_before {
            remove_if_exists(&file.destination)?;
        }
    }
    for file in copied.iter().rev() {
        if file.existed_before {
            fs::copy(backup_dir.join(&file.relative), &file.destination)?;
        }
    }
    Ok(())
}

fn remove_if_exists(path: &Path) -> Result<(), Box<dyn Error>> {
    if !path.exists() {
        return Ok(());
    }
    if path.is_dir() {
        fs::remove_dir_all(path)?;
    } else {
        fs::remove_file(path)?;
    }
    Ok(())
}

fn unique_backup_name() -> String {
    let timestamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    timestamp.to_string()
}

pub fn current_framework_version(root: &Path) -> Result<FrameworkVersion, String> {
    let content =
        fs::read_to_string(root.join("core/version.py")).map_err(|error| error.to_string())?;
    let numeric = content
        .lines()
        .find_map(|line| {
            let (key, value) = line.trim().split_once('=')?;
            if key.trim() == "VERSION" {
                Some(value)
            } else {
                None
            }
        })
        .map(|value| {
            value
                .trim()
                .trim_matches(|character| character == '"' || character == '\'')
        })
        .ok_or_else(|| "VERSION not found".to_string())?;
    let app_version = content
        .lines()
        .find(|line| line.trim().starts_with("APP_VERSION"))
        .unwrap_or_default();
    let channel = if app_version.contains("VersionType.BETA") {
        "beta"
    } else if app_version.contains("VersionType.PRE_RELEASE") {
        "pre-release"
    } else if app_version.contains("VersionType.RELEASE") {
        "release"
    } else if app_version.contains("VersionType.INTERNAL") {
        "internal"
    } else {
        "alpha"
    };
    FrameworkVersion::parse(&format!("{channel}-v{numeric}"))
}

pub fn archive_root_component(path: &Path) -> Option<&str> {
    path.components().find_map(|component| match component {
        Component::Normal(value) => value.to_str(),
        _ => None,
    })
}
