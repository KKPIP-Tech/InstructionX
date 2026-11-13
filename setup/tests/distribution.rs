use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use sha2::{Digest, Sha256};

const BUNDLED_ASSETS: &[&str] = &[
    "instructionx-setup-windows-x86_64.exe",
    "instructionx-setup-windows-aarch64.exe",
];
const FUTURE_ASSETS: &[&str] = &[
    "instructionx-setup-macos-x86_64",
    "instructionx-setup-macos-aarch64",
    "instructionx-setup-linux-x86_64",
    "instructionx-setup-linux-aarch64",
];
const MACHINE_X64: u16 = 0x8664;
const MACHINE_ARM64: u16 = 0xaa64;

fn project_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .to_path_buf()
}

fn asset_path(asset: &str) -> PathBuf {
    project_root().join("tools/setup").join(asset)
}

fn read_u16(bytes: &[u8], offset: usize) -> u16 {
    u16::from_le_bytes(bytes[offset..offset + 2].try_into().unwrap())
}

fn read_u32(bytes: &[u8], offset: usize) -> u32 {
    u32::from_le_bytes(bytes[offset..offset + 4].try_into().unwrap())
}

fn assert_pe_architecture(asset: &str, bytes: &[u8]) {
    assert_eq!(&bytes[..2], b"MZ");
    let pe = read_u32(bytes, 0x3c) as usize;
    assert_eq!(&bytes[pe..pe + 4], b"PE\0\0");
    let expected = if asset.contains("aarch64") {
        MACHINE_ARM64
    } else {
        MACHINE_X64
    };
    assert_eq!(read_u16(bytes, pe + 4), expected, "wrong PE architecture");
}

#[test]
fn release_archive_contains_both_windows_native_setups() {
    for asset in BUNDLED_ASSETS {
        let path = asset_path(asset);
        let bytes = fs::read(&path).unwrap_or_else(|error| panic!("{}: {error}", path.display()));
        assert_pe_architecture(asset, &bytes);
    }
}

#[test]
fn bundled_checksums_cover_both_windows_binaries_and_match_content() {
    let checksums = fs::read_to_string(project_root().join("tools/setup/SHA256SUMS")).unwrap();
    let expected: BTreeMap<&str, &str> = checksums
        .lines()
        .filter_map(|line| line.split_once("  "))
        .map(|(hash, name)| (name, hash))
        .collect();
    assert_eq!(expected.len(), BUNDLED_ASSETS.len());
    for asset in BUNDLED_ASSETS {
        let actual = format!("{:x}", Sha256::digest(fs::read(asset_path(asset)).unwrap()));
        assert_eq!(expected.get(asset), Some(&actual.as_str()));
    }
}

#[test]
fn windows_launcher_selects_os_architecture_without_downloading() {
    let script = fs::read_to_string(project_root().join("setup.ps1")).unwrap();
    assert!(script.contains("RuntimeInformation"));
    assert!(script.contains("tools\\setup"));
    for asset in BUNDLED_ASSETS {
        assert!(script.contains(asset));
    }
    for forbidden in ["Invoke-RestMethod", "Invoke-WebRequest", "Get-NativeSetup"] {
        assert!(!script.contains(forbidden));
    }
}

#[test]
fn windows_build_script_supports_reproducible_local_cross_compilation() {
    let script = fs::read_to_string(project_root().join("setup/build_windows.ps1")).unwrap();
    for expected in [
        "x86_64-pc-windows-msvc",
        "aarch64-pc-windows-gnullvm",
        "CARGO_TARGET_AARCH64_PC_WINDOWS_GNULLVM_LINKER",
        "Resolve-LlvmMingw",
        "Assert-PeArchitecture",
        "Write-SetupChecksums",
    ] {
        assert!(script.contains(expected));
    }
    assert!(script.contains("SHA256"));
}

#[test]
fn unix_launcher_preserves_future_targets_without_downloading() {
    let script = fs::read_to_string(project_root().join("setup.sh")).unwrap();
    assert!(script.contains("tools/setup"));
    for asset in FUTURE_ASSETS {
        assert!(script.contains(asset));
    }
    for forbidden in ["curl", "download_native_setup", "API_URL"] {
        assert!(!script.contains(forbidden));
    }
}
