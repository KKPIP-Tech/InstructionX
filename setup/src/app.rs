use std::cell::Cell;
use std::error::Error;
use std::fmt::Write as _;
use std::io;
use std::path::PathBuf;

use crossterm::event::{self, Event, KeyCode, KeyEvent, KeyEventKind, MouseEventKind};
use crossterm::event::{DisableMouseCapture, EnableMouseCapture};
use crossterm::execute;
use crossterm::terminal::{
    EnterAlternateScreen, LeaveAlternateScreen, disable_raw_mode, enable_raw_mode,
};
use ratatui::backend::{CrosstermBackend, TestBackend};
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::widgets::{Block, Borders, List, ListItem, Paragraph, Wrap};
use ratatui::{Frame, Terminal};
use unicode_width::UnicodeWidthStr;

use crate::i18n::{I18n, Language, Preferences};
use crate::system::{SystemOverview, fetch_public_ip_with_url};
use crate::version::setup_build_version;
use crate::workspace::Workspace;

const NAVIGATION_WIDTH: u16 = 30;
const HEADER_HEIGHT: u16 = 3;
const FOOTER_HEIGHT: u16 = 3;
const ACTIVITY_HEIGHT: u16 = 9;
const MINIMUM_WIDTH: u16 = 60;
const MINIMUM_HEIGHT: u16 = 20;
const EVENT_POLL_INTERVAL: std::time::Duration = std::time::Duration::from_millis(80);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Page {
    Overview,
    Install,
    Environment,
    Upgrade,
    Plugins,
    Misc,
}

impl Page {
    pub const ALL: [Page; 6] = [
        Page::Overview,
        Page::Install,
        Page::Environment,
        Page::Upgrade,
        Page::Plugins,
        Page::Misc,
    ];

    pub const fn index(self) -> usize {
        match self {
            Self::Overview => 0,
            Self::Install => 1,
            Self::Environment => 2,
            Self::Upgrade => 3,
            Self::Plugins => 4,
            Self::Misc => 5,
        }
    }

