# 插件文档

> InstructionX 项目的所有插件文档索引

---

## 文档结构

```
plugins/
├── index.md                    # 本文档 - 插件索引
├── official-plugins.md         # 官方插件说明（当前无预装插件）
├── thirdparty-plugins.md       # 第三方插件说明（已废弃）
└── llm-integration-guide.md    # LLM 集成开发指南
```

---

## 插件获取方式

InstructionX 不再捆绑预装插件，而是通过 **GitHub 插件安装器** 按需获取插件。

### 通过 GitHub 安装插件

使用 **GitHub Plugin Installer** 从社区仓库安装插件：

- **官方插件仓库**: [KKPIP-Tech/InstructionX-Plugins](https://github.com/KKPIP-Tech/InstructionX-Plugins)（安装到 `plugin/` 目录）
- **第三方插件**: 任何包含 `IXPlugin.json` 或 `IXRepo.json` 的 GitHub 仓库（安装到 `custom_plugin/` 目录）

详细说明见 [GitHub 插件安装器](../core/plugin-system/plugin-installer.md)。

---

## 文档索引

```
plugins/
├── index.md                    # 本文档 - 插件索引
├── official-plugins.md         # 官方插件说明（当前无预装插件）
├── thirdparty-plugins.md       # 第三方插件说明（已废弃）
└── llm-integration-guide.md    # LLM 集成开发指南
```

### 文档说明

| 文档 | 说明 |
|------|------|
| [官方插件](official-plugins.md) | 当前无预装插件，所有插件通过 GitHub 安装 |
| [第三方插件](thirdparty-plugins.md) | 已废弃，第三方插件通过 GitHub 安装 |
| [LLM 集成开发指南](llm-integration-guide.md) | 学习如何在插件中使用 LLM 服务 |
| [GitHub 插件安装器](../core/plugin-system/plugin-installer.md) | 从 GitHub 安装插件的完整说明 |
| [插件开发指南](../core/plugin-system/plugin-development.md) | 学习如何开发自己的插件 |

---

*本文档由 Claude Code 自动生成*
