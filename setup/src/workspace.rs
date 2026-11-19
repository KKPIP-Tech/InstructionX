use std::collections::BTreeSet;
use std::error::Error;
use std::fmt::Write as _;
use std::fs;
use std::path::{Path, PathBuf};

use crossterm::event::{KeyCode, KeyEvent};

use crate::actions::{ArchiveAction, ToolPreflight};
use crate::app::Page;
use crate::github::{Release, ReleaseCatalog};
use crate::operations::{
    OperationData, OperationEvent, OperationRequest, OperationSuccess, OperationUpdate,
    RunningOperation,
};
use crate::plugins::{DependencyResult, PluginInventory, PluginUpdateStatus, apply_update_results};
use crate::uv::PackageInfo;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum PendingAction {
    Install,
    Repair,
    Upgrade,
    CheckUpdates,
    UpdatePackages,
    RemovePackages,
    RebuildEnvironment,
    QueryPackages,
    RefreshPlugins,
    CheckPluginUpdates,
    InstallPluginDependencies,
    CreateShortcut,
    ChangeLanguage,
    InstallGit,
    InstallUv,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WorkspaceRegion {
    Actions,
    Data,
}

#[derive(Clone, Copy)]
struct ActionItem {
    label_key: &'static str,
    action: PendingAction,
}

const INSTALL_ACTIONS: &[ActionItem] = &[
    ActionItem {
        label_key: "action.install",
        action: PendingAction::Install,
    },
    ActionItem {
        label_key: "action.repair",
        action: PendingAction::Repair,
    },
    ActionItem {
        label_key: "action.check_releases",
        action: PendingAction::CheckUpdates,
    },
];
const ENVIRONMENT_ACTIONS: &[ActionItem] = &[
    ActionItem {
        label_key: "action.query_packages",
        action: PendingAction::QueryPackages,
    },
    ActionItem {
        label_key: "action.update_selected",
        action: PendingAction::UpdatePackages,
    },
    ActionItem {
        label_key: "action.remove_selected",
        action: PendingAction::RemovePackages,
    },
    ActionItem {
        label_key: "action.rebuild_environment",
        action: PendingAction::RebuildEnvironment,
    },
    ActionItem {
        label_key: "action.install_plugin_dependencies",
        action: PendingAction::InstallPluginDependencies,
    },
];
const UPGRADE_ACTIONS: &[ActionItem] = &[
    ActionItem {
        label_key: "action.check_updates",
        action: PendingAction::CheckUpdates,
    },
    ActionItem {
        label_key: "action.upgrade_selected",
        action: PendingAction::Upgrade,
    },
];
const PLUGIN_ACTIONS: &[ActionItem] = &[
    ActionItem {
        label_key: "action.refresh_plugins",
        action: PendingAction::RefreshPlugins,
    },
    ActionItem {
        label_key: "action.check_plugin_updates",
        action: PendingAction::CheckPluginUpdates,
    },
    ActionItem {
        label_key: "action.install_plugin_dependencies",
        action: PendingAction::InstallPluginDependencies,
    },
];
const MISC_ACTIONS: &[ActionItem] = &[
    ActionItem {
        label_key: "action.create_shortcut",
        action: PendingAction::CreateShortcut,
    },
    ActionItem {
        label_key: "action.language",
        action: PendingAction::ChangeLanguage,
    },
];

pub struct Workspace {
    root: PathBuf,
    pub release_catalog: Option<ReleaseCatalog>,
    pub release_index: usize,
    pub action_index: usize,
    pub region: WorkspaceRegion,
    pub packages: Vec<PackageInfo>,
    pub package_index: usize,
    pub plugin_index: usize,
    pub selected_packages: BTreeSet<String>,
    pub plugins: PluginInventory,
    pub dependency_results: Vec<DependencyResult>,
    pending: Option<PendingAction>,
    language_requested: bool,
    status: String,
    operation: Option<RunningOperation>,
    operation_update: Option<OperationUpdate>,
    activity: Vec<String>,
}

impl Workspace {
    const ACTIVITY_LIMIT: usize = 200;

    pub fn new(root: &Path) -> Self {
        let plugins = PluginInventory::load(root).unwrap_or_default();
        Self {
            root: root.to_path_buf(),
            release_catalog: None,
            release_index: 0,
            action_index: 0,
            region: WorkspaceRegion::Actions,
            packages: Vec::new(),
            package_index: 0,
            plugin_index: 0,
            selected_packages: BTreeSet::new(),
            plugins,
            dependency_results: Vec::new(),
            pending: None,
            language_requested: false,
            status: "Ready".to_string(),
            operation: None,
            operation_update: None,
            activity: Vec::new(),
        }
    }

    pub fn start_operation(&mut self, request: OperationRequest) -> Result<(), Box<dyn Error>> {
        if self.is_running() {
            return Err("Another operation is still running".into());
        }
        self.pending = None;
        self.activity.clear();
        self.operation_update = None;
        self.status = format!("Running: {}", request.name());
        self.operation = Some(RunningOperation::start(request));
        Ok(())
    }

    pub fn is_running(&self) -> bool {
        self.operation.is_some()
    }

    pub fn poll_operation(&mut self) -> bool {
        let events = self.drain_operation_events();
        let finished = events
            .iter()
            .any(|event| matches!(event, OperationEvent::Finished(_)));
        for event in events {
            self.apply_operation_event(event);
        }
        finished
    }

    fn drain_operation_events(&mut self) -> Vec<OperationEvent> {
        let mut events = Vec::new();
        let Some(operation) = &self.operation else {
            return events;
        };
        loop {
            match operation.try_recv() {
                Ok(event) => {
                    let finished = matches!(event, OperationEvent::Finished(_));
                    events.push(event);
                    if finished {
                        break;
                    }
                }
                Err(std::sync::mpsc::TryRecvError::Empty) => break,
                Err(std::sync::mpsc::TryRecvError::Disconnected) => {
                    events.push(OperationEvent::Finished(Err(
                        "Operation worker stopped without a result".to_string(),
                    )));
                    break;
                }
            }
        }
        events
    }

    fn apply_operation_event(&mut self, event: OperationEvent) {
        match event {
            OperationEvent::Update(update) => {
                self.push_activity(update.message.clone());
                self.operation_update = Some(update);
            }
            OperationEvent::Finished(result) => {
                self.operation = None;
                match result {
                    Ok(success) => self.apply_success(success),
                    Err(error) => self.show_message(&format!("Operation failed: {error}")),
                }
            }
        }
    }

    fn apply_success(&mut self, success: OperationSuccess) {
        self.status = success.summary;
        self.push_activity(self.status.clone());
        for detail in success.details {
            self.push_activity(detail);
        }
        self.apply_operation_data(success.data);
    }

    fn apply_operation_data(&mut self, data: OperationData) {
        match data {
            OperationData::None => {}
            OperationData::Releases(catalog) => self.set_release_catalog(catalog),
            OperationData::Packages(packages) => {
                self.packages = packages;
                self.package_index = 0;
            }
            OperationData::Plugins(inventory) => {
                self.plugins = inventory;
                self.plugin_index = 0;
            }
            OperationData::PluginUpdates(results) => {
                apply_update_results(&mut self.plugins, results)
            }
            OperationData::Dependencies(results) => self.dependency_results = results,
        }
    }

    fn push_activity(&mut self, message: String) {
        self.activity.push(message);
        if self.activity.len() > Self::ACTIVITY_LIMIT {
            let excess = self.activity.len() - Self::ACTIVITY_LIMIT;
            self.activity.drain(0..excess);
        }
    }

    pub fn activity_text(&self) -> String {
        const VISIBLE_MESSAGES: usize = 4;
        let mut lines = vec![format!("Status: {}", self.status)];
        if self.is_running()
            && let Some(update) = &self.operation_update
        {
            lines.push(format!(
                "Progress: [{}/{}] {}",
                update.current, update.total, update.message
            ));
        }
        if let Some(name) = self.pending_action_name() {
            lines.push(format!("Confirm {name}: press Enter again; Esc cancels"));
        }
        let start = self.activity.len().saturating_sub(VISIBLE_MESSAGES);
        lines.extend(self.activity[start..].iter().cloned());
        lines.push("Log: logs/tui_setup.log".to_string());
        lines.join("\n")
    }

    pub fn show_message(&mut self, message: &str) {
        self.status = message.to_string();
        self.push_activity(message.to_string());
    }

    fn action_items(page: Page) -> &'static [ActionItem] {
        match page {
            Page::Install => INSTALL_ACTIONS,
            Page::Environment => ENVIRONMENT_ACTIONS,
            Page::Upgrade => UPGRADE_ACTIONS,
            Page::Plugins => PLUGIN_ACTIONS,
            Page::Misc => MISC_ACTIONS,
            Page::Overview => &[],
        }
    }

    fn selected_action(&self, page: Page) -> Option<PendingAction> {
        Self::action_items(page)
            .get(self.action_index)
            .map(|item| item.action)
    }

    pub fn has_pending_action(&self) -> bool {
        self.pending.is_some()
    }

    pub fn pending_action_name(&self) -> Option<&'static str> {
        self.pending.map(|action| match action {
            PendingAction::Install => "Install",
            PendingAction::Repair => "Repair",
            PendingAction::Upgrade => "Upgrade",
            PendingAction::CheckUpdates => "CheckUpdates",
            PendingAction::UpdatePackages => "UpdatePackages",
            PendingAction::RemovePackages => "RemovePackages",
            PendingAction::RebuildEnvironment => "RebuildEnvironment",
            PendingAction::QueryPackages => "QueryPackages",
            PendingAction::RefreshPlugins => "RefreshPlugins",
            PendingAction::CheckPluginUpdates => "CheckPluginUpdates",
            PendingAction::InstallPluginDependencies => "InstallPluginDependencies",
            PendingAction::CreateShortcut => "CreateShortcut",
            PendingAction::ChangeLanguage => "ChangeLanguage",
            PendingAction::InstallGit => "InstallGit",
            PendingAction::InstallUv => "InstallUv",
        })
    }

    pub fn toggle_region(&mut self) {
        self.region = match self.region {
            WorkspaceRegion::Actions => WorkspaceRegion::Data,
            WorkspaceRegion::Data => WorkspaceRegion::Actions,
        };
    }

    pub fn reset_region(&mut self) {
        self.region = WorkspaceRegion::Actions;
        self.action_index = 0;
        self.pending = None;
    }

    pub fn has_data(page: Page) -> bool {
        matches!(
            page,
            Page::Install | Page::Environment | Page::Upgrade | Page::Plugins
        )
    }

    pub fn take_language_request(&mut self) -> bool {
        std::mem::take(&mut self.language_requested)
    }

    pub fn set_release_catalog(&mut self, catalog: ReleaseCatalog) {
        self.release_catalog = Some(catalog);
        self.release_index = 0;
    }

    pub fn handle_key(&mut self, page: Page, key: KeyCode) -> Result<(), Box<dyn Error>> {
        self.handle_key_event(page, KeyEvent::from(key))
    }

    pub fn handle_key_event(&mut self, page: Page, key: KeyEvent) -> Result<(), Box<dyn Error>> {
        if self.is_running() {
            return Ok(());
        }
        match key.code {
            KeyCode::Esc => self.cancel_pending(),
            KeyCode::Up | KeyCode::Down => {
                self.move_selection(page, if key.code == KeyCode::Up { -1 } else { 1 })
            }
            KeyCode::Char(' ') => self.toggle_package(page),
            KeyCode::Enter => self.confirm(page)?,
            KeyCode::Char('c') => self.refresh(page)?,
            KeyCode::Char('u') => self.pending = Some(PendingAction::UpdatePackages),
            KeyCode::Char('d') => self.pending = Some(PendingAction::RemovePackages),
            KeyCode::Char('r') => self.pending = Some(PendingAction::RebuildEnvironment),
            KeyCode::Char('g') => self.pending = Some(PendingAction::InstallGit),
            KeyCode::Char('v') => self.pending = Some(PendingAction::InstallUv),
            _ => {}
        }
        Ok(())
    }

    fn cancel_pending(&mut self) {
        if self.pending.take().is_some() {
            self.show_message("Operation cancelled before execution");
        }
    }

    fn move_selection(&mut self, page: Page, delta: i32) {
        if self.region == WorkspaceRegion::Actions {
            let count = Self::action_items(page).len();
            Self::move_index(&mut self.action_index, count, delta);
            return;
        }
        match page {
            Page::Install | Page::Upgrade => {
                let count = self.release_count();
                Self::move_index(&mut self.release_index, count, delta);
            }
            Page::Environment => {
                Self::move_index(&mut self.package_index, self.packages.len(), delta)
            }
            Page::Plugins => {
                Self::move_index(&mut self.plugin_index, self.plugins.plugins.len(), delta)
            }
            _ => {}
        }
    }

    fn move_index(index: &mut usize, count: usize, delta: i32) {
        if count > 0 {
            *index = (*index as i32 + delta).rem_euclid(count as i32) as usize;
        }
    }

    fn toggle_package(&mut self, page: Page) {
        if page != Page::Environment {
            return;
        }
        if let Some(package) = self.packages.get(self.package_index) {
            let name = package.name.clone();
            if !self.selected_packages.remove(&name) {
                self.selected_packages.insert(name);
            }
        }
    }

    fn confirm(&mut self, page: Page) -> Result<(), Box<dyn Error>> {
        if let Some(action) = self.pending.take() {
            return self.start_pending(action);
        }
        if self.region == WorkspaceRegion::Data {
            return Ok(());
        }
        if let Some(action) = self.selected_action(page) {
            self.pending = Some(action);
            self.show_message(&format!(
                "Confirm {} with Enter; Esc cancels",
                action_name(action)
            ));
        }
        Ok(())
    }

    fn refresh(&mut self, page: Page) -> Result<(), Box<dyn Error>> {
        let request = match page {
            Page::Install | Page::Upgrade => OperationRequest::LoadReleases {
                root: self.root.clone(),
            },
            Page::Environment => OperationRequest::LoadPackages {
                root: self.root.clone(),
            },
            Page::Plugins => OperationRequest::CheckPluginUpdates {
                root: self.root.clone(),
            },
            Page::Misc => {
                self.pending = Some(PendingAction::CreateShortcut);
                return Ok(());
            }
            Page::Overview => return Ok(()),
        };
        self.start_operation(request)
    }

    fn start_pending(&mut self, action: PendingAction) -> Result<(), Box<dyn Error>> {
        if action == PendingAction::ChangeLanguage {
            self.language_requested = true;
            self.show_message("Select the interface language");
            return Ok(());
        }
        let request = self.operation_request(action);
        self.start_operation(request)
    }

    fn operation_request(&self, action: PendingAction) -> OperationRequest {
        let root = self.root.clone();
        match action {
            PendingAction::Install | PendingAction::Repair | PendingAction::Upgrade => {
                OperationRequest::Archive {
                    root,
                    action: archive_action(action),
                    selected_release: if action == PendingAction::Repair {
                        None
                    } else {
                        self.selected_release().cloned()
                    },
                    archive: None,
                    release_tag: None,
                    auto_install: true,
                }
            }
            PendingAction::CheckUpdates => OperationRequest::LoadReleases { root },
            PendingAction::UpdatePackages => OperationRequest::UpdatePackages {
                root,
                packages: self.selected_packages.iter().cloned().collect(),
            },
            PendingAction::RemovePackages => OperationRequest::RemovePackages {
                root,
                packages: self.removable_packages(),
            },
            PendingAction::RebuildEnvironment => OperationRequest::RebuildEnvironment { root },
            PendingAction::QueryPackages => OperationRequest::LoadPackages { root },
            PendingAction::RefreshPlugins => OperationRequest::RefreshPlugins { root },
            PendingAction::CheckPluginUpdates => OperationRequest::CheckPluginUpdates { root },
            PendingAction::InstallPluginDependencies => {
                OperationRequest::InstallPluginDependencies { root }
            }
            PendingAction::CreateShortcut => OperationRequest::CreateShortcut { root },
            PendingAction::InstallGit => OperationRequest::InstallGit { root },
            PendingAction::InstallUv => OperationRequest::InstallUv { root },
            PendingAction::ChangeLanguage => unreachable!("语言切换不启动后台操作"),
        }
    }

    fn selected_release(&self) -> Option<&Release> {
        self.release_catalog
            .as_ref()?
            .releases
            .get(self.release_index)
    }

    fn release_count(&self) -> usize {
        self.release_catalog
            .as_ref()
            .map_or(0, |catalog| catalog.releases.len())
    }

    fn removable_packages(&self) -> Vec<String> {
        let protected = self.protected_packages();
        self.selected_packages
            .iter()
            .filter(|name| !protected.contains(*name))
            .cloned()
            .collect()
    }

    fn protected_packages(&self) -> BTreeSet<String> {
        fs::read_to_string(self.root.join("requirements.txt"))
            .unwrap_or_default()
            .lines()
            .filter_map(|line| {
                let name = line
                    .split(['>', '<', '=', '[', ';', ' '])
                    .next()?
                    .trim()
                    .to_string();
                if name.is_empty() { None } else { Some(name) }
            })
            .collect()
    }

    pub fn render(&self, page: Page) -> String {
        self.render_with_i18n(
            page,
            &crate::i18n::I18n::new(crate::i18n::Language::English),
        )
    }

    pub fn render_with_i18n(&self, page: Page, i18n: &crate::i18n::I18n) -> String {
        let mut text = match page {
            Page::Install => self.render_install(i18n),
            Page::Environment => self.render_environment(i18n),
            Page::Upgrade => self.render_releases(),
            Page::Plugins => self.render_plugins(i18n),
            Page::Misc => self.render_action_menu(Page::Misc, i18n),
            Page::Overview => String::new(),
        };
        let _ = writeln!(text, "\nStatus: {}", self.status);
        text
    }

    fn render_action_menu(&self, page: Page, i18n: &crate::i18n::I18n) -> String {
        let items = Self::action_items(page);
        let mut text = String::new();
        for (index, item) in items.iter().enumerate() {
            let marker = if self.region == WorkspaceRegion::Actions && index == self.action_index {
                "▸"
            } else {
                " "
            };
            let _ = writeln!(text, "{marker} {}", i18n.t(item.label_key));
        }
        if !items.is_empty() {
            text.push('\n');
        }
        text
    }

    fn render_install(&self, i18n: &crate::i18n::I18n) -> String {
        let preflight = ToolPreflight::detect_for_root(&self.root);
        let mut text = format!(
            "Tools: git={} uv={} (g install Git, v install uv)\n\n",
            preflight.git_present, preflight.uv_present
        );
        text.push_str(&self.render_action_menu(Page::Install, i18n));
        text.push_str(&self.render_releases());
        text
    }

    fn render_releases(&self) -> String {
        let Some(catalog) = &self.release_catalog else {
            return "No Releases loaded. Install loads the latest automatically; Check loads the timeline.\n".to_string();
        };
        let mut text = String::new();
        for (index, release) in catalog.releases.iter().enumerate() {
            let selected = if self.region == WorkspaceRegion::Data && index == self.release_index {
                "▸"
            } else {
                " "
            };
            let latest = if index == 0 { "latest" } else { "" };
            let current = if Some(release.id) == catalog.current_release_id {
                "current"
            } else {
                ""
            };
            let pre = if release.prerelease {
                "Pre-release"
            } else {
                ""
            };
            let invalid = if release.version.is_none() {
                "unrecognized"
            } else {
                ""
            };
            let _ = writeln!(
                text,
                "{selected} {} | {} | {} | {latest} {current} {pre} {invalid}",
                release.name,
                release.tag_name,
                release.published_at.format("%Y-%m-%d")
            );
        }
        text
    }

    fn render_environment(&self, i18n: &crate::i18n::I18n) -> String {
        let mut text = self.render_action_menu(Page::Environment, i18n);
        if self.packages.is_empty() {
            text.push_str("No package information. Select Query package list to load it.\n");
            return text;
        }
        let protected = self.protected_packages();
        text.push_str("Space: select package\n");
        for (index, package) in self.packages.iter().enumerate() {
            let selected = if self.selected_packages.contains(&package.name) {
                "[x]"
            } else {
                "[ ]"
            };
            let current = if self.region == WorkspaceRegion::Data && index == self.package_index {
                "▸"
            } else {
                " "
            };
            let latest = package.latest_version.as_deref().unwrap_or("unknown");
            let protected = if protected.contains(&package.name) {
                "protected"
            } else {
                ""
            };
            let _ = writeln!(
                text,
                "{current} {selected} {} {} -> {} {protected}",
                package.name, package.version, latest
            );
        }
        text
    }

    fn render_plugins(&self, i18n: &crate::i18n::I18n) -> String {
        let mut text = self.render_action_menu(Page::Plugins, i18n);
        if self.plugins.plugins.is_empty() {
            text.push_str("No plugins found. Select Refresh plugin list to reload.\n");
            return text;
        }
        for (index, plugin) in self.plugins.plugins.iter().enumerate() {
            let selected = if self.region == WorkspaceRegion::Data && index == self.plugin_index {
                "▸"
            } else {
                " "
            };
            let scope = match plugin.scope {
                crate::plugins::PluginScope::Official => "official",
                crate::plugins::PluginScope::ThirdParty => "thirdparty",
            };
            let update = match &plugin.update {
                PluginUpdateStatus::Unchecked => "unchecked".to_string(),
                PluginUpdateStatus::Checking => "checking".to_string(),
                PluginUpdateStatus::UpToDate => "latest".to_string(),
                PluginUpdateStatus::UpdateAvailable(version) => format!("update: {version}"),
                PluginUpdateStatus::Failed(error) => format!("error: {error}"),
            };
            let _ = writeln!(
                text,
                "{selected} [{scope}] {} | {} | {update}\n  {}\n  {}",
                plugin.name, plugin.version, plugin.description, plugin.developer_url
            );
        }
        for result in &self.dependency_results {
            let _ = writeln!(
                text,
                "Dependency {}: {} {}",
                result.plugin_name,
                if result.success { "OK" } else { "FAILED" },
                result.detail
            );
        }
        text
    }
}