    pub const fn title_key(self) -> &'static str {
        match self {
            Self::Overview => "menu.overview",
            Self::Install => "menu.install",
            Self::Environment => "menu.environment",
            Self::Upgrade => "menu.upgrade",
            Self::Plugins => "menu.plugins",
            Self::Misc => "menu.misc",
        }
    }

    pub const fn has_selection(self) -> bool {
        matches!(
            self,
            Self::Install | Self::Environment | Self::Upgrade | Self::Plugins | Self::Misc
        )
    }

    pub fn from_index(index: usize) -> Self {
        Self::ALL[index % Self::ALL.len()]
    }

    pub fn from_name(name: &str) -> Option<Self> {
        match name {
            "menu" | "status" | "doctor" => Some(Self::Overview),
            "manage" => Some(Self::Environment),
            "cleanup" | "launch" | "help" => Some(Self::Misc),
            _ => Self::ALL
                .into_iter()
                .find(|page| page.title_key().strip_prefix("menu.") == Some(name)),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Focus {
    Navigation,
    Content,
}

pub struct App {
    pub preferences: Preferences,
    pub page: Page,
    pub focus: Focus,
    pub should_quit: bool,
    preferences_path: PathBuf,
    project_root: PathBuf,
    overview: Option<SystemOverview>,
    public_ip: Option<String>,
    public_ip_error: Option<String>,
    pub workspace: Workspace,
    pub content_scroll: u16,
    content_height: Cell<u16>,
    content_viewport: Cell<u16>,
    i18n: I18n,
    language_index: usize,
    show_language_selection: bool,
}

impl App {
    pub fn new(preferences: Preferences, preferences_path: PathBuf) -> Self {
        let language_index = Language::ALL
            .iter()
            .position(|language| *language == preferences.language)
            .unwrap_or_default();
        let project_root = preferences_path
            .parent()
            .and_then(|path| path.parent())
            .unwrap_or_else(|| std::path::Path::new("."))
            .to_path_buf();
        let overview = if preferences.needs_language_selection {
            None
        } else {
            Some(SystemOverview::collect(&project_root))
        };
        Self {
            preferences,
            page: Page::Overview,
            focus: Focus::Navigation,
            should_quit: false,
            preferences_path,
            project_root: project_root.clone(),
            overview,
            public_ip: None,
            public_ip_error: None,
            workspace: Workspace::new(&project_root),
            content_scroll: 0,
            content_height: Cell::new(0),
            content_viewport: Cell::new(0),
            i18n: I18n::new(preferences.language),
            language_index,
            show_language_selection: preferences.needs_language_selection,
        }
    }

    pub fn handle_key(&mut self, key: KeyCode) -> Result<(), Box<dyn Error>> {
        self.handle_key_event(KeyEvent::from(key))
    }

    pub fn handle_key_event(&mut self, key: KeyEvent) -> Result<(), Box<dyn Error>> {
        if key.kind == KeyEventKind::Release {
            return Ok(());
        }
        if key.code == KeyCode::Char('q') {
            if self.workspace.is_running() {
                self.workspace.show_localized_message(
                    "activity.quit_blocked",
                    &[],
                    "An operation is still running; wait for its result before quitting",
                );
            } else {
                self.should_quit = true;
            }
            return Ok(());
        }
        if self.show_language_selection {
            return self.handle_language_key(key.code);
        }
        self.handle_navigation_event(key)
    }

    pub fn handle_mouse(&mut self, kind: MouseEventKind) {
        match kind {
            MouseEventKind::ScrollUp => {
                self.focus = Focus::Content;
                self.scroll_by(-1);
            }
            MouseEventKind::ScrollDown => {
                self.focus = Focus::Content;
                self.scroll_by(1);
            }
            _ => {}
        }
    }

    fn handle_language_key(&mut self, key: KeyCode) -> Result<(), Box<dyn Error>> {
        match key {
            KeyCode::Up => self.move_language_selection(-1),
            KeyCode::Down | KeyCode::Tab => self.move_language_selection(1),
            KeyCode::Enter => self.confirm_language()?,
            _ => {}
        }
        Ok(())
    }

    fn handle_navigation_event(&mut self, key: KeyEvent) -> Result<(), Box<dyn Error>> {
        match key.code {
            KeyCode::Left => self.focus = Focus::Navigation,
            KeyCode::Right => {
                self.focus = Focus::Content;
                self.workspace.reset_region();
            }
            KeyCode::Tab => self.toggle_focus(),
            KeyCode::Up | KeyCode::Down
                if self.focus == Focus::Content && self.page.has_selection() =>
            {
                self.workspace.handle_key_event(self.page, key)?;
                self.reveal_selection();
            }
            KeyCode::Up | KeyCode::Down if self.focus == Focus::Navigation => {
                let delta = if key.code == KeyCode::Up {
                    Page::ALL.len() - 1
                } else {
                    1
                };
                self.set_page(Page::from_index(self.page.index() + delta));
            }
            KeyCode::Up => self.scroll_by(-1),
            KeyCode::Down => self.scroll_by(1),
            KeyCode::PageUp => self.scroll_page(-1),
            KeyCode::PageDown => self.scroll_page(1),
            KeyCode::Home => self.content_scroll = 0,
            KeyCode::End => self.content_scroll = self.max_scroll(),
            KeyCode::Enter if self.focus == Focus::Navigation => {
                self.focus = Focus::Content;
                self.workspace.reset_region();
            }
            KeyCode::Char('l') => self.show_language_selection = true,
            KeyCode::Char('r') if self.page == Page::Overview => self.refresh_overview(),
            KeyCode::Char('p') if self.page == Page::Overview => self.refresh_public_ip(),
            KeyCode::Char(value) if ('0'..='5').contains(&value) => {
                let index = value.to_digit(10).unwrap_or_default() as usize;
                self.set_page(Page::from_index(index));
            }
            _ => self.workspace.handle_key_event(self.page, key)?,
        }
        self.apply_workspace_requests();
        Ok(())
    }

    fn apply_workspace_requests(&mut self) {
        if self.workspace.take_language_request() {
            self.show_language_selection = true;
        }
    }

    fn toggle_focus(&mut self) {
        if self.focus == Focus::Navigation {
            self.focus = Focus::Content;
            self.workspace.reset_region();
            return;
        }
        if self.workspace.region == crate::workspace::WorkspaceRegion::Actions
            && Workspace::has_data(self.page)
        {
            self.workspace.toggle_region();
            return;
        }
        self.focus = Focus::Navigation;
    }

    fn set_page(&mut self, page: Page) {
        self.page = page;
        self.content_scroll = 0;
        self.workspace.reset_region();
    }

    fn scroll_by(&mut self, delta: i32) {
        let next = self.content_scroll as i32 + delta;
        self.content_scroll = next.clamp(0, self.max_scroll() as i32) as u16;
    }

    fn scroll_page(&mut self, direction: i32) {
        let step = self.content_viewport.get().max(1) as i32 * direction;
        self.scroll_by(step);
    }

    fn max_scroll(&self) -> u16 {
        self.content_height
            .get()
            .saturating_sub(self.content_viewport.get())
    }

    fn reveal_selection(&mut self) {
        let index = if self.workspace.region == crate::workspace::WorkspaceRegion::Actions {
            self.workspace.action_index
        } else {
            match self.page {
                Page::Upgrade | Page::Install => self.workspace.release_index,
                Page::Environment => self.workspace.package_index,
                Page::Plugins => self.workspace.plugin_index,
                _ => return,
            }
        };
        self.content_scroll = (index as u16).min(self.max_scroll());
    }

    fn move_language_selection(&mut self, delta: i32) {
        let count = Language::ALL.len() as i32;
        self.language_index = (self.language_index as i32 + delta).rem_euclid(count) as usize;
    }

    fn confirm_language(&mut self) -> Result<(), Box<dyn Error>> {
        self.preferences.language = Language::ALL[self.language_index];
        self.preferences.needs_language_selection = false;
        self.i18n = I18n::new(self.preferences.language);
        self.preferences.save(&self.preferences_path)?;
        self.show_language_selection = false;
        self.refresh_overview();
        Ok(())
    }

    fn refresh_overview(&mut self) {
        self.overview = Some(SystemOverview::collect(&self.project_root));
    }

    fn refresh_public_ip(&mut self) {
        const PUBLIC_IP_URL: &str = "https://api.ipify.org";
        match fetch_public_ip_with_url(PUBLIC_IP_URL) {
            Ok(address) => {
                self.public_ip = Some(address);
                self.public_ip_error = None;
            }
            Err(error) => {
                self.public_ip = None;
                self.public_ip_error = Some(error.to_string());
            }
        }
    }

    pub fn render(&self, frame: &mut Frame) {
        let area = frame.area();
        if area.width < MINIMUM_WIDTH || area.height < MINIMUM_HEIGHT {
            self.render_small_terminal(frame, area);
            return;
        }
        let rows = Layout::vertical([
            Constraint::Length(HEADER_HEIGHT),
            Constraint::Min(5),
            Constraint::Length(ACTIVITY_HEIGHT),
            Constraint::Length(FOOTER_HEIGHT),
        ])
        .split(area);
        self.render_header(frame, rows[0]);
        if self.show_language_selection {
            self.render_languages(frame, rows[1]);
        } else {
            self.render_navigation(frame, rows[1]);
        }
        self.render_activity(frame, rows[2]);
        self.render_footer(frame, rows[3]);
    }

    fn render_activity(&self, frame: &mut Frame, area: Rect) {
        let title = if self.workspace.is_running() {
            format!(
                " {} · {} ",
                self.i18n.t("activity.title"),
                self.i18n.t("activity.running")
            )
        } else {
            format!(" {} ", self.i18n.t("activity.title"))
        };
        let content = self.workspace.activity_text_with_i18n(&self.i18n);
        let content_width = area.width.saturating_sub(2);
        let viewport = area.height.saturating_sub(2);
        let line_count = wrapped_line_count(&content, content_width);
        let bottom = u16::try_from(line_count)
            .unwrap_or(u16::MAX)
            .saturating_sub(viewport);
        let activity = Paragraph::new(content)
            .block(Block::default().title(title).borders(Borders::ALL))
            .wrap(Wrap { trim: false })
            .scroll((bottom, 0));
        frame.render_widget(activity, area);
    }

    fn render_header(&self, frame: &mut Frame, area: Rect) {
        let focus = match self.focus {
            Focus::Navigation => "focus.menu",
            Focus::Content => "focus.content",
        };
        let title = format!(
            " InstructionX Setup {} · {} · {}: {} ",
            setup_build_version(),
            self.i18n.t(self.page.title_key()),
            self.i18n.t("focus.label"),
            self.i18n.t(focus)
        );
        let block = Block::default()
            .title(title)
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::Cyan));
        frame.render_widget(block, area);
    }

    fn render_languages(&self, frame: &mut Frame, area: Rect) {
        let items = Language::ALL.iter().map(|language| {
            let marker = if Language::ALL[self.language_index] == *language {
                "▸ "
            } else {
                "  "
            };
            ListItem::new(format!("{marker}{}", language_display_name(*language)))
        });
        let list = List::new(items)
            .block(
                Block::default()
                    .title(format!(" {} ", self.i18n.t("language.title")))
                    .borders(Borders::ALL),
            )
            .highlight_style(Style::default().fg(Color::LightCyan));
        frame.render_widget(list, area);
    }

    fn render_navigation(&self, frame: &mut Frame, area: Rect) {
        let columns =
            Layout::horizontal([Constraint::Length(NAVIGATION_WIDTH), Constraint::Min(20)])
                .split(area);
        let items = Page::ALL.iter().map(|page| {
            let marker = if *page == self.page { "▸ " } else { "  " };
            let text = format!("{marker}{} {}", page.index(), self.i18n.t(page.title_key()));
            let style = if *page == self.page {
                Style::default()
                    .fg(Color::LightCyan)
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default()
            };
            ListItem::new(text).style(style)
        });
        let navigation = List::new(items).block(
            Block::default()
                .title(format!(" {} ", self.i18n.t("focus.menu")))
                .borders(Borders::ALL)
                .border_style(Style::default().fg(if self.focus == Focus::Navigation {
                    Color::LightCyan
                } else {
                    Color::DarkGray
                })),
        );
        frame.render_widget(navigation, columns[0]);
        let content_text = if self.page == Page::Overview {
            self.overview_text()
        } else {
            self.workspace.render_with_i18n(self.page, &self.i18n)
        };
        let content_width = columns[1].width.saturating_sub(2);
        let line_count = wrapped_line_count(&content_text, content_width);
        self.content_height
            .set(u16::try_from(line_count).unwrap_or(u16::MAX));
        self.content_viewport
            .set(columns[1].height.saturating_sub(2));
        let content = Paragraph::new(content_text)
            .block(
                Block::default()
                    .title(format!(" {} ", self.i18n.t(self.page.title_key())))
                    .borders(Borders::ALL)
                    .border_style(Style::default().fg(if self.focus == Focus::Content {
                        Color::LightCyan
                    } else {
                        Color::DarkGray
                    })),
            )
            .wrap(Wrap { trim: false })
            .scroll((self.content_scroll.min(self.max_scroll()), 0));
        frame.render_widget(content, columns[1]);
    }

    fn overview_text(&self) -> String {
        let Some(overview) = &self.overview else {
            return self.i18n.t("overview.placeholder").to_string();
        };
        let mut text = String::new();
        self.write_localized(
            &mut text,
            "overview.os",
            &[
                ("name", &overview.os_name),
                ("version", &overview.os_version),
                ("architecture", &overview.architecture),
            ],
        );
        self.write_localized(
            &mut text,
            "overview.kernel_host",
            &[
                ("kernel", &overview.kernel_version),
                ("host", &overview.host_name),
            ],
        );
        let physical = display_optional(overview.physical_cores, &self.i18n);
        let logical = overview.logical_cores.to_string();
        self.write_localized(
            &mut text,
            "overview.cpu",
            &[
                ("model", &overview.cpu_model),
                ("physical", &physical),
                ("logical", &logical),
            ],
        );
        let total = format_bytes(overview.memory_total_bytes);
        let available = format_bytes(overview.memory_available_bytes);
        self.write_localized(
            &mut text,
            "overview.memory",
            &[("total", &total), ("available", &available)],
        );
        self.append_hardware_text(&mut text, overview);
        self.append_framework_text(&mut text, overview);
        text
    }

    fn write_localized(&self, text: &mut String, key: &str, arguments: &[(&str, &str)]) {
        let line = self.i18n.format_values(key, arguments);
        let _ = writeln!(text, "{line}");
    }

    fn append_hardware_text(&self, text: &mut String, overview: &SystemOverview) {
        for module in &overview.memory_modules {
            let capacity = format_bytes(module.capacity_bytes.unwrap_or_default());
            let speed = display_optional(module.speed_mts, &self.i18n);
            self.write_localized(
                text,
                "overview.ram",
                &[
                    ("slot", &module.slot),
                    ("capacity", &capacity),
                    ("manufacturer", &module.manufacturer),
                    ("part", &module.part_number),
                    ("speed", &speed),
                ],
            );
        }
        for disk in &overview.disks {
            let size = format_bytes(disk.size_bytes.unwrap_or_default());
            self.write_localized(
                text,
                "overview.disk",
                &[("model", &disk.model), ("size", &size)],
            );
        }
        for volume in &overview.volumes {
            let total = format_bytes(volume.total_bytes);
            let free = format_bytes(volume.available_bytes);
            self.write_localized(
                text,
                "overview.volume",
                &[
                    ("mount", &volume.mount_point),
                    ("filesystem", &volume.file_system),
                    ("total", &total),
                    ("free", &free),
                ],
            );
        }
        self.append_display_network_text(text, overview);
    }

    fn append_display_network_text(&self, text: &mut String, overview: &SystemOverview) {
        for monitor in &overview.monitors {
            self.write_localized(
                text,
                "overview.monitor",
                &[("name", &monitor.name), ("details", &monitor.details)],
            );
        }
        for network in &overview.networks {
            let addresses = network.ip_addresses.join(", ");
            self.write_localized(
                text,
                "overview.network",
                &[
                    ("name", &network.name),
                    ("mac", &network.mac_address),
                    ("addresses", &addresses),
                ],
            );
        }
        for warning in &overview.warnings {
            self.write_localized(text, "overview.warning", &[("warning", warning)]);
        }
    }

    fn append_framework_text(&self, text: &mut String, overview: &SystemOverview) {
        let status = &overview.framework;
        let path = overview.tui_path.display().to_string();
        self.write_localized(text, "overview.tui_path", &[("path", &path)]);
        let installed = if status.installed {
            "overview.installed"
        } else {
            "overview.not_installed"
        };
        let installed = self.i18n.t(installed).to_string();
        let version = status
            .version
            .as_deref()
            .unwrap_or_else(|| self.i18n.t("common.unknown"))
            .to_string();
        self.write_localized(
            text,
            "overview.framework",
            &[("status", &installed), ("version", &version)],
        );
        let git = status.git_present.to_string();
        let uv = status.uv_present.to_string();
        let venv = status.venv_present.to_string();
        self.write_localized(
            text,
            "overview.tools",
            &[("git", &git), ("uv", &uv), ("venv", &venv)],
        );
        let address = self.public_ip_text();
        self.write_localized(text, "overview.public_ip", &[("address", &address)]);
    }

    fn public_ip_text(&self) -> String {
        if let Some(address) = &self.public_ip {
            return address.clone();
        }
        if let Some(error) = &self.public_ip_error {
            return self
                .i18n
                .format_values("overview.unavailable", &[("error", error)]);
        }
        self.i18n.t("overview.not_fetched").to_string()
    }

    fn render_footer(&self, frame: &mut Frame, area: Rect) {
        let key = if self.show_language_selection {
            "language.hint"
        } else {
            "nav.hint"
        };
        let footer = Paragraph::new(self.i18n.t(key))
            .block(Block::default().borders(Borders::ALL))
            .style(Style::default().fg(Color::Gray));
        frame.render_widget(footer, area);
    }

    fn render_small_terminal(&self, frame: &mut Frame, area: Rect) {
        let width = area.width.to_string();
        let height = area.height.to_string();
        let message = self.i18n.format_values(
            "terminal.too_small",
            &[("width", &width), ("height", &height)],
        );
        frame.render_widget(Paragraph::new(message), area);
    }

    pub fn render_text(&self, width: u16, height: u16) -> io::Result<String> {
        let backend = TestBackend::new(width, height);
        let mut terminal =
            Terminal::new(backend).map_err(|_| io::Error::other("初始化 Ratatui 测试终端失败"))?;
        terminal
            .draw(|frame| self.render(frame))
            .map_err(|_| io::Error::other("渲染 Ratatui 测试终端失败"))?;
        Ok(buffer_text(terminal.backend().buffer()))
    }
}

