use std::error::Error;
use std::fmt;
use std::fs;
use std::io;
use std::path::Path;

use chrono::{DateTime, Utc};
use serde::Deserialize;
use sha2::{Digest, Sha256};

const RELEASES_PER_PAGE: usize = 100;
const REPOSITORY_RELEASES_PATH: &str = "/repos/KKPIP-Tech/InstructionX/releases";
const ARCHIVE_BASE_URL: &str = "https://codeload.github.com/KKPIP-Tech/InstructionX/zip/refs/tags";

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum ReleaseChannel {
    Internal,
    Alpha,
    Beta,
    PreRelease,
    Release,
}

impl ReleaseChannel {
    fn parse(value: &str) -> Result<Self, String> {
        match value {
            "internal" => Ok(Self::Internal),
            "alpha" => Ok(Self::Alpha),
            "beta" => Ok(Self::Beta),
            "pre-release" => Ok(Self::PreRelease),
            "release" => Ok(Self::Release),
            _ => Err(format!("Invalid release channel: {value}")),
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::Internal => "internal",
            Self::Alpha => "alpha",
            Self::Beta => "beta",
            Self::PreRelease => "pre-release",
            Self::Release => "release",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct FrameworkVersion {
    channel: ReleaseChannel,
    major: u64,
    minor: u64,
    patch: u64,
}

impl FrameworkVersion {
    pub fn parse(tag: &str) -> Result<Self, String> {
        let (channel_name, numbers) = if let Some(value) = tag.strip_prefix('v') {
            ("release", value)
        } else {
            tag.split_once("-v")
                .ok_or_else(|| format!("Invalid Release Tag: {tag}"))?
        };
        let parts: Vec<_> = numbers.split('.').collect();
        if parts.len() != 3 {
            return Err(format!("Invalid Release Tag: {tag}"));
        }
        let parse_number = |part: &str| {
            part.parse::<u64>()
                .map_err(|_| format!("Invalid Release Tag: {tag}"))
        };
        Ok(Self {
            channel: ReleaseChannel::parse(channel_name)?,
            major: parse_number(parts[0])?,
            minor: parse_number(parts[1])?,
            patch: parse_number(parts[2])?,
        })
    }
}

impl fmt::Display for FrameworkVersion {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "{}.{}.{}.{}",
            self.channel.as_str(),
            self.major,
            self.minor,
            self.patch
        )
    }
}

#[derive(Debug, Clone)]
pub struct Release {
    pub id: u64,
    pub name: String,
    pub tag_name: String,
    pub version: Option<FrameworkVersion>,
    pub prerelease: bool,
    pub published_at: DateTime<Utc>,
    pub body: String,
    pub html_url: String,
}

impl Release {
    fn from_api(value: serde_json::Value) -> Self {
        let tag_name = value
            .get("tag_name")
            .and_then(|item| item.as_str())
            .unwrap_or("")
            .to_string();
        let published_at = parse_time(value.get("published_at").and_then(|item| item.as_str()))
            .or_else(|| parse_time(value.get("created_at").and_then(|item| item.as_str())))
            .unwrap_or(DateTime::UNIX_EPOCH);
        Self {
            id: value
                .get("id")
                .and_then(|item| item.as_u64())
                .unwrap_or_default(),
            name: api_text(&value, "name", &tag_name),
            version: FrameworkVersion::parse(&tag_name).ok(),
            tag_name,
            prerelease: value
                .get("prerelease")
                .and_then(|item| item.as_bool())
                .unwrap_or(false),
            published_at,
            body: api_text(&value, "body", ""),
            html_url: api_text(&value, "html_url", ""),
        }
    }
}

fn api_text(value: &serde_json::Value, key: &str, default: &str) -> String {
    value
        .get(key)
        .and_then(|item| item.as_str())
        .unwrap_or(default)
        .to_string()
}

#[derive(Debug, Clone)]
pub struct ReleaseCatalog {
    pub releases: Vec<Release>,
    pub current_release_id: Option<u64>,
    pub current_version: FrameworkVersion,
}

impl ReleaseCatalog {
    pub fn from_api(values: Vec<serde_json::Value>, current_version: FrameworkVersion) -> Self {
        let mut releases: Vec<_> = values
            .into_iter()
            .filter(|value| {
                !value
                    .get("draft")
                    .and_then(|item| item.as_bool())
                    .unwrap_or(false)
            })
            .map(Release::from_api)
            .collect();
        releases.sort_by_key(|release| (release.published_at, release.id));
        releases.reverse();
        let current_release_id = releases
            .iter()
            .find(|release| release.version == Some(current_version))
            .map(|release| release.id);
        Self {
            releases,
            current_release_id,
            current_version,
        }
    }

    pub fn latest(&self) -> Option<&Release> {
        self.releases.first()
    }

    pub fn latest_is_update(&self) -> bool {
        self.latest()
            .is_some_and(|release| self.can_update(release.id))
    }

    pub fn can_update(&self, release_id: u64) -> bool {
        self.releases
            .iter()
            .find(|release| release.id == release_id)
            .and_then(|release| release.version)
            .is_some_and(|version| version > self.current_version)
    }
}

fn parse_time(value: Option<&str>) -> Option<DateTime<Utc>> {
    DateTime::parse_from_rfc3339(value?)
        .ok()
        .map(|time| time.with_timezone(&Utc))
}

pub struct ReleaseClient {
    client: reqwest::blocking::Client,
    api_base_url: String,
}

impl ReleaseClient {
    pub fn new(api_base_url: &str) -> Result<Self, Box<dyn Error>> {
        let client = reqwest::blocking::Client::builder()
            .user_agent("InstructionX-Setup")
            .build()?;
        Ok(Self {
            client,
            api_base_url: api_base_url.trim_end_matches('/').to_string(),
        })
    }

    pub fn list_all_releases(
        &self,
        current: FrameworkVersion,
    ) -> Result<ReleaseCatalog, Box<dyn Error>> {
        let mut page = 1;
        let mut values = Vec::new();
        loop {
            let url = format!("{}{}", self.api_base_url, REPOSITORY_RELEASES_PATH);
            let response = self
                .client
                .get(url)
                .query(&[("per_page", RELEASES_PER_PAGE), ("page", page)])
                .send()?
                .error_for_status()?;
            let items: Vec<serde_json::Value> = response.json()?;
            let count = items.len();
            values.extend(items);
            if count < RELEASES_PER_PAGE {
                return Ok(ReleaseCatalog::from_api(values, current));
            }
            page += 1;
        }
    }

    pub fn download_archive(
        &self,
        tag: &str,
        destination: &Path,
    ) -> Result<String, Box<dyn Error>> {
        let encoded: String = url::form_urlencoded::byte_serialize(tag.as_bytes()).collect();
        let response = self
            .client
            .get(format!("{ARCHIVE_BASE_URL}/{encoded}"))
            .send()?
            .error_for_status()?;
        if let Some(parent) = destination.parent() {
            fs::create_dir_all(parent)?;
        }
        let temporary = destination.with_extension("download");
        let mut file = fs::File::create(&temporary)?;
        let mut response = response;
        io::copy(&mut response, &mut file)?;
        fs::rename(temporary, destination)?;
        Ok(format!("{:x}", Sha256::digest(fs::read(destination)?)))
    }
}

#[derive(Debug, Deserialize)]
pub struct ReleaseAsset {
    pub name: String,
    pub browser_download_url: String,
}
