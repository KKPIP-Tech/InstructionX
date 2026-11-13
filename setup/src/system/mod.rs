pub mod native;
pub mod parsers;

use std::error::Error;
use std::fs;
use std::net::IpAddr;
use std::path::{Path, PathBuf};
use std::time::Duration;

use sysinfo::{Disks, Networks, System};

#[derive(Debug, Clone, Default)]
pub struct MemoryModule {
    pub capacity_bytes: Option<u64>,
    pub manufacturer: String,
    pub part_number: String,
    pub speed_mts: Option<u32>,
    pub slot: String,
}

#[derive(Debug, Clone, Default)]
pub struct DiskInfo {
    pub model: String,
    pub size_bytes: Option<u64>,
}

#[derive(Debug, Clone)]
pub struct VolumeInfo {
    pub mount_point: String,
    pub file_system: String,
    pub total_bytes: u64,
    pub available_bytes: u64,
}

#[derive(Debug, Clone, Default)]
pub struct MonitorInfo {
    pub name: String,
    pub details: String,
}

#[derive(Debug, Clone, Default)]
pub struct NetworkInfo {
    pub name: String,
    pub mac_address: String,
    pub ip_addresses: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct FrameworkStatus {
    pub root: PathBuf,
    pub installed: bool,
    pub git_present: bool,
    pub uv_present: bool,
    pub venv_present: bool,
    pub version: Option<String>,
}

impl FrameworkStatus {
    pub fn detect(root: &Path) -> Self {
        let installed = root.join("main.py").is_file()
            && root.join("core/version.py").is_file()
            && root.join("pyproject.toml").is_file();
        Self {
            root: root.to_path_buf(),
            installed,
            git_present: root.join(".git").exists(),
            uv_present: executable_exists("uv"),
            venv_present: root.join(".venv").exists(),
            version: read_framework_version(root),
        }
    }
}

#[derive(Debug, Clone)]
pub struct SystemOverview {
    pub os_name: String,
    pub os_version: String,
    pub kernel_version: String,
    pub host_name: String,
    pub architecture: String,
    pub cpu_model: String,
    pub physical_cores: Option<usize>,
    pub logical_cores: usize,
    pub memory_total_bytes: u64,
    pub memory_available_bytes: u64,
    pub memory_modules: Vec<MemoryModule>,
    pub disks: Vec<DiskInfo>,
    pub volumes: Vec<VolumeInfo>,
    pub monitors: Vec<MonitorInfo>,
    pub networks: Vec<NetworkInfo>,
    pub tui_path: PathBuf,
    pub framework: FrameworkStatus,
    pub warnings: Vec<String>,
}

impl SystemOverview {
    pub fn collect(root: &Path) -> Self {
        let mut system = System::new_all();
        system.refresh_all();
        let cpu_model = cpu_model(&system);
        let volumes = collect_volumes();
        let networks = collect_networks();
        let tui_path = std::env::current_exe().unwrap_or_else(|_| root.to_path_buf());
        let mut warnings = Vec::new();
        let memory_modules =
            with_warning(native::memory_modules(), "memory modules", &mut warnings);
        let disks = with_warning(native::physical_disks(), "physical disks", &mut warnings);
        let monitors = with_warning(native::monitors(), "monitors", &mut warnings);
        Self {
            os_name: System::name().unwrap_or_else(|| std::env::consts::OS.to_string()),
            os_version: System::os_version().unwrap_or_else(|| "Unknown".to_string()),
            kernel_version: System::kernel_version().unwrap_or_else(|| "Unknown".to_string()),
            host_name: System::host_name().unwrap_or_else(|| "Unknown".to_string()),
            architecture: System::cpu_arch(),
            cpu_model,
            physical_cores: system.physical_core_count(),
            logical_cores: system.cpus().len(),
            memory_total_bytes: system.total_memory(),
            memory_available_bytes: system.available_memory(),
            memory_modules,
            disks,
            volumes,
            monitors,
            networks,
            tui_path,
            framework: FrameworkStatus::detect(root),
            warnings,
        }
    }
}

fn cpu_model(system: &System) -> String {
    system
        .cpus()
        .first()
        .map(|cpu| cpu.brand().trim().to_string())
        .filter(|brand| !brand.is_empty())
        .unwrap_or_else(|| "Unknown".to_string())
}

fn collect_volumes() -> Vec<VolumeInfo> {
    Disks::new_with_refreshed_list()
        .list()
        .iter()
        .map(|disk| VolumeInfo {
            mount_point: disk.mount_point().display().to_string(),
            file_system: disk.file_system().to_string_lossy().to_string(),
            total_bytes: disk.total_space(),
            available_bytes: disk.available_space(),
        })
        .collect()
}

fn collect_networks() -> Vec<NetworkInfo> {
    Networks::new_with_refreshed_list()
        .iter()
        .map(|(name, data)| NetworkInfo {
            name: name.to_string(),
            mac_address: data.mac_address().to_string(),
            ip_addresses: data
                .ip_networks()
                .iter()
                .map(|network| network.addr.to_string())
                .collect(),
        })
        .collect()
}

fn with_warning<T>(
    result: Result<Vec<T>, String>,
    component: &str,
    warnings: &mut Vec<String>,
) -> Vec<T> {
    result.unwrap_or_else(|error| {
        warnings.push(format!("{component}: {error}"));
        Vec::new()
    })
}

pub fn fetch_public_ip_with_url(url: &str) -> Result<String, Box<dyn Error>> {
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(8))
        .user_agent("InstructionX-Setup")
        .build()?;
    let response = client.get(url).send()?.error_for_status()?;
    let address = response.text()?.trim().to_string();
    address.parse::<IpAddr>()?;
    Ok(address)
}

fn read_framework_version(root: &Path) -> Option<String> {
    let content = fs::read_to_string(root.join("core/version.py")).ok()?;
    content.lines().find_map(|line| {
        let value = line
            .trim()
            .strip_prefix("VERSION")?
            .split('=')
            .nth(1)?
            .trim();
        Some(
            value
                .trim_matches(|character| character == '"' || character == '\'')
                .to_string(),
        )
    })
}

fn executable_exists(name: &str) -> bool {
    let Some(paths) = std::env::var_os("PATH") else {
        return false;
    };
    let extensions: Vec<String> = if cfg!(windows) {
        std::env::var("PATHEXT")
            .unwrap_or_else(|_| ".EXE;.CMD;.BAT".to_string())
            .split(';')
            .map(|item| item.to_ascii_lowercase())
            .collect()
    } else {
        vec![String::new()]
    };
    std::env::split_paths(&paths).any(|directory| {
        extensions
            .iter()
            .any(|extension| directory.join(format!("{name}{extension}")).is_file())
    })
}
