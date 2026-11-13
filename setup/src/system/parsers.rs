use super::{DiskInfo, MemoryModule, MonitorInfo};

pub fn parse_lsblk_disks(json: &str) -> Vec<DiskInfo> {
    let Ok(document) = serde_json::from_str::<serde_json::Value>(json) else {
        return Vec::new();
    };
    document
        .get("blockdevices")
        .and_then(|items| items.as_array())
        .map(|items| items.iter().filter_map(parse_disk).collect())
        .unwrap_or_default()
}

fn parse_disk(item: &serde_json::Value) -> Option<DiskInfo> {
    if item.get("type").and_then(|value| value.as_str()) != Some("disk") {
        return None;
    }
    Some(DiskInfo {
        model: item
            .get("model")
            .and_then(|value| value.as_str())
            .unwrap_or("Unknown")
            .to_string(),
        size_bytes: item.get("size").and_then(|value| value.as_u64()),
    })
}

pub fn parse_xrandr_monitors(output: &str) -> Vec<MonitorInfo> {
    output
        .lines()
        .filter_map(|line| {
            let mut parts = line.split_whitespace();
            let name = parts.next()?;
            if parts.next() != Some("connected") {
                return None;
            }
            Some(MonitorInfo {
                name: name.to_string(),
                details: parts.collect::<Vec<_>>().join(" "),
            })
        })
        .collect()
}

pub fn parse_macos_monitors(output: &str) -> Vec<MonitorInfo> {
    let mut monitors = Vec::new();
    let mut current_name = String::new();
    let mut details = Vec::new();
    for line in output.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with("Resolution:") || trimmed.starts_with("UI Looks like:") {
            details.push(trimmed.to_string());
            continue;
        }
        if line.starts_with("        ") && trimmed.ends_with(':') {
            current_name = trimmed.trim_end_matches(':').to_string();
        }
        if trimmed.starts_with("Connection:") || trimmed.starts_with("Display Type:") {
            details.push(trimmed.to_string());
        }
    }
    if !current_name.is_empty() || !details.is_empty() {
        monitors.push(MonitorInfo {
            name: if current_name.is_empty() {
                "Display".to_string()
            } else {
                current_name
            },
            details: details.join(", "),
        });
    }
    monitors
}

pub fn parse_macos_memory(output: &str) -> Vec<MemoryModule> {
    let mut modules = Vec::new();
    let mut current: Option<MemoryModule> = None;
    for line in output.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with("DIMM") || trimmed.starts_with("BANK") {
            if let Some(module) = current.take() {
                modules.push(module);
            }
            current = Some(MemoryModule {
                slot: trimmed.trim_end_matches(':').to_string(),
                ..MemoryModule::default()
            });
            continue;
        }
        let Some(module) = current.as_mut() else {
            continue;
        };
        if let Some(value) = trimmed.strip_prefix("Size:") {
            module.capacity_bytes = parse_capacity(value);
        } else if let Some(value) = trimmed.strip_prefix("Speed:") {
            module.speed_mts = parse_number(value);
        } else if let Some(value) = trimmed.strip_prefix("Manufacturer:") {
            module.manufacturer = value.trim().to_string();
        } else if let Some(value) = trimmed.strip_prefix("Part Number:") {
            module.part_number = value.trim().to_string();
        }
    }
    if let Some(module) = current {
        modules.push(module);
    }
    modules
}

pub fn parse_dmidecode_memory(output: &str) -> Vec<MemoryModule> {
    output
        .split("\n\n")
        .filter_map(|block| {
            if block.contains("No Module Installed") {
                return None;
            }
            let mut module = MemoryModule::default();
            for line in block.lines() {
                let trimmed = line.trim();
                if let Some(value) = trimmed.strip_prefix("Size:") {
                    module.capacity_bytes = parse_capacity(value);
                } else if let Some(value) = trimmed.strip_prefix("Locator:") {
                    module.slot = value.trim().to_string();
                } else if let Some(value) = trimmed.strip_prefix("Speed:") {
                    module.speed_mts = parse_number(value);
                } else if let Some(value) = trimmed.strip_prefix("Manufacturer:") {
                    module.manufacturer = value.trim().to_string();
                } else if let Some(value) = trimmed.strip_prefix("Part Number:") {
                    module.part_number = value.trim().to_string();
                }
            }
            if module.capacity_bytes.is_some() {
                Some(module)
            } else {
                None
            }
        })
        .collect()
}

pub fn parse_macos_storage(output: &str) -> Vec<DiskInfo> {
    output
        .split("\n\n")
        .filter_map(|block| {
            let model = block
                .lines()
                .find_map(|line| line.trim().strip_prefix("Model:"))?;
            let size_bytes = block.lines().find_map(|line| {
                line.trim()
                    .strip_prefix("Capacity:")
                    .and_then(parse_capacity)
            });
            Some(DiskInfo {
                model: model.trim().to_string(),
                size_bytes,
            })
        })
        .collect()
}

fn parse_capacity(value: &str) -> Option<u64> {
    if let Some(start) = value.find('(') {
        let end = value.find(')').unwrap_or(value.len());
        let digits: String = value[start + 1..end]
            .chars()
            .filter(|character| character.is_ascii_digit())
            .collect();
        return digits.parse().ok();
    }
    let mut parts = value.split_whitespace();
    let amount: f64 = parts.next()?.replace(',', "").parse().ok()?;
    let unit = parts.next().unwrap_or("B").to_ascii_lowercase();
    let multiplier = match unit.as_str() {
        "kb" | "kib" => 1024.0,
        "mb" | "mib" => 1024.0 * 1024.0,
        "gb" | "gib" => 1024.0 * 1024.0 * 1024.0,
        "tb" | "tib" => 1024.0 * 1024.0 * 1024.0 * 1024.0,
        _ => 1.0,
    };
    Some((amount * multiplier) as u64)
}

fn parse_number(value: &str) -> Option<u32> {
    value.split_whitespace().next()?.parse().ok()
}
