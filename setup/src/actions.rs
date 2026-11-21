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

    pub fn detect_for_root(root: &Path) -> Self {
        Self::detect_for_root_with(root, tool_available)
    }

    pub fn detect_for_root_with<F>(root: &Path, available: F) -> Self
    where
        F: Fn(&str) -> bool,
    {
        Self {
            git_present: available("git"),
            uv_present: crate::uv::uv_program(root).is_file() || available("uv"),
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
    let result = copy_and_verify(
        &source,
        root,
        &backup_dir,
        &mut copied,
        action != ArchiveAction::Install,
        after_copy,
    );
    if let Err(error) = result {
        if let Err(rollback_error) = rollback(&backup_dir, copied) {
            return Err(format!("{error}; rollback also failed: {rollback_error}").into());
        }
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
    preserve_plugins: bool,
    after_copy: F,
) -> Result<(), Box<dyn Error>>
where
    F: FnOnce() -> Result<(), Box<dyn Error>>,
{
    copy_directory(source, root, root, backup_dir, copied, preserve_plugins)?;
    after_copy()
}

fn copy_directory(
    source: &Path,
    destination: &Path,
    root: &Path,
    backup_dir: &Path,
    copied: &mut Vec<CopiedFile>,
    preserve_plugins: bool,
) -> Result<(), Box<dyn Error>> {
    for entry in fs::read_dir(source)? {
        let entry = entry?;
        let name = entry.file_name();
        let name_text = name.to_string_lossy();
        let target = destination.join(&name);
        let existing_plugin = !preserve_plugins
            && matches!(name_text.as_ref(), "plugin" | "custom_plugin")
            && target.exists();
        let preserved = destination == root
            && (should_preserve_directory(&name_text, preserve_plugins) || existing_plugin);
        if preserved || name_text == "__pycache__" {
            continue;
        }
        if entry.file_type()?.is_dir() {
            fs::create_dir_all(&target)?;
            copy_directory(
                &entry.path(),
                &target,
                root,
                backup_dir,
                copied,
                preserve_plugins,
            )?;
        } else {
            copy_file(&entry.path(), &target, root, backup_dir, copied)?;
        }
    }
    Ok(())
}

fn should_preserve_directory(name: &str, preserve_plugins: bool) -> bool {
    if !PRESERVED_DIRECTORIES.contains(&name) {
        return false;
    }
    preserve_plugins || !matches!(name, "plugin" | "custom_plugin")
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
    let backup = backup_dir.join(&relative);
    let move_to_backup = existed_before && is_running_executable(destination);
    if existed_before {
        if let Some(parent) = backup.parent() {
            fs::create_dir_all(parent)?;
        }
        if move_to_backup {
            fs::rename(destination, &backup).map_err(|error| {
                format!(
                    "Failed to move the running Setup from {} to {}: {error}",
                    destination.display(),
                    backup.display()
                )
            })?;
        } else {
            fs::copy(destination, &backup).map_err(|error| {
                format!(
                    "Failed to back up {} to {}: {error}",
                    destination.display(),
                    backup.display()
                )
            })?;
        }
    }
    copy_new_file(source, destination, &backup, move_to_backup)?;
    copied.push(CopiedFile {
        destination: destination.to_path_buf(),
        relative,
        existed_before,
    });
    Ok(())
}

fn copy_new_file(
    source: &Path,
    destination: &Path,
    backup: &Path,
    restore_on_failure: bool,
) -> Result<(), Box<dyn Error>> {
    if let Err(error) = fs::copy(source, destination) {
        let copy_error = format!(
            "Failed to copy {} to {}: {error}",
            source.display(),
            destination.display()
        );
        if restore_on_failure && let Err(restore_error) = fs::rename(backup, destination) {
            return Err(format!("{copy_error}; immediate restore failed: {restore_error}").into());
        }
        return Err(copy_error.into());
    }
    Ok(())
}

fn is_running_executable(path: &Path) -> bool {
    let Ok(executable) = std::env::current_exe() else {
        return false;
    };
    match (fs::canonicalize(path), fs::canonicalize(&executable)) {
        (Ok(path), Ok(executable)) => path == executable,
        _ => path == executable,
    }
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

#[cfg(test)]
mod tests {
    use std::io::Write;

    use super::*;

    #[test]
    fn install_copies_official_and_third_party_plugin_directories() {
        let temporary = tempfile::tempdir().expect("创建临时目录");
        let archive = temporary.path().join("release.zip");
        write_test_archive(&archive);
        let target = temporary.path().join("target");
        fs::create_dir(&target).expect("创建安装目录");

        install_archive(&archive, &target, ArchiveAction::Install, || {
            Ok::<(), Box<dyn Error>>(())
        })
        .expect("安装测试归档");

        assert!(target.join("plugin/example/IXPlugin.json").is_file());
        assert!(target.join("custom_plugin/__init__.py").is_file());
    }

    #[test]
    fn local_uv_satisfies_interactive_preflight_without_path_uv() {
        let temporary = tempfile::tempdir().expect("创建临时目录");
        let binary_name = if cfg!(windows) { "uv.exe" } else { "uv" };
        let local_uv = temporary.path().join(".tui/tools").join(binary_name);
        fs::create_dir_all(local_uv.parent().expect("uv 父目录")).expect("创建工具目录");
        fs::write(&local_uv, b"test").expect("写入本地 uv 占位文件");

        let preflight = ToolPreflight::detect_for_root_with(temporary.path(), |_| false);

        assert!(preflight.uv_present);
        assert!(!preflight.git_present);
        assert_eq!(crate::uv::uv_program(temporary.path()), local_uv);
    }

    #[test]
    fn failed_copy_restores_executable_moved_to_backup() {
        let temporary = tempfile::tempdir().expect("创建临时目录");
        let destination = temporary.path().join("setup.exe");
        let backup = temporary.path().join("backup.exe");
        fs::write(&backup, b"old setup").expect("写入旧 Setup 备份");

        let result = copy_new_file(
            &temporary.path().join("missing.exe"),
            &destination,
            &backup,
            true,
        );

        assert!(result.is_err());
        assert_eq!(
            fs::read(destination).expect("读取恢复的 Setup"),
            b"old setup"
        );
        assert!(!backup.exists());
    }

    fn write_test_archive(archive: &Path) {
        let file = fs::File::create(archive).expect("创建测试归档");
        let mut zip = zip::ZipWriter::new(file);
        let options = zip::write::SimpleFileOptions::default();
        for (name, content) in test_archive_files() {
            zip.start_file(format!("InstructionX-test/{name}"), options)
                .expect("写入归档条目");
            zip.write_all(content.as_bytes()).expect("写入归档内容");
        }
        zip.finish().expect("完成测试归档");
    }

    fn test_archive_files() -> [(&'static str, &'static str); 6] {
        [
            ("main.py", "print('ok')\n"),
            ("core/version.py", "VERSION = '1.0.0'\n"),
            (
                "pyproject.toml",
                "[project]\nname='test'\nversion='1.0.0'\n",
            ),
            ("requirements.txt", ""),
            ("plugin/example/IXPlugin.json", "{\"id\":\"example\"}"),
            ("custom_plugin/__init__.py", ""),
        ]
    }
}
