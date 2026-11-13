use std::collections::BTreeSet;
use std::error::Error;
use std::fmt::Write as _;
use std::fs;
use std::path::{Path, PathBuf};

use crossterm::event::{KeyCode, KeyEvent};

use crate::actions::{ArchiveAction, ToolPreflight, current_framework_version, install_archive};
use crate::app::Page;
use crate::github::{FrameworkVersion, Release, ReleaseCatalog, ReleaseClient};
use crate::plugins::{
    DependencyResult, PluginInventory, PluginUpdateStatus, apply_update_results,
    check_plugin_updates, install_plugin_dependencies,
};
use crate::shortcuts::ShortcutManager;
use crate::uv::{PackageInfo, UvClient, uv_program};

const GITHUB_API_URL: &str = "https://api.github.com";

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
}

impl Workspace {
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
        }
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
        match key.code {
            KeyCode::Up | KeyCode::Down => {
                self.move_selection(page, if key.code == KeyCode::Up { -1 } else { 1 })
            }
            KeyCode::Char(' ') => self.toggle_package(page),
            KeyCode::Enter => self.confirm(page)?,
            KeyCode::Char('c') => self.refresh(page)?,
            KeyCode::Char('u') => self.pending = Some(PendingAction::UpdatePackages),
            KeyCode::Char('d') => self.pending = Some(PendingAction::RemovePackages),
            KeyCode::Char('r') => self.pending = Some(PendingAction::RebuildEnvironment),
            KeyCode::Char('g') => self.install_git(),
            KeyCode::Char('v') => self.install_uv(),
            _ => {}
        }
        Ok(())
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
                Self::move_index(&mut self.release_index, count, delta)
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
        if count == 0 {
            return;
        }
        *index = (*index as i32 + delta).rem_euclid(count as i32) as usize;
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
            return self.execute(action);
        }
        if self.region == WorkspaceRegion::Data {
            return Ok(());
        }
        if let Some(action) = self.selected_action(page) {
            self.pending = Some(action);
        }
        Ok(())
    }

    fn refresh(&mut self, page: Page) -> Result<(), Box<dyn Error>> {
        match page {
            Page::Install | Page::Upgrade => self.load_releases()?,
            Page::Environment => self.load_packages()?,
            Page::Plugins => self.check_plugin_updates()?,
            Page::Misc => self.pending = Some(PendingAction::CreateShortcut),
            Page::Overview => {}
        }
        Ok(())
    }

    fn load_releases(&mut self) -> Result<(), Box<dyn Error>> {
        self.status = "Checking GitHub Releases...".to_string();
        let current = current_framework_version(&self.root)
            .unwrap_or(FrameworkVersion::parse("alpha-v0.0.0")?);
        let client = ReleaseClient::new(GITHUB_API_URL)?;
        match client.list_all_releases(current) {
            Ok(catalog) => {
                self.set_release_catalog(catalog);
                self.status = "Releases updated".to_string();
            }
            Err(error) => self.status = format!("Release check failed: {error}"),
        }
        Ok(())
    }

    fn load_packages(&mut self) -> Result<(), Box<dyn Error>> {
        self.status = "Reading package versions...".to_string();
        let client = UvClient::new(&self.root);
        match client.list_packages() {
            Ok(packages) => {
                self.packages = packages;
                self.package_index = 0;
                self.status = "Package list updated".to_string();
            }
            Err(error) => self.status = format!("Package query failed: {error}"),
        }
        Ok(())
    }

    fn check_plugin_updates(&mut self) -> Result<(), Box<dyn Error>> {
        self.status = "Checking plugin updates...".to_string();
        match check_plugin_updates(&self.root) {
            Ok(results) => {
                apply_update_results(&mut self.plugins, results);
                self.status = "Plugin updates checked".to_string();
            }
            Err(error) => self.status = format!("Plugin update check failed: {error}"),
        }
        Ok(())
    }

    fn refresh_plugins(&mut self) -> Result<(), Box<dyn Error>> {
        self.plugins = PluginInventory::load(&self.root)?;
        self.plugin_index = 0;
        self.status = "Plugin list refreshed".to_string();
        Ok(())
    }

    fn install_dependencies(&mut self) -> Result<(), Box<dyn Error>> {
        self.dependency_results = install_plugin_dependencies(&self.root)?;
        let failed = self
            .dependency_results
            .iter()
            .filter(|result| !result.success)
            .count();
        self.status = format!("Plugin dependency installation finished; {failed} failed");
        Ok(())
    }

    fn execute(&mut self, action: PendingAction) -> Result<(), Box<dyn Error>> {
        let result = match action {
            PendingAction::Install => self.execute_archive(ArchiveAction::Install),
            PendingAction::Repair => self.execute_archive(ArchiveAction::Repair),
            PendingAction::Upgrade => self.execute_archive(ArchiveAction::Upgrade),
            PendingAction::CheckUpdates => self.load_releases(),
            PendingAction::UpdatePackages => self.update_packages(),
            PendingAction::RemovePackages => self.remove_packages(),
            PendingAction::RebuildEnvironment => self.rebuild_environment(),
            PendingAction::QueryPackages => self.load_packages(),
            PendingAction::RefreshPlugins => self.refresh_plugins(),
            PendingAction::CheckPluginUpdates => self.check_plugin_updates(),
            PendingAction::InstallPluginDependencies => self.install_dependencies(),
            PendingAction::CreateShortcut => self.create_shortcut(),
            PendingAction::ChangeLanguage => {
                self.language_requested = true;
                Ok(())
            }
        };
        if let Err(error) = result {
            self.status = format!("Operation failed: {error}");
        }
        Ok(())
    }

    fn execute_archive(&mut self, action: ArchiveAction) -> Result<(), Box<dyn Error>> {
        let preflight = ToolPreflight::detect();
        if !preflight.uv_present {
            self.status = "uv is required. Press v to install it, then retry.".to_string();
            return Ok(());
        }
        let Some(release) = self.selected_release().cloned() else {
            self.status = "Press c to check Releases before continuing".to_string();
            return Ok(());
        };
        if !preflight.git_present {
            self.status =
                "Git is missing; archive installation will be used. Press g to install it."
                    .to_string();
        }
        let client = ReleaseClient::new(GITHUB_API_URL)?;
        let archive = self
            .root
            .join(".tui/work")
            .join(format!("{}.zip", release.tag_name));
        client.download_archive(&release.tag_name, &archive)?;
        let mut uv = UvClient::new(&self.root);
        let report = install_archive(&archive, &self.root, action, || uv.sync_environment())?;
        self.status = format!(
            "Completed {}: {} files copied",
            release.tag_name, report.copied_files
        );
        Ok(())
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

    fn update_packages(&mut self) -> Result<(), Box<dyn Error>> {
        let packages: Vec<_> = self.selected_packages.iter().cloned().collect();
        UvClient::new(&self.root).update_packages(&packages)?;
        self.status = format!("Updated {} packages", packages.len());
        self.load_packages()
    }

    fn remove_packages(&mut self) -> Result<(), Box<dyn Error>> {
        let protected = self.protected_packages();
        let packages: Vec<_> = self
            .selected_packages
            .iter()
            .filter(|name| !protected.contains(*name))
            .cloned()
            .collect();
        UvClient::new(&self.root).remove_packages(&packages)?;
        self.status = format!(
            "Removed {} packages; protected dependencies were kept",
            packages.len()
        );
        self.load_packages()
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

    fn rebuild_environment(&mut self) -> Result<(), Box<dyn Error>> {
        UvClient::new(&self.root).rebuild_environment()?;
        self.dependency_results = install_plugin_dependencies(&self.root)?;
        let failed = self
            .dependency_results
            .iter()
            .filter(|result| !result.success)
            .count();
        self.status = format!("Environment rebuilt; {failed} plugin dependency tasks failed");
        Ok(())
    }

    fn create_shortcut(&mut self) -> Result<(), Box<dyn Error>> {
        let manager = ShortcutManager::new(self.root.clone(), uv_program(&self.root));
        let path = manager.create(false)?;
        self.status = format!("Shortcut created: {}", path.display());
        Ok(())
    }

    fn install_git(&mut self) {
        self.status = match crate::uv::install_git() {
            Ok(()) => "Git installed successfully".to_string(),
            Err(error) => format!("Git installation failed: {error}"),
        };
    }

    fn install_uv(&mut self) {
        self.status = match crate::uv::install_uv(&self.root) {
            Ok(path) => format!("uv installed: {}", path.display()),
            Err(error) => format!("uv installation failed: {error}"),
        };
    }

    pub fn run_action(
        &mut self,
        action: &str,
        archive: Option<&Path>,
        release_tag: Option<&str>,
        dry_run: bool,
        auto_install: bool,
    ) -> Result<String, Box<dyn Error>> {
        if dry_run {
            return Ok(format!(
                "Dry run: action={action}, archive={archive:?}, release_tag={release_tag:?}"
            ));
        }
        match action {
            "install" => {
                self.run_archive_action(ArchiveAction::Install, archive, release_tag, auto_install)
            }
            "repair" => {
                self.run_archive_action(ArchiveAction::Repair, archive, release_tag, auto_install)
            }
            "upgrade" => {
                self.run_archive_action(ArchiveAction::Upgrade, archive, release_tag, auto_install)
            }
            _ => self.run_simple_action(action, auto_install),
        }
    }

    fn run_simple_action(
        &mut self,
        action: &str,
        auto_install: bool,
    ) -> Result<String, Box<dyn Error>> {
        match action {
            "environment-repair" => {
                self.rebuild_environment()?;
                Ok(self.status.clone())
            }
            "check-updates" => {
                self.load_releases()?;
                Ok(self.render_releases())
            }
            "create-shortcut" => {
                self.create_shortcut()?;
                Ok(self.status.clone())
            }
            "doctor" => {
                let overview = crate::system::SystemOverview::collect(&self.root);
                Ok(format!(
                    "Framework installed: {}",
                    overview.framework.installed
                ))
            }
            "clean-temp" => {
                let work = self.root.join(".tui/work");
                if work.exists() {
                    fs::remove_dir_all(work)?;
                }
                Ok("Temporary files cleaned".to_string())
            }
            "uninstall" => self.uninstall(auto_install),
            _ => Err(format!("Unknown action: {action}").into()),
        }
    }

    fn run_archive_action(
        &mut self,
        action: ArchiveAction,
        archive: Option<&Path>,
        release_tag: Option<&str>,
        auto_install: bool,
    ) -> Result<String, Box<dyn Error>> {
        self.ensure_uv(auto_install)?;
        let archive = self.resolve_archive(action, archive, release_tag)?;
        let mut uv = UvClient::new(&self.root);
        let report = install_archive(&archive, &self.root, action, || uv.sync_environment())?;
        Ok(format!(
            "{} files copied; backup: {}",
            report.copied_files,
            report.backup_dir.display()
        ))
    }

    fn ensure_uv(&mut self, auto_install: bool) -> Result<(), Box<dyn Error>> {
        if ToolPreflight::detect().uv_present {
            return Ok(());
        }
        if !auto_install {
            return Err("uv is missing; use --yes to allow automatic installation".into());
        }
        crate::uv::install_uv(&self.root)?;
        Ok(())
    }

    fn resolve_archive(
        &mut self,
        action: ArchiveAction,
        archive: Option<&Path>,
        release_tag: Option<&str>,
    ) -> Result<PathBuf, Box<dyn Error>> {
        if let Some(path) = archive {
            return Ok(path.to_path_buf());
        }
        if let Some(tag) = release_tag {
            let client = ReleaseClient::new(GITHUB_API_URL)?;
            let destination = self.root.join(".tui/work").join(format!("{tag}.zip"));
            client.download_archive(tag, &destination)?;
            return Ok(destination);
        }
        self.load_releases()?;
        let current = current_framework_version(&self.root).ok();
        let release = match action {
            ArchiveAction::Repair => self.release_catalog.as_ref().and_then(|catalog| {
                catalog
                    .releases
                    .iter()
                    .find(|release| release.version == current)
            }),
            _ => self
                .release_catalog
                .as_ref()
                .and_then(|catalog| catalog.releases.first()),
        }
        .cloned()
        .ok_or("No matching Release was found")?;
        let client = ReleaseClient::new(GITHUB_API_URL)?;
        let destination = self
            .root
            .join(".tui/work")
            .join(format!("{}.zip", release.tag_name));
        client.download_archive(&release.tag_name, &destination)?;
        Ok(destination)
    }

    fn uninstall(&self, confirmed: bool) -> Result<String, Box<dyn Error>> {
        if !confirmed {
            return Err("Uninstall requires --yes".into());
        }
        for name in [".venv", "config", "data", "logs", ".tui"] {
            let path = self.root.join(name);
            if path.exists() {
                fs::remove_dir_all(path)?;
            }
        }
        let shortcut = ShortcutManager::new(self.root.clone(), PathBuf::from("uv")).shortcut_path();
        if shortcut.is_dir() {
            fs::remove_dir_all(shortcut)?;
        } else if shortcut.is_file() {
            fs::remove_file(shortcut)?;
        }
        Ok("Environment and shortcuts removed; program files and plugins were kept".to_string())
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
        let preflight = ToolPreflight::detect();
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
            return "No Releases loaded. Select Check for updates to load them.\n".to_string();
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
