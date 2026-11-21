use std::error::Error;
use std::path::{Path, PathBuf};

use clap::Parser;

use crate::app::{App, Page};
use crate::i18n::{I18n, Language, Preferences};
use crate::operations::{OperationUpdate, execute_operation, request_for_action};
use crate::system::SystemOverview;
use crate::version::setup_build_version;

#[derive(Debug, Parser)]
#[command(
    name = "instructionx-setup",
    disable_version_flag = true,
    about = "InstructionX native setup TUI"
)]
pub struct Cli {
    #[arg(long = "version", short = 'V', help = "Show Setup build version")]
    pub show_version: bool,
    #[arg(long)]
    pub lang: Option<String>,
    #[arg(long)]
    pub preview: Option<String>,
    #[arg(long)]
    pub no_color: bool,
    #[arg(long)]
    pub check: bool,
    #[arg(long)]
    pub state: bool,
    #[arg(long)]
    pub action: Option<String>,
    #[arg(long)]
    pub archive: Option<PathBuf>,
    #[arg(long)]
    pub release_tag: Option<String>,
    #[arg(long)]
    pub dry_run: bool,
    #[arg(long)]
    pub yes: bool,
    #[arg(long)]
    pub project_root: Option<PathBuf>,
}

pub fn normalize_legacy_args<I>(arguments: I) -> Vec<String>
where
    I: IntoIterator<Item = String>,
{
    arguments
        .into_iter()
        .map(|argument| match argument.as_str() {
            "-Check" | "-check" => "--check".to_string(),
            "-State" | "-state" => "--state".to_string(),
            "-Preview" | "-preview" => "--preview".to_string(),
            "-Action" | "-action" => "--action".to_string(),
            "-ArchivePath" | "-archive" => "--archive".to_string(),
            "-ReleaseTag" | "-release-tag" => "--release-tag".to_string(),
            "-DryRun" | "-dryrun" | "--dryrun" => "--dry-run".to_string(),
            "-Yes" | "-yes" => "--yes".to_string(),
            "-Lang" | "-lang" => "--lang".to_string(),
            "-NoColor" | "-no-color" => "--no-color".to_string(),
            _ => argument,
        })
        .collect()
}

pub fn execute(cli: Cli) -> Result<(), Box<dyn Error>> {
    if cli.show_version {
        println!("instructionx-setup {}", setup_build_version());
        return Ok(());
    }
    let root = cli
        .project_root
        .clone()
        .or_else(|| std::env::var_os("INSTRUCTIONX_PROJECT_ROOT").map(PathBuf::from))
        .unwrap_or(std::env::current_dir()?);
    if cli.check {
        print!("{}", doctor_text(&root));
        return Ok(());
    }
    if cli.state {
        print!("{}", state_text(&root));
        return Ok(());
    }
    if cli.action.is_some() {
        return execute_action(root, &cli);
    }
    execute_interactive(root, &cli)
}

fn execute_action(root: PathBuf, cli: &Cli) -> Result<(), Box<dyn Error>> {
    let action = cli.action.as_deref().unwrap_or_default();
    if action == "doctor" {
        let overview = SystemOverview::collect(&root);
        println!("Framework installed: {}", overview.framework.installed);
        return Ok(());
    }
    if cli.dry_run {
        print_dry_run(&root, cli, action);
        return Ok(());
    }
    let request = request_for_action(
        &root,
        action,
        cli.archive.as_deref(),
        cli.release_tag.as_deref(),
        cli.yes,
    )?;
    let i18n = action_i18n(&root, cli)?;
    let success = execute_operation(request, |update| print_update(update, &i18n))?;
    let summary = success.summary_key.map_or_else(
        || success.summary.clone(),
        |key| i18n.format(key, &success.summary_args),
    );
    println!("{summary}");
    for detail in success.details {
        let text = detail
            .key
            .map(|key| i18n.format(key, &detail.args))
            .unwrap_or(detail.text);
        println!("{text}");
    }
    Ok(())
}

fn action_i18n(root: &Path, cli: &Cli) -> Result<I18n, Box<dyn Error>> {
    let preferences_path = root.join(".tui/preferences.toml");
    let preferences = Preferences::load(&preferences_path)?;
    let language = cli
        .lang
        .as_deref()
        .map_or(preferences.language, Language::from_code);
    Ok(I18n::new(language))
}

fn print_dry_run(root: &Path, cli: &Cli, action: &str) {
    println!("Dry run: no files, directories, configuration or environments will be changed");
    println!("Project root: {}", root.display());
    println!("Action: {action}");
    println!("Archive: {:?}", cli.archive);
    println!("Release Tag: {:?}", cli.release_tag);
    println!("Automatic tool installation and confirmations: {}", cli.yes);
}

fn print_update(update: OperationUpdate, i18n: &I18n) {
    let message = i18n.format(update.key, &update.args);
    if update.total > 0 {
        println!("[{}/{}] {message}", update.current, update.total);
    } else {
        println!("  {message}");
    }
}

fn execute_interactive(root: PathBuf, cli: &Cli) -> Result<(), Box<dyn Error>> {
    let preferences_path = root.join(".tui/preferences.toml");
    let mut preferences = Preferences::load(&preferences_path)?;
    if let Some(code) = &cli.lang {
        preferences.language = Language::from_code(code);
        preferences.needs_language_selection = false;
    }
    if cli.preview.as_deref() == Some("language") {
        preferences.needs_language_selection = true;
    }
    let mut app = App::new(preferences, preferences_path);
    if let Some(preview) = &cli.preview {
        if preview != "language" {
            app.page = Page::from_name(preview)
                .ok_or_else(|| format!("Unknown preview page: {preview}"))?;
        }
        print!("{}", app.render_text(100, 30)?);
        return Ok(());
    }
    crate::app::run_terminal(app)
}

fn doctor_text(root: &Path) -> String {
    let overview = SystemOverview::collect(root);
    let status = &overview.framework;
    format!(
        "OS: {} {}\nCPU: {}\nFramework installed: {}\nGit: {}\nuv: {}\n.venv: {}\n",
        overview.os_name,
        overview.os_version,
        overview.cpu_model,
        status.installed,
        status.git_present,
        status.uv_present,
        status.venv_present,
    )
}

fn state_text(root: &Path) -> String {
    let overview = SystemOverview::collect(root);
    let status = &overview.framework;
    format!(
        "setup_version={}\nproject_root={}\nframework_version={}\ngit_available={}\nuv_available={}\nvenv_exists={}\ninstalled={}\ntui_path={}\n",
        setup_build_version(),
        root.display(),
        status.version.as_deref().unwrap_or(""),
        status.git_present,
        status.uv_present,
        status.venv_present,
        status.installed,
        overview.tui_path.display(),
    )
}
