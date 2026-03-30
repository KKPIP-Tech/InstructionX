# 插件文档

> InstructionX 项目的所有插件文档索引

---

## 文档结构

```
plugins/
├── index.md                # 本文档 - 插件索引
├── official-plugins.md     # 官方插件文档（10个）
└── thirdparty-plugins.md   # 第三方插件文档（4个）
```

---

## 插件总览

InstructionX 内置了 **14 个插件**，分为官方插件和第三方插件两类。

### 官方插件（10个）

位于项目根目录下的 `plugin/` 目录：

| 插件 | 类型 ID | 功能描述 |
|------|---------|---------|
| [LLM Chat](official-plugins.md#llm-chat) | `llm-chat` | 多提供商 LLM 对话，支持流式输出 |
| [文本格式化](official-plugins.md#文本格式化) | `text-formatting` | 文本大小写转换 |
| [代码格式化](official-plugins.md#代码格式化) | `code-formatter` | JSON/XML 格式化、注释移除 |
| [字符串工具](official-plugins.md#字符串工具) | `string-tools` | 文本反转、单词统计等 |
| [任务管理器](official-plugins.md#任务管理器) | `task-manager` | 任务 CRUD、优先级管理 |
| [任务报告器](official-plugins.md#任务报告器) | `task-reporter` | 订阅任务变化、生成报告 |
| [图片压缩](official-plugins.md#图片压缩) | `image-compressor` | 图片压缩与信息查看 |
| [后台任务演示](official-plugins.md#后台任务演示) | `background-task-demo` | 四种后台任务演示 |
| [本地服务器](official-plugins.md#本地服务器) | `local-server` | 本地 HTTP 服务器 |
| [UI 演示](official-plugins.md#ui-演示) | `ui-demo` | FluentUI3 风格控件展示 |

### 第三方插件（4个）

位于项目根目录下的 `custom_plugin/` 目录：

| 插件 | 类型 ID | 功能描述 |
|------|---------|---------|
| [API 调用演示](thirdparty-plugins.md#api-调用演示) | `api-demo` | 跨插件 API 调用演示 |
| [框架 API 综合演示](thirdparty-plugins.md#框架-api-综合演示) | `framework-api-demo` | 所有框架 API 综合演示 |
| [颜色转换](thirdparty-plugins.md#颜色转换) | `color-converter` | HEX 到 RGB 颜色转换 |
| [单位转换](thirdparty-plugins.md#单位转换) | `unit-converter` | 长度/重量/温度单位转换 |

---

## 学习路径

1. **[官方插件文档](official-plugins.md)** - 了解所有内置插件的功能和使用方式
2. **[第三方插件文档](thirdparty-plugins.md)** - 了解示例插件的实现方式
3. **[插件开发指南](../core/plugin-system/plugin-development.md)** - 学习如何开发自己的插件

---

*本文档由 Claude Code 自动生成*
