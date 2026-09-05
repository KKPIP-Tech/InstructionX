<div align="center">

<img src="./assets/logo.png" alt="InstructionX Logo" width="100%">

# InstructionX

**A PySide6-based plugin-oriented desktop application framework — LLM integration · Bidirectional MCP protocol support · Hot-swappable plugin system**

[![CI](https://github.com/KKPIP-Tech/InstructionX/actions/workflows/test.yml/badge.svg)](https://github.com/KKPIP-Tech/InstructionX/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/Python-3.14+-blue.svg)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/PySide6-6.10+-green.svg)](https://doc.qt.io/qtforpython/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-lightgrey.svg)](#)
[![Version](https://img.shields.io/badge/Alpha-1.1.0%20CE-red.svg)](#)
[![License](https://img.shields.io/badge/License-Commercial%20Source-orange.svg)](LICENSE)

[中文版](README.md) | English Version

</div>

---

## Introduction

InstructionX is a **plugin-oriented desktop application framework** built on PySide6. It unifies plugin hot-swapping, multi-provider LLM integration, bidirectional MCP protocol support, data persistence, and background task management into a single infrastructure, allowing users to freely compose tool plugins around their own workflows and build a personalized all-in-one Tools Cluster.

The framework itself ships no business functionality: every capability is plugged in as a plugin and distributed through the GitHub plugin-repository ecosystem. Developers can rapidly build and publish their own plugins on top of the framework's standardized plugin interfaces, dependency-injected service container, and the UIKit component library.

> This is an application project: it runs directly from source and is not distributed as a library.

## Screenshots

<!-- TODO: Application screenshots to be added. Place image files in assets/ (e.g. assets/screenshot-main.png) and replace this placeholder. -->

> Application screenshots coming soon.

## Core Features

### Plugin System

- **Lifecycle Management**: Hot-load / hot-unload / hot-reload plugins without restarting the application; uninstalling automatically cleans up associated data such as the plugin identity and language overrides
- **Installation & Updates**: The built-in GitHub installer supports single-plugin repositories (IXPlugin.json) and multi-plugin repositories (IXRepo.json), with background installation and progress display; local zip installation and GitHub Release upgrade/downgrade with version-relation detection are supported; repositories under the KKPIP-Tech organization are automatically classified as official plugins
- **Versioning & Identity Governance**: Semantic plugin versions (alpha / beta / pre-release / release) and a per-plugin UUID identity; the installed-plugin registry records version / source / install time as the basis for upgrades and update checks; Python dependencies declared by plugins are installed automatically by the framework (uv first, pip as fallback)
- **Cross-Plugin Collaboration**: Declaring `service_api` automatically registers cross-plugin APIs and exposes them as MCP tools; plugins can also register tools directly with the LLM via `llm_tools`
- **Panel Organization**: The skills panel supports custom groups, folding, and mixed ordering; plugin UI state is cached when switching plugins and fully restored on return

### LLM Integration

- **Multi-Provider Support**: Five built-in provider presets — MiniMax, SiliconFlow, Zhipu GLM, Ollama, and OpenAI — plus an `openai-compatible` fallback adapter for zero-code integration with any OpenAI-compatible endpoint
- **Multi-Conversation Management**: Conversation creation / switching / persistence, with automatic context truncation based on token estimation when the window is exceeded (system prompt and recent messages are preserved)
- **Automated Tool Calling**: ToolCallExecutor automatically handles the multi-turn tool-calling loop (default `max_turns=5`); plugins only need to register their tools
- **Multimodal**: Image understanding (Vision), image generation, TTS voice synthesis, and Embedding support
- **Usage Statistics**: Per-conversation and global token consumption and cost estimation, with a built-in visualization panel (AI → Usage)

### Bidirectional MCP Protocol Support

- **MCP Server**: Automatically exposes all plugin APIs as MCP tools over stdio and HTTP transport, with optional Bearer authentication; MCP clients such as Claude Code can invoke plugin capabilities directly
- **MCP Client**: Connects to external MCP Servers and registers their tools into the local ToolRegistry for LLM invocation
- **Bidirectional Bridge**: MCPBridge automatically synchronizes the plugin API registry with the MCP Server

### Data Persistence

- **SQLite WAL + Explicit Transactions**: The default backend, resilient against unexpected interruptions; a JSON backend is available via environment variable
- **Dual Namespaces**: PRIVATE space is visible only within a plugin; PUBLIC space enables cross-plugin sharing
- **Pub/Sub**: Plugins can subscribe to data changes for reactive interactions; an in-memory cache reduces disk I/O

### Background Task System

- **Thread-Pool Async Tasks**: Four worker threads keep the UI responsive
- **Scheduled & Long-Running Tasks**: Fixed-interval recurring execution; long-running tasks support graceful shutdown and automatic restart
- **Task Persistence**: Task states survive restarts and are rebuilt automatically via the task factory mechanism

### Internationalization (i18n)

- **XML Language Files**: Both the framework and plugins follow a one-XML-file-per-language convention, with Chinese (default) and English built in
- **Live Switching**: Switch the UI language instantly from the Edit → Language menu without restarting
- **Fallback Chain**: Entries missing in the current language automatically fall back to the default language
- **Per-Plugin Language Override**: Individual plugins may use a UI language different from the framework

### User Interface

- **InstructionX_UIKit Component Library**: 58 components + 13 layouts + 52 animations, including a native chart engine, a blueprint node graph, and Mermaid rendering; three global theme modes (light / dark / auto) with design tokens that restyle in real time
- **Font Manager**: Application-level font install / uninstall / preview (process-local, no writes to the system font directory), with automatic fallback to system fonts
- **System Tray**: The tray menu presents running plugins and background tasks in real time; closing the main window prompts a confirmation dialog offering exit or minimize-to-tray

## Quick Start

### Requirements

- Windows 10 / 11
- Python 3.14 or higher
- [uv](https://docs.astral.sh/uv/) (Python virtual environment & dependency manager)

### Install uv

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Install Dependencies

The first run of `uv run main.py` automatically creates a virtual environment and syncs dependencies from `uv.lock`; you may also install them explicitly first:

```bash
uv venv
uv pip install -r requirements.txt
```

> Note: Do **not** use `uv sync` — it strictly reconciles to `uv.lock` and **removes** extra packages installed in the environment (e.g., plugin dependencies installed via the framework's DependencyManager, or test dependencies).

### Run

```bash
uv run main.py
```

The `data/` and `config/` directories are created automatically on first run.

## Plugin Ecosystem

InstructionX is a plugin framework and ships no built-in business plugins. Ways to obtain plugins:

- **GitHub Installation**: Menu "Edit → Install Plugin from GitHub..." — enter a plugin repository URL for one-click installation
- **Manual Installation**: Copy plugins obtained from third-party developers into the `custom_plugin/` directory

### Plugin Structure

Each plugin is a top-level subdirectory under `plugin/` (official) or `custom_plugin/` (third-party):

```
my_plugin/
├── entrance.py      # Required: Plugin entry, defines the IPlugin subclass
├── information.py   # Required: Plugin metadata (IPluginInfo subclass: version, icon, service_api, etc.)
├── service.py       # Required: Plugin service / public API layer
├── config/          # Required: Plugin configuration directory
├── text/            # Required: Language pack directory (<language-code>.xml, one file per language)
└── assets/          # Optional: Static assets directory
```

When `service_api` is provided and the service class name ends with `Service`, the framework automatically registers the cross-plugin API and syncs it as MCP tools.

### Plugin Metadata

A plugin repository describes each plugin via `IXPlugin.json`, where `name` and `description` support multi-language fields:

```json
{
    "id": "my-plugin",
    "name": {"zh": "我的插件", "en": "My Plugin"},
    "version": "release.1.0.0",
    "main": "entrance.py",
    "description": {"zh": "插件简介", "en": "Short description."},
    "author": "Your Name",
    "keywords": ["instructionx", "plugin"]
}
```

Multi-plugin repositories additionally require an `IXRepo.json` index file.

### Framework Services Available to Plugins

The framework automatically injects the `PluginServices` container when creating a plugin instance, giving plugins direct access to the framework's full infrastructure:

| Service | Description |
|---------|-------------|
| `services.llm_facade` | LLM plugin service facade: multi-conversation chat, tool calling, multimodal, usage statistics |
| `services.data_provider` | DataProvider data layer: PRIVATE / PUBLIC namespaces, pub/sub |
| `services.task_manager` | BackgroundTaskManager: async / scheduled / long-running tasks |
| `services.logger` | Logging interface (ILogger) |
| `services.mcp_manager` | MCP Server management: expose plugin APIs as MCP tools |
| `services.mcp_client` | MCP Client: connect to external MCP Servers |
| `services.font_manager` | Font manager: font resolution with fallback chains |
| `services.localization` | i18n facade (bound to the plugin UUID) |

### Minimal Plugin Example

```python
from core import IPlugin
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout

class MyPlugin(IPlugin):
    @property
    def plugin_name(self) -> str:
        """Name displayed in the skills panel"""
        return "My\nPlugin"

    @property
    def skill_description(self) -> str:
        return "This is a sample plugin"

    def _create_widget(self, parent=None, data_provider=None):
        """Create the plugin UI"""
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("Hello from MyPlugin!"))
        return widget
```

### Sample Plugins

The `plugin/` directory provides reference samples for local development: [framework-api-demo](plugin/framework-api-demo) (framework core API demos: data persistence, background tasks, LLM, MCP, cross-plugin calls), [ui-demo](plugin/ui-demo), and [blueprint-opencv](plugin/blueprint-opencv). See the [plugin index](docs/plugins/index.md) for details.

### Plugin Development Documentation

- [Plugin Development Guide (English)](Plugin-Development-Guide.md)
- [Plugin Development Guide (Chinese)](docs/core/plugin-system/plugin-development.md)
- [IPlugin Interface Details](docs/core/plugin-system/iplugin.md)
- [LLM Integration Guide](docs/plugins/llm-integration-guide.md)

## Documentation

Complete technical documentation (in Chinese) is available under [docs/](docs/README.md), covering:

- **Architecture**: [System Architecture Overview](docs/architecture/overview.md), [Module Dependencies](docs/architecture/module-dependencies.md)
- **Core Modules**: [Plugin System](docs/core/plugin-system/overview.md), [DataProvider](docs/core/data-provider/overview.md), [Background Tasks](docs/core/background-task/overview.md), [LLM Provider](docs/core/llm-provider/overview.md), [MCP Protocol](docs/core/mcp/overview.md), [i18n Subsystem](docs/core/i18n/overview.md), [Font Manager](docs/core/font-manager/overview.md)
- **UI**: [Main Window](docs/ui/main-window.md), [System Tray & Close Behavior](docs/ui/system-tray.md), [UIKit Theme System](docs/utils/uikit-theme.md)
- **API Reference**: [Full API Index](docs/api/full-reference.md)

## Project Structure

```
main.py            # Application entry point
core/              # Framework core: interfaces / plugin system / data layer / background tasks / LLM / MCP / fonts / i18n
ui/                # UI layer: main window / skills panel / work area / system tray / dialogs / InstructionX_UIKit
utils/             # Utility modules (logging, thread marshaling, etc.)
plugin/            # Official / sample plugins (for local development verification)
custom_plugin/     # Third-party plugin directory
scripts/           # Smoke / screenshot / demo scripts
test/              # pytest tests
docs/              # Technical documentation
config/            # Generated at runtime: configuration files
data/              # Generated at runtime: database, task states, fonts, etc.
logs/              # Generated at runtime: application logs
```

## Configuration & Data

The following files are generated at runtime; do not modify their structure manually:

| File | Purpose |
|------|---------|
| `config/llm_providers.json` | LLM provider instance configuration (API keys stored obfuscated) |
| `config/llm_models_cache.json` | Model list cache |
| `config/mcp_config.json` | MCP Server / Client configuration |
| `config/plugin_order.json` | Display order of ungrouped plugins |
| `config/plugin_groups.json` | User-defined plugin groups and panel ordering |
| `config/plugin_registry.json` | Installed plugin registry (basis for upgrade/downgrade) |
| `config/i18n.json` | Framework language settings |
| `config/plugin_languages.json` | Per-plugin language overrides |
| `data/data.db` | Plugin data (SQLite + WAL) |
| `data/tasks.json` | Background task states |
| `data/llm_usage.json` | LLM usage records |
| `data/conversations.json` | LLM conversation persistence |
| `data/fonts/` | Framework-installed fonts and registry |
| `logs/application.log` | Application logs |

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `INSTRUCTIONX_DATAPROVIDER_BACKEND` | Data layer backend: `sqlite` (default) / `json` |
| `INSTRUCTIONX_MCP_CONFIG` | Override the MCP configuration file path |
| `INSTRUCTIONX_GITHUB_TOKEN` | GitHub API token: raises rate limits for plugin installation / update checks |
| `INSTRUCTIONX_LOG_DIR` | Override the log output directory |
| `INSTRUCTIONX_LOG_LEVEL` | Override the log level (`DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`) |
| `DEVELOPMENT_MODE` | Development mode toggle |

## Testing & CI

```bash
pip install -e ".[test]"
python -m pytest test/ -q --tb=short -p no:cacheprovider
```

- CI runs on GitHub Actions (`windows-latest` + Python 3.14), triggered by pushes to `dev` / `main` and by all pull requests
- The `scripts/` directory provides offline smoke scripts for core paths (`smoke_*.py`), language-file completeness checks (`check_i18n_completeness.py`), MCP SDK smoke tests, and other standalone verification scripts

## Contributing & Support

- **Issue Reporting**: If you encounter problems or have feature suggestions, please file an [Issue](https://github.com/KKPIP-Tech/InstructionX/issues)
- **Branch Conventions**: `dev` is the development branch (no test code), pytest test code lives exclusively on the `test` branch, and `main` is the release branch
- **Documentation Language**: Project documentation and code comments are primarily in Chinese

## Tech Stack

| Technology | Purpose | Version |
|------------|---------|---------|
| Python | Programming language | >= 3.14 |
| PySide6 | Qt GUI framework | >= 6.10 |
| mcp | MCP protocol (FastMCP) | >= 1.28.1, < 2 |
| requests / aiohttp | HTTP / async HTTP | >= 2.32 / >= 3.11 |
| orjson | High-performance JSON serialization | >= 3.11.0, < 4 |
| matplotlib | Usage statistics and UIKit MarkdownView LaTeX formula rendering | >= 3.10 |
| packaging | Plugin dependency version checking | >= 23.0 |
| qrcode[pil] | UIKit QRCodeView component | >= 7.4 |
| InstructionX_UIKit | UI theme & component library | Built-in (alpha-v1.0.2) |

## License

InstructionX is licensed under the **InstructionX Commercial Source License** (a commercial source-available license; **this is not an open-source license**):

- **Personal, non-commercial use**: Free to use
- **Organizational use**: Organizations with more than 100 global employees (including corporations, non-profits, educational institutions, and government bodies) require written authorization
- **Deployment scale**: More than 30 installed instances require written authorization
- **SaaS / multi-tenant service**: Prohibited without authorization
- **Redistribution**: Requires written authorization

See [LICENSE](LICENSE) for the complete terms.
