use instructionx_setup::github::{FrameworkVersion, ReleaseCatalog};

fn release(id: u64, tag: &str, date: &str, prerelease: bool, draft: bool) -> serde_json::Value {
    serde_json::json!({
        "id": id,
        "name": format!("Release {id}"),
        "tag_name": tag,
        "published_at": date,
        "created_at": date,
        "prerelease": prerelease,
        "draft": draft,
        "body": format!("Notes {id}"),
        "html_url": format!("https://github.com/KKPIP-Tech/InstructionX/releases/{id}")
    })
}

#[test]
fn parses_and_compares_framework_versions() {
    assert_eq!(
        FrameworkVersion::parse("alpha-v1.2.3").unwrap().to_string(),
        "alpha.1.2.3"
    );
    assert_eq!(
        FrameworkVersion::parse("v1.2.3").unwrap().to_string(),
        "release.1.2.3"
    );
    assert!(
        FrameworkVersion::parse("alpha-v1.10.0").unwrap()
            > FrameworkVersion::parse("alpha-v1.2.0").unwrap()
    );
    assert!(
        FrameworkVersion::parse("release-v1.0.0").unwrap()
            > FrameworkVersion::parse("alpha-v9.0.0").unwrap()
    );
    assert!(FrameworkVersion::parse("nightly").is_err());
}

#[test]
fn catalog_sorts_by_publish_time_and_marks_current() {
    let catalog = ReleaseCatalog::from_api(
        vec![
            release(1, "alpha-v1.1.2", "2026-02-01T00:00:00Z", true, false),
            release(2, "alpha-v1.0.0", "2026-03-01T00:00:00Z", true, false),
            release(3, "alpha-v1.2.0", "2026-01-01T00:00:00Z", true, false),
            release(4, "alpha-v9.0.0", "2026-04-01T00:00:00Z", true, true),
            release(5, "nightly", "2026-05-01T00:00:00Z", true, false),
        ],
        FrameworkVersion::parse("alpha-v1.1.2").unwrap(),
    );

    assert_eq!(
        catalog
            .releases
            .iter()
            .map(|item| item.id)
            .collect::<Vec<_>>(),
        [5, 2, 1, 3]
    );
    assert_eq!(catalog.current_release_id, Some(1));
    assert_eq!(catalog.latest().unwrap().id, 5);
    assert!(!catalog.latest_is_update());
    assert!(catalog.can_update(3));
    assert!(!catalog.can_update(1));
}