fn archive_action(action: PendingAction) -> ArchiveAction {
    match action {
        PendingAction::Install => ArchiveAction::Install,
        PendingAction::Repair => ArchiveAction::Repair,
        PendingAction::Upgrade => ArchiveAction::Upgrade,
        _ => unreachable!("仅归档操作需要 ArchiveAction"),
    }
}

fn action_name(action: PendingAction) -> &'static str {
    match action {
        PendingAction::Install => "Install",
        PendingAction::Repair => "Repair",
        PendingAction::Upgrade => "Upgrade",
        PendingAction::CheckUpdates => "Check updates",
        PendingAction::UpdatePackages => "Update packages",
        PendingAction::RemovePackages => "Remove packages",
        PendingAction::RebuildEnvironment => "Rebuild environment",
        PendingAction::QueryPackages => "Query packages",
        PendingAction::RefreshPlugins => "Refresh plugins",
        PendingAction::CheckPluginUpdates => "Check plugin updates",
        PendingAction::InstallPluginDependencies => "Install plugin dependencies",
        PendingAction::CreateShortcut => "Create shortcut",
        PendingAction::ChangeLanguage => "Change language",
        PendingAction::InstallGit => "Install Git",
        PendingAction::InstallUv => "Install uv",
    }
}

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use super::*;

    #[test]
    fn background_operation_reports_activity_and_writes_persistent_log() {
        let temporary = tempfile::tempdir().expect("创建临时目录");
        let work = temporary.path().join(".tui/work");
        fs::create_dir_all(&work).expect("创建待清理目录");
        fs::write(work.join("temporary.txt"), b"temporary").expect("写入临时文件");
        let mut workspace = Workspace::new(temporary.path());

        workspace
            .start_operation(OperationRequest::CleanTemp {
                root: temporary.path().to_path_buf(),
            })
            .expect("启动后台操作");
        assert!(workspace.is_running());
        wait_until_finished(&mut workspace);

        assert!(!work.exists());
        assert!(workspace.status.contains("Temporary files cleaned"));
        assert!(workspace.activity_text().contains("Clean temporary files"));
        let log =
            fs::read_to_string(temporary.path().join("logs/tui_setup.log")).expect("读取操作日志");
        assert!(log.contains("Operation started: Clean temporary files"));
        assert!(log.contains("Operation completed: Temporary files cleaned"));
    }

    #[test]
    fn selected_action_requires_explicit_second_enter() {
        let temporary = tempfile::tempdir().expect("创建临时目录");
        let mut workspace = Workspace::new(temporary.path());

        workspace
            .handle_key(Page::Misc, KeyCode::Enter)
            .expect("选择操作");

        assert!(workspace.has_pending_action());
        assert!(!workspace.is_running());
        assert!(workspace.activity_text().contains("press Enter again"));
    }

    #[test]
    fn repair_resolves_matching_version_instead_of_selected_latest_release() {
        let temporary = tempfile::tempdir().expect("创建临时目录");
        let mut workspace = Workspace::new(temporary.path());
        let latest = Release {
            id: 1,
            name: "Latest".to_string(),
            tag_name: "alpha-v9.9.9".to_string(),
            version: crate::github::FrameworkVersion::parse("alpha-v9.9.9").ok(),
            prerelease: false,
            published_at: chrono::Utc::now(),
            body: String::new(),
            html_url: String::new(),
        };
        workspace.release_catalog = Some(ReleaseCatalog {
            releases: vec![latest],
            current_release_id: None,
            current_version: crate::github::FrameworkVersion::parse("alpha-v1.0.0")
                .expect("当前版本"),
        });

        let request = workspace.operation_request(PendingAction::Repair);

        match request {
            OperationRequest::Archive {
                selected_release, ..
            } => {
                assert!(selected_release.is_none());
            }
            _ => panic!("修复应生成归档操作"),
        }
    }

    fn wait_until_finished(workspace: &mut Workspace) {
        for _ in 0..100 {
            workspace.poll_operation();
            if !workspace.is_running() {
                return;
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        panic!("后台操作未及时完成");
    }
}
