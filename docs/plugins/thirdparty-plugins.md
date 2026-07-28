# 第三方插件

> 第三方插件通过 GitHub 安装到 `custom_plugin/` 目录

---

## 当前状态

InstructionX 支持第三方插件。第三方插件通过 **GitHub 插件安装器** 安装，安装到 `custom_plugin/` 目录。

任何包含 `IXPlugin.json` 或 `IXRepo.json` 的 GitHub 仓库（非 `KKPIP-Tech` 组织）都可以作为第三方插件安装源。

---

## 获取第三方插件

通过菜单 **编辑 → 从 GitHub 安装插件...** 打开安装对话框，输入第三方插件仓库 URL 即可安装。

### 安装目录规则

| GitHub 组织/用户 | 目标目录 |
|----------------|---------|
| `KKPIP-Tech` | `plugin/` |
| 其他所有 | `custom_plugin/`（第三方插件） |

### 仓库要求

第三方插件仓库需要包含有效的插件描述文件：

- `IXPlugin.json` — 单插件仓库描述文件
- `IXRepo.json` — 多插件仓库索引文件

描述文件格式详见 [GitHub 插件安装器](../core/plugin-system/plugin-installer.md)。

---

## 插件目录

| 目录 | 说明 | 加载时机 |
|------|------|----------|
| `custom_plugin/` | 第三方插件目录 | 应用启动时，官方插件加载完毕后加载 |

---

## 相关文档

- [插件索引](index.md)
- [插件系统概述](../core/plugin-system/overview.md)
- [GitHub 插件安装器](../core/plugin-system/plugin-installer.md)
- [插件开发指南](../core/plugin-system/plugin-development.md)
- [IPlugin 接口](../core/plugin-system/iplugin.md)
- [PluginManager](../core/plugin-system/plugin-manager.md)
