use super::{DiskInfo, MemoryModule, MonitorInfo};

#[cfg(windows)]
pub fn memory_modules() -> Result<Vec<MemoryModule>, String> {
    windows::memory_modules()
}

#[cfg(windows)]
pub fn physical_disks() -> Result<Vec<DiskInfo>, String> {
    windows::physical_disks()
}

#[cfg(windows)]
pub fn monitors() -> Result<Vec<MonitorInfo>, String> {
    windows::monitors()
}

#[cfg(target_os = "macos")]
pub fn memory_modules() -> Result<Vec<MemoryModule>, String> {
    let output = std::process::Command::new("system_profiler")
        .arg("SPMemoryDataType")
        .output()
        .map_err(|error| error.to_string())?;
    Ok(super::parsers::parse_macos_memory(
        &String::from_utf8_lossy(&output.stdout),
    ))
}

#[cfg(target_os = "macos")]
pub fn physical_disks() -> Result<Vec<DiskInfo>, String> {
    let output = std::process::Command::new("system_profiler")
        .arg("SPStorageDataType")
        .output()
        .map_err(|error| error.to_string())?;
    Ok(super::parsers::parse_macos_storage(
        &String::from_utf8_lossy(&output.stdout),
    ))
}

#[cfg(target_os = "macos")]
pub fn monitors() -> Result<Vec<MonitorInfo>, String> {
    let output = std::process::Command::new("system_profiler")
        .arg("SPDisplaysDataType")
        .output()
        .map_err(|error| error.to_string())?;
    Ok(super::parsers::parse_macos_monitors(
        &String::from_utf8_lossy(&output.stdout),
    ))
}

#[cfg(target_os = "linux")]
pub fn memory_modules() -> Result<Vec<MemoryModule>, String> {
    let output = std::process::Command::new("dmidecode")
        .args(["-t", "memory"])
        .output()
        .map_err(|error| error.to_string())?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).to_string());
    }
    Ok(super::parsers::parse_dmidecode_memory(
        &String::from_utf8_lossy(&output.stdout),
    ))
}

#[cfg(target_os = "linux")]
pub fn physical_disks() -> Result<Vec<DiskInfo>, String> {
    let output = std::process::Command::new("lsblk")
        .args(["-J", "-b", "-o", "NAME,MODEL,SIZE,TYPE"])
        .output()
        .map_err(|error| error.to_string())?;
    Ok(super::parsers::parse_lsblk_disks(&String::from_utf8_lossy(
        &output.stdout,
    )))
}

#[cfg(target_os = "linux")]
pub fn monitors() -> Result<Vec<MonitorInfo>, String> {
    let output = std::process::Command::new("xrandr")
        .arg("--current")
        .output()
        .map_err(|error| error.to_string())?;
    Ok(super::parsers::parse_xrandr_monitors(
        &String::from_utf8_lossy(&output.stdout),
    ))
}

#[cfg(windows)]
mod windows {
    #![allow(non_camel_case_types)]

    use serde::Deserialize;
    use wmi::{COMLibrary, WMIConnection};

    use super::{DiskInfo, MemoryModule, MonitorInfo};

    #[derive(Deserialize)]
    #[serde(rename_all = "PascalCase")]
    struct Win32_PhysicalMemory {
        capacity: Option<u64>,
        manufacturer: Option<String>,
        part_number: Option<String>,
        speed: Option<u32>,
        device_locator: Option<String>,
    }

    #[derive(Deserialize)]
    #[serde(rename_all = "PascalCase")]
    struct Win32_DiskDrive {
        model: Option<String>,
        size: Option<u64>,
    }

    #[derive(Deserialize)]
    #[serde(rename_all = "PascalCase")]
    struct Win32_VideoController {
        name: Option<String>,
        current_horizontal_resolution: Option<u32>,
        current_vertical_resolution: Option<u32>,
        current_refresh_rate: Option<u32>,
    }

    fn connection() -> Result<WMIConnection, String> {
        WMIConnection::new(COMLibrary::new().map_err(|error| error.to_string())?)
            .map_err(|error| error.to_string())
    }

    pub fn memory_modules() -> Result<Vec<MemoryModule>, String> {
        let records = connection()?
            .query::<Win32_PhysicalMemory>()
            .map_err(|error| error.to_string())?;
        Ok(records
            .into_iter()
            .map(|record| MemoryModule {
                capacity_bytes: record.capacity,
                manufacturer: record.manufacturer.unwrap_or_else(|| "Unknown".to_string()),
                part_number: record.part_number.unwrap_or_else(|| "Unknown".to_string()),
                speed_mts: record.speed,
                slot: record
                    .device_locator
                    .unwrap_or_else(|| "Unknown".to_string()),
            })
            .collect())
    }

    pub fn physical_disks() -> Result<Vec<DiskInfo>, String> {
        let records = connection()?
            .query::<Win32_DiskDrive>()
            .map_err(|error| error.to_string())?;
        Ok(records
            .into_iter()
            .map(|record| DiskInfo {
                model: record.model.unwrap_or_else(|| "Unknown".to_string()),
                size_bytes: record.size,
            })
            .collect())
    }

    pub fn monitors() -> Result<Vec<MonitorInfo>, String> {
        let records = connection()?
            .query::<Win32_VideoController>()
            .map_err(|error| error.to_string())?;
        Ok(records
            .into_iter()
            .filter(|record| {
                record.current_horizontal_resolution.unwrap_or_default() > 0
                    && record.current_vertical_resolution.unwrap_or_default() > 0
            })
            .map(|record| MonitorInfo {
                name: record.name.unwrap_or_else(|| "Display".to_string()),
                details: format!(
                    "{}x{} @ {}Hz",
                    record.current_horizontal_resolution.unwrap_or_default(),
                    record.current_vertical_resolution.unwrap_or_default(),
                    record.current_refresh_rate.unwrap_or_default()
                ),
            })
            .collect())
    }
}
