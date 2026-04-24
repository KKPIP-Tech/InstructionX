# 官方插件

> InstructionX 当前无预装插件，官方插件通过 GitHub 按需安装到 `plugin/` 目录

---

## 当前状态

InstructionX 不再捆绑预装插件。所有插件通过 **GitHub 插件安装器** 按需安装。

**官方插件仓库**: [KKPIP-Tech/InstructionX-Plugins](https://github.com/KKPIP-Tech/InstructionX-Plugins)

来自 `KKPIP-Tech` 组织的插件仓库通过 GitHub 插件安装器安装时，会被安装到 `plugin/` 目录，被视为"官方插件"。关于安装目录规则详见 [GitHub 插件安装器](../core/plugin-system/plugin-installer.md)。

---

## 获取插件

通过菜单 **编辑 → 从 GitHub 安装插件...** 打开安装对话框，输入官方插件仓库 URL 即可安装。

例如：
- `https://github.com/KKPIP-Tech/InstructionX-Plugins`

详细说明见 [GitHub 插件安装器](../core/plugin-system/plugin-installer.md)。

---

## 插件目录

| 目录 | 说明 | 加载时机 |
|------|------|----------|
| `plugin/` | 官方插件目录 | 应用启动时优先加载 |

---

## 相关文档

- [插件索引](index.md)
- [第三方插件](thirdparty-plugins.md)
- [插件系统概述](../core/plugin-system/overview.md)
- [GitHub 插件安装器](../core/plugin-system/plugin-installer.md)
- [插件开发指南](../core/plugin-system/plugin-development.md)
- [IPlugin 接口](../core/plugin-system/iplugin.md)
- [PluginManager](../core/plugin-system/plugin-manager.md)

---

*本文档由 Claude Code 自动生成*
