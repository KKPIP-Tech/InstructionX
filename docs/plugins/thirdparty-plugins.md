# 第三方插件

> InstructionX 附带的 4 个示例/第三方插件详细文档

---

## 1. API 调用演示 {#api-调用演示}

**文件位置**: `custom_plugin/api_demo/`

**类型 ID**: `api-demo`

**版本**: `release.1.0.0`

**开发者**: KKPIP-Tech

### 功能描述

演示如何通过 PluginManager 进行跨插件 API 调用。

### service_api

此插件本身不提供服务 API（`service_api = {}`），它演示如何调用其他插件的 API。

### 核心功能

- 获取所有已注册的 API 列表
- 查看指定插件的 API 详情
- 生成所有 Function Tools（OpenAI/MCP 格式）
- 执行跨插件方法调用

### 界面布局

水平分割面板：左侧为 API 列表 + 刷新/查看所有/查看工具按钮，右侧为输入区 + 执行按钮 + 输出文本区。

### 演示流程

1. 刷新 API 列表 → 获取 "字符串工具" 插件的 ID
2. 查看所有插件 API → 查看系统所有可用接口
3. 查看 Function Tools → 查看 MCP/OpenAI 格式的工具定义
4. 执行调用 → 调用 `string_tools` 的 `to_uppercase` 方法

---

## 2. 框架 API 综合演示 {#框架-api-综合演示}

**文件位置**: `custom_plugin/framework_api_demo/`

**类型 ID**: `framework-api-demo`

**版本**: `release.1.0.0`

**开发者**: InstructionX

### 功能描述

最全面的框架 API 演示插件，包含 5 个功能标签页，涵盖 DataProvider、Task、LLM、API 和 Info 所有方面。

### service_api

| 方法 | 功能 |
|------|------|
| `demo_data_operation` | 数据操作演示 |
| `demo_task_operation` | 任务操作演示 |
| `get_framework_info` | 获取框架信息 |

### 界面布局

5 个功能标签页：

| 标签页 | 演示内容 |
|--------|---------|
| DataProvider | 插件注册/注销、PRIVATE/PUBLIC 数据读写、资产保存/加载 |
| Task | 同步/异步/定时任务创建、任务查询、清理 |
| LLM | Provider 列表、模型列表、聊天、嵌入 |
| API | 所有插件查询、所有 API 查询、Function Tools、跨插件调用 |
| Info | 框架信息、API 文档 |

### 使用方式

这是一个学习工具，推荐开发者逐一尝试每个功能，理解框架 API 的使用方式。

---

## 3. 颜色转换 {#颜色转换}

**文件位置**: `custom_plugin/color_converter/`

**类型 ID**: `color-converter`

**版本**: `release.1.0.0`

**开发者**: KKPIP-Tech

### 功能描述

提供 HEX 颜色值到 RGB 格式的转换功能。

### service_api

| 方法 | 功能 |
|------|------|
| `hex_to_rgb` | 将 HEX 颜色转换为 RGB 字符串 |

### 界面布局

居中布局：HEX 输入框、转换按钮、RGB 输出框（只读）。

### 使用示例

```
输入: #FF5733
输出: rgb(255, 87, 51)
```

---

## 4. 单位转换 {#单位转换}

**文件位置**: `custom_plugin/unit_converter/`

**类型 ID**: `unit-converter`

**版本**: `release.1.0.0`

**开发者**: KKPIP-Tech

### 功能描述

提供长度、重量、温度三个类别的单位转换。

### service_api

| 方法 | 功能 |
|------|------|
| `length_converter` | 长度单位转换 |
| `weight_converter` | 重量单位转换（方法存在，但 UI 中未提供入口） |
| `temperature_converter` | 温度单位转换 |

### 支持的单位

**长度**: 米(m)、千米(km)、厘米(cm)、毫米(mm)、英寸(inch)、英尺(ft)

**重量**: 千克(kg)、克(g)、毫克(mg)、磅(lb)、盎司(oz)（有 service 方法但 UI 未暴露）

**温度**: 摄氏度(°C)、华氏度(°F)、开尔文(K)

### 界面布局

两个 GroupBox 分别处理长度和温度转换（`weight_converter` 方法存在但 UI 未提供入口）：
- 长度：输入值 + 源单位 + 目标单位 + 结果标签
- 温度：输入值 + 源单位 + 目标单位 + 结果标签

---

## 相关文档

- [官方插件](official-plugins.md)
- [插件开发指南](../core/plugin-system/plugin-development.md)
- [插件系统概述](../core/plugin-system/overview.md)

---

*本文档由 Claude Code 自动生成*
