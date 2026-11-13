use std::error::Error;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use serde::Deserialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PluginScope {
    Official,
    ThirdParty,
}

#[derive(Debug, Clone)]
pub enum PluginUpdateStatus {
    Unchecked,
    Checking,
    UpToDate,
    UpdateAvailable(String),
    Failed(String),
}

#[derive(Debug, Clone)]
pub struct PluginInfo {
    pub id: String,
    pub name: String,
    pub description: String,
    pub version: String,
    pub developer_url: String,
    pub scope: PluginScope,
    pub dependencies: Vec<String>,
    pub update: PluginUpdateStatus,
}

#[derive(Debug, Clone, Default)]
pub struct PluginInventory {
    pub plugins: Vec<PluginInfo>,
    pub warnings: Vec<String>,
}

impl PluginInventory {
    pub fn load(root: &Path) -> Result<Self, Box<dyn Error>> {
        let registry = load_registry(root);
        let mut inventory = Self::default();
        inventory.load_scope(root, "plugin", PluginScope::Official, &registry)?;
        inventory.load_scope(root, "custom_plugin", PluginScope::ThirdParty, &registry)?;
        Ok(inventory)
    }

    fn load_scope(
        &mut self,
        root: &Path,
        directory: &str,
        scope: PluginScope,
        registry: &serde_json::Value,
    ) -> Result<(), Box<dyn Error>> {
        let parent = root.join(directory);
        if !parent.is_dir() {
            return Ok(());
        }
        for entry in fs::read_dir(parent)? {
            let entry = entry?;
            if !entry.file_type()?.is_dir() || entry.file_name().to_string_lossy().starts_with('_')
            {
                continue;
            }
            match load_plugin(&entry.path(), scope, registry) {
                Ok(plugin) => self.plugins.push(plugin),
                Err(error) => self
                    .warnings
                    .push(format!("{}: {error}", entry.path().display())),
            }
        }
        Ok(())
    }
}

fn load_plugin(
    directory: &Path,
    scope: PluginScope,
    registry: &serde_json::Value,
) -> Result<PluginInfo, Box<dyn Error>> {
    let document: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(directory.join("IXPlugin.json"))?)?;
    let id = text(document.get("id")).unwrap_or_else(|| {
        directory
            .file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string()
    });
    let version = text(document.get("version")).unwrap_or_else(|| "unknown".to_string());
    let developer_url = text(document.get("homepage"))
        .or_else(|| registry_source_url(registry, &id))
        .unwrap_or_default();
    let dependencies = document
        .get("dependencies")
        .and_then(|value| value.as_object())
        .map(|items| items.keys().cloned().collect())
        .unwrap_or_default();
    Ok(PluginInfo {
        id: id.clone(),
        name: localized(document.get("name")).unwrap_or(id),
        description: localized(document.get("description")).unwrap_or_default(),
        version,
        developer_url,
        scope,
        dependencies,
        update: PluginUpdateStatus::Unchecked,
    })
}

fn text(value: Option<&serde_json::Value>) -> Option<String> {
    value.and_then(|item| item.as_str()).map(str::to_string)
}

fn localized(value: Option<&serde_json::Value>) -> Option<String> {
    let value = value?;
    if let Some(text) = value.as_str() {
        return Some(text.to_string());
    }
    let object = value.as_object()?;
    for language in ["en", "zh", "fr", "ru", "default"] {
        if let Some(text) = object.get(language).and_then(|item| item.as_str()) {
            return Some(text.to_string());
        }
    }
    object
        .values()
        .find_map(|item| item.as_str())
        .map(str::to_string)
}

fn load_registry(root: &Path) -> serde_json::Value {
    fs::read_to_string(root.join("config/plugin_registry.json"))
        .ok()
        .and_then(|content| serde_json::from_str(&content).ok())
        .unwrap_or(serde_json::Value::Null)
}

fn registry_source_url(registry: &serde_json::Value, descriptor_id: &str) -> Option<String> {
    registry
        .get("plugins")?
        .as_object()?
        .values()
        .find_map(|record| {
            if record.get("descriptor_id").and_then(|value| value.as_str()) == Some(descriptor_id) {
                return text(record.get("source_url"));
            }
            None
        })
}

#[derive(Debug, Deserialize)]
pub struct DependencyResult {
    pub plugin_name: String,
    pub success: bool,
    pub detail: String,
    pub missing_dependencies: Vec<String>,
}

#[derive(Debug, Deserialize)]
pub struct PluginUpdateResult {
    pub descriptor_id: String,
    pub latest_version: String,
    pub update_available: bool,
    pub error: String,
}

pub fn parse_dependency_results(json: &str) -> Result<Vec<DependencyResult>, Box<dyn Error>> {
    Ok(serde_json::from_str(json)?)
}

pub fn install_plugin_dependencies(root: &Path) -> Result<Vec<DependencyResult>, Box<dyn Error>> {
    let output = run_backend(root, "install")?;
    parse_dependency_results(&output)
}

pub fn check_plugin_updates(root: &Path) -> Result<Vec<PluginUpdateResult>, Box<dyn Error>> {
    let output = run_backend(root, "check-updates")?;
    Ok(serde_json::from_str(&output)?)
}

fn run_backend(root: &Path, command: &str) -> Result<String, Box<dyn Error>> {
    let python = framework_python(root);
    let output = Command::new(python)
        .args(["-m", "core.plugin.setup_dependency_cli", command, "--root"])
        .arg(root)
        .current_dir(root)
        .output()?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).to_string().into());
    }
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

fn framework_python(root: &Path) -> PathBuf {
    if cfg!(windows) {
        root.join(".venv/Scripts/python.exe")
    } else {
        root.join(".venv/bin/python")
    }
}

pub fn apply_update_results(inventory: &mut PluginInventory, results: Vec<PluginUpdateResult>) {
    for plugin in &mut inventory.plugins {
        let Some(result) = results.iter().find(|item| item.descriptor_id == plugin.id) else {
            continue;
        };
        plugin.update = if !result.error.is_empty() {
            PluginUpdateStatus::Failed(result.error.clone())
        } else if result.update_available {
            PluginUpdateStatus::UpdateAvailable(result.latest_version.clone())
        } else {
            PluginUpdateStatus::UpToDate
        };
    }
}