fn language_display_name(language: Language) -> &'static str {
    match language {
        Language::English => "English (Default)",
        Language::Chinese => "中文",
        Language::French => "Français",
        Language::Russian => "Русский",
    }
}

fn display_optional<T>(value: Option<T>, i18n: &I18n) -> String
where
    T: std::fmt::Display,
{
    value
        .map(|value| value.to_string())
        .unwrap_or_else(|| i18n.t("common.unknown").to_string())
}

fn format_bytes(bytes: u64) -> String {
    const KIB: f64 = 1024.0;
    const MIB: f64 = KIB * 1024.0;
    const GIB: f64 = MIB * 1024.0;
    const TIB: f64 = GIB * 1024.0;
    let value = bytes as f64;
    if value >= TIB {
        format!("{:.2} TiB", value / TIB)
    } else if value >= GIB {
        format!("{:.2} GiB", value / GIB)
    } else if value >= MIB {
        format!("{:.2} MiB", value / MIB)
    } else {
        format!("{:.2} KiB", value / KIB)
    }
}

fn wrapped_line_count(text: &str, width: u16) -> usize {
    let width = usize::from(width.max(1));
    text.lines()
        .map(|line| {
            let line_width = UnicodeWidthStr::width(line);
            line_width.max(1).div_ceil(width)
        })
        .sum()
}

