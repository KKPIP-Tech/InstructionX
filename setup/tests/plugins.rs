use std::fs;

use instructionx_setup::plugins::{PluginInventory, PluginScope, PluginUpdateStatus};

#[test]
fn loads_official_and_third_party_plugins_with_localized_fields() {
    let directory = tempfile::tempdir().unwrap();
    let root = directory.path();
    let official = root.join("plugin/demo");
    fs::create_dir_all(&official).unwrap();
    fs::write(
        official.join("IXPlugin.json"),
        r#"{
        "id":"demo",
        "name":{"en":"Demo","zh":"演示"},
        "description":{"en":"Description"},
        "version":"release.1.0.0",
        "homepage":"https://github.com/example/demo",
        "dependencies":{"requests":">=2.0"}
    }"#,
    )
    .unwrap();
    let custom = root.join("custom_plugin/community");
    fs::create_dir_all(&custom).unwrap();
    fs::write(
        custom.join("IXPlugin.json"),
        r#"{
        "id":"community",
        "name":"Community",
        "description":"Third party",
        "version":"release.0.9.0"
    }"#,
    )
    .unwrap();

    let inventory = PluginInventory::load(root).unwrap();

    assert_eq!(inventory.plugins.len(), 2);
    assert_eq!(inventory.plugins[0].scope, PluginScope::Official);
    assert_eq!(inventory.plugins[0].name, "Demo");
    assert_eq!(
        inventory.plugins[0].developer_url,
        "https://github.com/example/demo"
    );
    assert_eq!(inventory.plugins[0].dependencies.len(), 1);
    assert_eq!(inventory.plugins[1].scope, PluginScope::ThirdParty);
    assert!(matches!(
        inventory.plugins[0].update,
        PluginUpdateStatus::Unchecked
    ));
}

#[test]
fn parses_dependency_results_from_framework_backend() {
    let directory = tempfile::tempdir().unwrap();
    let root = directory.path();
    let plugin = root.join("plugin/demo");
    fs::create_dir_all(&plugin).unwrap();
    fs::write(
        plugin.join("IXPlugin.json"),
        r#"{
        "id":"demo","name":"Demo","version":"release.1.0.0"
    }"#,
    )
    .unwrap();
    let inventory = PluginInventory::load(root).unwrap();
    let results = instructionx_setup::plugins::parse_dependency_results(
        r#"[{"plugin_name":"demo","success":false,"detail":"bad","missing_dependencies":["bad-package"]}]"#,
    ).unwrap();

    assert_eq!(inventory.plugins.len(), 1);
    assert_eq!(results.len(), 1);
    assert!(!results[0].success);
    assert_eq!(results[0].missing_dependencies, ["bad-package"]);
}
