use std::fs;
use std::path::Path;

use instructionx_setup::actions::{ArchiveAction, ToolPreflight, install_archive};

fn write_version(root: &Path, version: &str) {
    fs::create_dir_all(root.join("core")).unwrap();
    fs::write(
        root.join("core/version.py"),
        format!(
            "VERSION = \"{version}\"\nAPP_VERSION = PluginVersion(VersionType.ALPHA, 1, 1, 2)\n"
        ),
    )
    .unwrap();
}

fn create_framework(root: &Path, version: &str) {
    write_version(root, version);
    fs::write(root.join("main.py"), "old").unwrap();
    fs::write(root.join("pyproject.toml"), "old").unwrap();
    fs::write(root.join("requirements.txt"), "requests\n").unwrap();
}

fn create_archive(root: &Path, version: &str) -> std::path::PathBuf {
    let source = root.join("package/InstructionX-release");
    create_framework(&source, version);
    fs::write(source.join("main.py"), "new").unwrap();
    fs::create_dir_all(source.join("plugin/example")).unwrap();
    fs::write(source.join("plugin/example/new.py"), "new plugin").unwrap();
    fs::create_dir_all(source.join("config")).unwrap();
    fs::write(source.join("config/ignored.json"), "ignored").unwrap();
    let archive = root.join("release.zip");
    let file = fs::File::create(&archive).unwrap();
    let mut zip = zip::ZipWriter::new(file);
    for path in [
        "main.py",
        "pyproject.toml",
        "requirements.txt",
        "core/version.py",
        "plugin/example/new.py",
        "config/ignored.json",
    ] {
        zip.start_file(
            format!("InstructionX-release/{path}"),
            zip::write::SimpleFileOptions::default(),
        )
        .unwrap();
        std::io::Write::write_all(&mut zip, &fs::read(source.join(path)).unwrap()).unwrap();
    }
    zip.finish().unwrap();
    archive
}

#[test]
fn install_preserves_user_directories_and_extra_files() {
    let directory = tempfile::tempdir().unwrap();
    let root = directory.path();
    let archive = create_archive(root, "1.2.0");
    for name in ["config", "data", "plugin", "custom_plugin"] {
        fs::create_dir_all(root.join(name)).unwrap();
        fs::write(root.join(name).join("sentinel.txt"), "keep").unwrap();
    }

    let report = install_archive(&archive, root, ArchiveAction::Install, || Ok(())).unwrap();

    assert!(report.copied_files > 0);
    assert_eq!(fs::read_to_string(root.join("main.py")).unwrap(), "new");
    assert!(!root.join("plugin/example/new.py").exists());
    assert!(!root.join("config/ignored.json").exists());
    for name in ["config", "data", "plugin", "custom_plugin"] {
        assert_eq!(
            fs::read_to_string(root.join(name).join("sentinel.txt")).unwrap(),
            "keep"
        );
    }
}

#[test]
fn repair_rolls_back_when_environment_configuration_fails() {
    let directory = tempfile::tempdir().unwrap();
    let root = directory.path();
    create_framework(root, "1.1.2");
    fs::write(root.join("extra.txt"), "keep").unwrap();
    let archive = create_archive(root, "1.1.2");

    let result = install_archive(&archive, root, ArchiveAction::Repair, || {
        Err("simulated uv failure".into())
    });

    assert!(result.is_err());
    assert_eq!(fs::read_to_string(root.join("main.py")).unwrap(), "old");
    assert_eq!(fs::read_to_string(root.join("extra.txt")).unwrap(), "keep");
}

#[test]
fn preflight_reports_each_missing_tool() {
    let preflight = ToolPreflight::detect_with(|name| name == "uv");
    assert!(!preflight.git_present);
    assert!(preflight.uv_present);
    assert_eq!(preflight.missing_tools(), vec!["git"]);
}

#[test]
fn current_version_ignores_docstrings_and_type_map() {
    let directory = tempfile::tempdir().unwrap();
    let root = directory.path();
    fs::create_dir_all(root.join("core")).unwrap();
    fs::write(
        root.join("core/version.py"),
        "\"\"\"VERSION is documented. VersionType.BETA is a mapping key.\"\"\"\n\
         VERSION = \"1.1.2\"\n\
         APP_VERSION = PluginVersion(VersionType.ALPHA, 1, 1, 2)\n",
    )
    .unwrap();

    let version = instructionx_setup::actions::current_framework_version(root).unwrap();

    assert_eq!(version.to_string(), "alpha.1.1.2");
}
