

<div align="center">

<img src="./assets/logo.png" alt="InstructionX Logo" width="100%">

[English Version](README_EN.md) | 中文版

[![Python](https://img.shields.io/badge/Python-3.14+-blue.svg)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/PySide6-6.10+-green.svg)](https://doc.qt.io/qtforpython/)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)](#)
[![License](https://img.shields.io/badge/License-Modified%20Apache%202.0-orange.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-0.1.0%20CE-blue.svg)](#)

> A PySide6-based plugin desktop application framework with LLM integration, MCP Protocol (Server/Client), multi-conversation management, and hot-swappable plugin system

</div>

---

## Introduction

InstructionX is a powerful **plugin integration framework** that allows you to combine various utility tools into a unified desktop application based on your actual needs. Whether you're a developer, designer, or regular user, you can create your own **Tools Cluster** tailored to your workflow.

With InstructionX, you can:
- Freely combine the tool plugins you need
- Engage in intelligent conversations with multiple LLM providers
- Use MCP Function Calling to let AI invoke plugin capabilities
- Quickly switch between different work scenarios
- Save and sync your tool configurations
- Develop custom plugins to meet special requirements

---

## Core Features

### 🔌 Plugin Hot-Swapping

The plugin system supports **hot-loading** and **hot-unloading**, allowing you to add, remove, or update plugins without restarting the application. You can dynamically manage plugins at runtime to build a personalized tool collection.

### 📦 GitHub Plugin Installer

Built-in GitHub plugin installer for installing plugins from any GitHub URL:

- **URL Installation**: Install plugins by entering a GitHub repository URL
- **Single/Multi-Plugin Support**: Supports single-plugin repos (IXPlugin.json) and multi-plugin repos (IXRepo.json)
- **Background Installation**: Installation runs in the background with progress display
- **Auto-Classification**: Plugins from KKPIP-Tech organization are automatically classified as official plugins

### 🤖 LLM Integration & Conversation Management

Built-in multi-provider LLM integration with `LLMPluginService` providing complete conversation management and automated tool calling:

- **Multi-Provider Support**: MiniMax, SiliconFlow, Zhipu GLM, Ollama, and more
- **Conversation Management**: Multi-session creation, switching, automatic history management, context auto-truncation
- **ToolCallExecutor**: Automatic two-round tool calling loop, plugins only need to register tools
- **Multimodal Support**: Image understanding (Vision), image generation, TTS voice synthesis
- **Usage Statistics**: Per-conversation and global Token consumption and cost estimation
- **Embedding**: Vector embedding support
- **Model Caching**: Automatic model list fetching and caching at startup

### 🔗 MCP Protocol Support

Full Model Context Protocol support through the official MCP SDK:

- **MCP Server**: Expose all plugin APIs as MCP tools, supporting stdio and HTTP transport
- **MCP Client**: Connect to external MCP Servers, registering their tools in the local ToolRegistry
- **Bidirectional Bridge**: MCPBridge automatically syncs plugin API registrations to MCP Server
- **External Invocation**: Claude Code and other MCP Clients can directly call InstructionX plugin functionality

### 💾 Flexible Data Layer

**DataProvider** provides robust data persistence capabilities:
- **Atomic Writes**: Uses temporary file + rename mechanism to ensure data isn't corrupted by unexpected interruptions
- **Dual Namespaces**: PRIVATE space is only accessible within a plugin, PUBLIC space supports cross-plugin access
- **Pub/Sub**: Plugins can subscribe to data changes for reactive interactions
- **Memory Cache**: Reduces frequent disk I/O for better performance

### ⚙️ Background Task System

**BackgroundTaskManager** supports multiple task types:
- **Sync Tasks**: Execute immediately in the main thread, suitable for lightweight operations
- **Async Tasks**: Execute in a thread pool (4 worker threads), avoiding UI blocking
- **Scheduled Tasks**: Support fixed-interval recurring execution, suitable for timed reminders, data synchronization, etc.
- **Long-Running Tasks**: Support continuous operation, graceful shutdown, and auto-restart
- **Task Persistence**: Task states persist across application restarts
- **Task Factory**: Supports task recovery mechanism, automatically rebuilds tasks after restart

### 📊 Usage Panel

Built-in LLM usage statistics and visualization panel:

- **Statistics Cards**: Multi-dimensional data cards (Token consumption, cost, request count, etc.)
- **Trend Charts**: Display LLM usage changes over time
- **Filter & Query**: Filter records by Provider, Model, conversation ID
- **Paginated Table**: Detailed usage records table

### 🔗 Cross-Plugin Communication

Plugins can call each other's APIs to achieve functional collaboration:
- **API Registration & Discovery**: Plugins can register their APIs with the manager
- **Cross-Plugin Calls**: One plugin can call another plugin's functionality
- **Data Sharing**: Share data through the PUBLIC namespace

### 🎨 StyleQSS Theme System

Built-in complete StyleQSS styling system with modern interface appearance:
- **Manual Switching**: Support for light/dark/auto theme modes, switchable via menu or shortcuts
- **Auto Theme Detection**: Automatically switch between dark/light mode based on OS settings
- **30+ Control Styles**: Covering buttons, inputs, menus, dialogs, and other common Qt controls
- **9+ Button Variants**: primary, danger, success, outline, subtle, etc.
- **Dynamic Loading**: Dynamically load and apply QSS styles through style registry

### 🅰️ Multi-Font Support

Built-in FontMap font mapping system:

- **5 Font Families**: Alibaba PuHuiTi 3.0, Alimama FangYuanTi, Alimama DongFang DaKai, ZenDots, SmileySans
- **22 Font Files**: Covering standard weights, italics, etc.
- **State Machine Lookup**: FontMap.get_path() avoids hardcoded paths

### 💾 UI State Caching

When switching plugins, the plugin's UI state is automatically cached. When you return to a previously used plugin, the interface state is fully preserved, providing a smooth user experience.

---

## Quick Start

### Environment Requirements

- Python 3.14 or higher
- Windows 10/11

### Install Dependencies

```bash
pip install -r requirements.txt
```

Main dependencies:
- `PySide6` (>=6.10) - Qt GUI framework
- `requests` - HTTP requests
- `aiohttp` - Asynchronous HTTP client
- `opencv-python` - Image processing
- `numpy` - Numerical computation

### Run the Application

```bash
python main.py
```

---

## Plugin Ecosystem

InstructionX is a **plugin framework** and does not include built-in plugins. Users can obtain plugins through:

- **GitHub Installation**: Use the built-in GitHub plugin installer, enter the plugin repository URL to install with one click
- **Third-party Developers**: Get plugins from other developers, copy to the `custom_plugin/` directory

### Install Plugins

```bash
# Install plugins via GitHub URL
# Menu path: Edit → Install GitHub Plugin
```

### Develop Plugins

If you want to develop your own plugins, please refer to the [Plugin Development](docs/core/plugin-system/plugin-development.md) documentation.

---

## Architecture Overview

### Core Components

InstructionX uses **singleton pattern** for core components, ensuring global uniqueness:

```mermaid
graph TD
    A[InstructionXMainWindow<br/>Main Window] --> B[SkillsPanel<br/>Skills Panel]
    A --> C[WorkArea<br/>Work Area]

    B --> D[PluginManager<br/>Plugin Manager]
    C --> D

    D --> E[plugin/<br/>Official Plugins]
    D --> F[custom_plugin/<br/>Third-party Plugins]

    D --> G[DataProvider<br/>Data Layer]
    D --> H[BackgroundTaskManager<br/>Task Manager]
    D --> I[LLMProvider<br/>LLM Provider]
```

### Core Modules

| Module | Path | Description |
|--------|------|-------------|
| core/plugin | `core/plugin/` | Plugin system core |
| core/data | `core/data/` | Data persistence layer |
| core/task | `core/task/` | Background task system |
| core/llm | `core/llm/` | LLM provider framework |
| ui | `ui/` | User interface components |
| utils | `utils/` | Utility classes (logging, themes) |
| utils/style_qss | `utils/style_qss/` | StyleQSS styling system |
| plugin | `plugin/` | Official plugin directory |
| custom_plugin | `custom_plugin/` | Custom plugin directory |
| workers | `workers/` | Worker threads (reserved for extension) |
| docs | `docs/` | Technical documentation |
| core/interfaces | `core/interfaces/` | Abstract interface layer (IPlugin, IDataProvider, etc.) |
| core/mcp | `core/mcp/` | MCP protocol core (Server/Client/Bridge) |
| core/llm/plugin_service | `core/llm/plugin_service.py` | LLM plugin service layer (conversation management, tool calling) |
| core/llm/types | `core/llm/types.py` | LLM data types (Conversation, UsageStats, etc.) |
| core/plugin/github_plugin_installer | `core/plugin/github_plugin_installer.py` | GitHub plugin installer |
| ui/usage_panel | `ui/usage_panel.py` | Usage query panel |
| utils/font_map | `utils/font_map.py` | Font mapping system |

### Detailed Documentation

- [System Architecture Overview](docs/architecture/overview.md)
- [Module Dependencies](docs/architecture/module-dependencies.md)
- [Plugin System Overview](docs/core/plugin-system/overview.md)
- [DataProvider Overview](docs/core/data-provider/overview.md)
- [Background Task Overview](docs/core/background-task/overview.md)
- [LLM Provider Overview](docs/core/llm-provider/overview.md)
- [StyleQSS Styling System](docs/utils/style-qss.md)

---

## Plugin Development

### Plugin Structure

Each plugin can contain the following files:

```
my_plugin/
├── entrance.py      # Required: Plugin entry, defines IPlugin subclass
├── service.py       # Optional: Plugin service logic
├── information.py   # Optional: Plugin metadata (version, icon, API definitions, etc.)
└── assets/          # Optional: Static assets directory
```

### Simple Example

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

### MCP Function Calling Integration

Define `service_api` in `information.py`, and the framework will automatically convert it to LLM-callable tools:

```python
from core.plugin.plugin_info_interface import IPluginInfo

class MyPluginInfo(IPluginInfo):
    @property
    def service_api(self) -> dict:
        return {
            "my_method": {
                "description": "Method description",
                "parameters": {
                    "param1": {
                        "type": "string",
                        "description": "Parameter description",
                        "required": True
                    }
                },
                "returns": {
                    "type": "string",
                    "description": "Return value description"
                }
            }
        }
```

### Development Documentation

- [Plugin Development Guide](docs/core/plugin-system/plugin-development.md)
- [IPlugin Interface Details](docs/core/plugin-system/iplugin.md)
- [PluginManager API](docs/core/plugin-system/plugin-manager.md)

---

## Configuration Files

| Config File | Path | Purpose |
|-------------|------|---------|
| Plugin Order | `config/plugin_order.json` | Plugin display order configuration |
| LLM Config | `config/llm_providers.json` | Provider API Key, Base URL, etc. |
| Model Cache | `config/llm_models_cache.json` | LLM model list cache |
| Plugin Data | `data/data.json` | Plugin data persistent storage |
| Task Status | `data/tasks.json` | Background task state persistence |
| Assets | `data/assets/` | Plugin asset file storage |
| MCP Config | `config/mcp_config.json` | MCP Server/Client connection configuration |
| Usage Records | `data/llm_usage.json` | LLM API usage records |

---

## License

InstructionX is licensed under a **Modified Apache License 2.0**:

- ✅ **Personal Use**: Free to use
- ✅ **Educational Use**: Requires written authorization
- ❌ **Enterprise Use**: Prohibited without authorization
- ❌ **Commercial Use**: Requires written authorization

See [LICENSE](LICENSE) file for complete terms.

---

## Contribution & Support

### Issue Reporting

If you encounter problems or have feature suggestions, please feel free to submit an Issue.

### Documentation

The project includes complete technical documentation (in Chinese) located in the `docs/` directory, covering:
- Architecture design
- Core module details
- API reference
- Plugin development guide

---

## Tech Stack

| Technology | Purpose | Version |
|------------|---------|---------|
| InstructionX CE | Application version | 0.1.0 |
| PySide6 | Qt GUI framework | >= 6.10 |
| Python | Programming language | >= 3.14 |
| requests | HTTP requests | - |
| aiohttp | Asynchronous HTTP | - |
| opencv-python | Image processing | - |
| numpy | Numerical computation | - |
| StyleQSS | UI theme | Built-in |

---

## Notes

- Currently only supports **Windows** platform
- **Python 3.14+** recommended
- `data/` and `config/` directories will be automatically created on first run

---

*Use InstructionX to build your personalized intelligent Tools Cluster!*