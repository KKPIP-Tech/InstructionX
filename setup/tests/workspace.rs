use crossterm::event::KeyCode;
use instructionx_setup::app::Page;
use instructionx_setup::github::{FrameworkVersion, ReleaseCatalog};
use instructionx_setup::workspace::Workspace;

fn catalog() -> ReleaseCatalog {
    ReleaseCatalog::from_api(
        vec![
            serde_json::json!({
                "id": 1, "name": "Current", "tag_name": "alpha-v1.1.2",
                "published_at": "2026-02-01T00:00:00Z", "prerelease": true,
                "draft": false, "body": "current", "html_url": "https://example/current"
            }),
            serde_json::json!({
                "id": 2, "name": "Next", "tag_name": "alpha-v1.2.0",
                "published_at": "2026-03-01T00:00:00Z", "prerelease": true,
                "draft": false, "body": "next", "html_url": "https://example/next"
            }),
        ],
        FrameworkVersion::parse("alpha-v1.1.2").unwrap(),
    )
}

#[test]
fn upgrade_page_lists_releases_and_moves_selection() {
    let directory = tempfile::tempdir().unwrap();
    let mut workspace = Workspace::new(directory.path());
    workspace.set_release_catalog(catalog());
    workspace.toggle_region();

    let text = workspace.render(Page::Upgrade);
    assert!(text.contains("Next"));
    assert!(text.contains("Current"));
    assert!(text.contains("current"));
    workspace.handle_key(Page::Upgrade, KeyCode::Down).unwrap();
    assert_eq!(workspace.release_index, 1);
}

#[test]
fn environment_and_plugin_pages_show_real_sections() {
    let directory = tempfile::tempdir().unwrap();
    let workspace = Workspace::new(directory.path());

    let environment = workspace.render(Page::Environment);
    assert!(environment.contains("No package information"));
    let plugins = workspace.render(Page::Plugins);
    assert!(plugins.contains("No plugins found"));
    let install = workspace.render(Page::Install);
    assert!(install.contains("Install InstructionX"));
    assert!(install.contains("Repair InstructionX"));
}
