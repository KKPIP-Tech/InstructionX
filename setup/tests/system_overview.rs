use std::fs;
use std::io::{Read, Write};
use std::net::TcpListener;

use instructionx_setup::system::parsers::{
    parse_dmidecode_memory, parse_lsblk_disks, parse_macos_memory, parse_macos_storage,
    parse_xrandr_monitors,
};
use instructionx_setup::system::{FrameworkStatus, SystemOverview, fetch_public_ip_with_url};

#[test]
fn framework_detection_uses_real_markers_and_version() {
    let directory = tempfile::tempdir().unwrap();
    let root = directory.path();
    assert!(!FrameworkStatus::detect(root).installed);
    fs::create_dir_all(root.join("core")).unwrap();
    fs::write(root.join("main.py"), "").unwrap();
    fs::write(root.join("pyproject.toml"), "").unwrap();
    fs::write(root.join("core/version.py"), "VERSION = \"1.1.2\"\n").unwrap();
    fs::create_dir(root.join(".git")).unwrap();
    fs::create_dir(root.join(".venv")).unwrap();

    let status = FrameworkStatus::detect(root);
    assert!(status.installed);
    assert!(status.git_present);
    assert!(status.venv_present);
    assert_eq!(status.version.as_deref(), Some("1.1.2"));
}

#[test]
fn collects_real_local_system_information() {
    let directory = tempfile::tempdir().unwrap();
    let overview = SystemOverview::collect(directory.path());

    assert!(!overview.os_name.is_empty());
    assert!(!overview.cpu_model.is_empty());
    assert!(overview.memory_total_bytes > 0);
    assert!(!overview.volumes.is_empty());
    assert!(overview.tui_path.is_absolute());
}

#[test]
fn public_ip_is_validated_and_fetched_only_when_called() {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let worker = std::thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        let mut buffer = [0_u8; 1024];
        let _ = stream.read(&mut buffer);
        let body = "203.0.113.42";
        let response = format!(
            "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
            body.len(),
            body
        );
        stream.write_all(response.as_bytes()).unwrap();
    });

    let ip = fetch_public_ip_with_url(&format!("http://{address}/ip")).unwrap();
    assert_eq!(ip, "203.0.113.42");
    worker.join().unwrap();
}

#[test]
fn parses_linux_disks_and_monitors() {
    let disks = parse_lsblk_disks(
        r#"{"blockdevices":[{"name":"nvme0n1","model":"Example NVMe","size":1000204886016,"type":"disk"}]}"#,
    );
    assert_eq!(disks.len(), 1);
    assert_eq!(disks[0].model, "Example NVMe");
    assert_eq!(disks[0].size_bytes, Some(1000204886016));

    let monitors =
        parse_xrandr_monitors("DP-1 connected primary 2560x1440+0+0 59.95\nHDMI-1 disconnected");
    assert_eq!(monitors.len(), 1);
    assert!(monitors[0].details.contains("2560x1440"));
    assert!(monitors[0].details.contains("59.95"));
}

#[test]
fn parses_macos_and_linux_hardware_details() {
    let memory = parse_macos_memory(
        "DIMM1:\n  Size: 16 GB\n  Speed: 6400 MT/s\n  Manufacturer: Example\n  Part Number: ABC-16\n",
    );
    assert_eq!(memory.len(), 1);
    assert_eq!(memory[0].manufacturer, "Example");
    assert_eq!(memory[0].part_number, "ABC-16");
    assert_eq!(memory[0].capacity_bytes, Some(16 * 1024 * 1024 * 1024));

    let disks =
        parse_macos_storage("Model: Example SSD\nCapacity: 1 TB (1,000,000,000,000 bytes)\n");
    assert_eq!(disks[0].model, "Example SSD");
    assert_eq!(disks[0].size_bytes, Some(1_000_000_000_000));

    let modules = parse_dmidecode_memory(
        "Memory Device\n  Size: 16 GB\n  Locator: DIMM1\n  Speed: 6400 MT/s\n  Manufacturer: Example\n  Part Number: ABC-16\n",
    );
    assert_eq!(modules.len(), 1);
    assert_eq!(modules[0].slot, "DIMM1");
    assert_eq!(modules[0].speed_mts, Some(6400));
}