fn buffer_text(buffer: &ratatui::buffer::Buffer) -> String {
    let mut output = String::new();
    for y in 0..buffer.area.height {
        let mut line = String::new();
        for x in 0..buffer.area.width {
            line.push_str(buffer[(x, y)].symbol());
        }
        output.push_str(line.trim_end());
        output.push('\n');
    }
    output
}

pub fn run_terminal(mut app: App) -> Result<(), Box<dyn Error>> {
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen, EnableMouseCapture)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;
    let result = run_event_loop(&mut terminal, &mut app);
    disable_raw_mode()?;
    execute!(
        terminal.backend_mut(),
        DisableMouseCapture,
        LeaveAlternateScreen
    )?;
    terminal.show_cursor()?;
    result
}

fn run_event_loop(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    app: &mut App,
) -> Result<(), Box<dyn Error>> {
    while !app.should_quit {
        if app.workspace.poll_operation() {
            app.refresh_overview();
        }
        terminal.draw(|frame| app.render(frame))?;
        if !event::poll(EVENT_POLL_INTERVAL)? {
            continue;
        }
        match event::read()? {
            Event::Key(key) => app.handle_key_event(key)?,
            Event::Mouse(mouse) => app.handle_mouse(mouse.kind),
            _ => {}
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn workspace_page_includes_persistent_activity_panel() {
        let temporary = tempfile::tempdir().expect("创建临时目录");
        let preferences = Preferences {
            needs_language_selection: true,
            ..Preferences::default()
        };
        let mut app = App::new(preferences, temporary.path().join(".tui/preferences.toml"));
        app.show_language_selection = false;
        app.page = Page::Misc;

        let rendered = app.render_text(100, 30).expect("渲染界面");

        assert!(rendered.contains("Activity"));
        assert!(rendered.contains("Ready"));
        assert!(rendered.contains("logs/tui_setup.log"));
    }

    #[test]
    fn activity_automatically_scrolls_wrapped_output_to_the_latest_line() {
        let temporary = tempfile::tempdir().expect("创建临时目录");
        let preferences = Preferences {
            needs_language_selection: true,
            ..Preferences::default()
        };
        let mut app = App::new(preferences, temporary.path().join(".tui/preferences.toml"));
        app.show_language_selection = false;
        app.page = Page::Misc;
        app.workspace.record_output(&"x".repeat(800));
        app.workspace.record_output("latest-activity-marker");

        let rendered = app.render_text(80, 30).expect("渲染界面");

        assert!(rendered.contains("latest-activity-marker"));
    }

    #[test]
    fn chinese_overview_translates_framework_and_network_labels() {
        let temporary = tempfile::tempdir().expect("创建临时目录");
        let preferences = Preferences {
            language: Language::Chinese,
            needs_language_selection: true,
        };
        let mut app = App::new(preferences, temporary.path().join(".tui/preferences.toml"));
        app.show_language_selection = false;
        app.overview = Some(SystemOverview::collect(temporary.path()));

        let text = app.overview_text();

        assert!(text.contains("操作系统："), "{text}");
        assert!(text.contains("框架："), "{text}");
        assert!(text.contains("公网 IP"), "{text}");
        assert!(!text.contains("Public IP"));
    }

    #[test]
    fn chinese_install_page_translates_tools_empty_release_and_menu() {
        let temporary = tempfile::tempdir().expect("创建临时目录");
        let preferences = Preferences {
            language: Language::Chinese,
            needs_language_selection: true,
        };
        let mut app = App::new(preferences, temporary.path().join(".tui/preferences.toml"));
        app.show_language_selection = false;
        app.page = Page::Install;

        let rendered = app.render_text(120, 30).expect("渲染界面");
        let compact = rendered.replace(' ', "");

        assert!(compact.contains("工具："), "{rendered}");
        assert!(compact.contains("尚未加载Release"), "{rendered}");
        assert!(compact.contains("菜单"), "{rendered}");
        assert!(!rendered.contains("Tools:"));
        assert!(!rendered.contains("No Releases loaded"));
    }

    #[test]
    fn chinese_activity_uses_chinese_status_and_progress_labels() {
        let temporary = tempfile::tempdir().expect("创建临时目录");
        let preferences = Preferences {
            language: Language::Chinese,
            needs_language_selection: true,
        };
        let mut app = App::new(preferences, temporary.path().join(".tui/preferences.toml"));
        app.show_language_selection = false;
        app.page = Page::Misc;
        app.workspace
            .start_operation(crate::operations::OperationRequest::CleanTemp {
                root: temporary.path().to_path_buf(),
            })
            .expect("启动操作");

        let rendered = app.render_text(100, 30).expect("渲染界面");

        let compact = rendered.replace(' ', "");
        assert!(compact.contains("状态：正在运行"), "{rendered}");
        assert!(compact.contains("清理临时文件"));
        assert!(compact.contains("日志："));
    }
}
