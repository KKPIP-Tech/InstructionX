# 文档更新日志

> InstructionX 技术文档更新记录

---

## 2026-03-31 - LLM 设置对话框全面重构

### LLM 设置对话框 (LLMSettingsDialog)
- **布局重构**: 从旧版单栏表单改为两栏布局，左栏 Provider 列表（250px），右栏配置详情（滚动区域）
- **新增组件**: `ProviderLogoLabel`（程序化 Provider 徽标）、`CapabilityBadge`（Vision/Thinking/Tools 徽章）、`CategoryBadge`（Chat/Embedding 徽章）、`ModelFetchedListItem`（模型行，含勾选状态）、增强 `ProviderListItem`（新增 tooltip 参数）
- **模型列表**: 支持预设分组（minimax/glm 使用 CollapsibleGroup 按类别折叠）和 API 动态获取（ollama/siliconflow）
- **新增 "AI" 菜单**: 原 "LLM" 菜单改名为 "AI"，整合模型服务、切换 Provider、用量统计、LLM 设置四项功能
- **Provider 切换菜单**: 自动标记 Vision/Function Calling 能力和健康状态
- **用量统计**: 对话框底部栏实时显示累计费用、Token 用量、请求次数
- **新增 LLM 模型服务对话框** (`LLMModelServiceDialog`): 通过 **AI > 模型服务...** 打开，设置默认 Provider 和模型

### 文档更新
- **docs/ui/main-window.md**: 更新菜单栏说明（编辑、用户中心、AI、帮助），补充 AI 菜单详细结构
- **docs/ui/dialogs.md**: 重写 LLMSettingsDialog 章节，反映两栏布局、新增组件和模型列表功能
- **docs/core/llm-provider/overview.md**: 更新 UI 配置说明（AI > LLM 设置...）

---

## 2026-03-30 - 文档全面升级

### 新增文档

#### 1. 接口层概述
- **文件**: `docs/core/interfaces/overview.md`
- **内容**: 
  - 接口层设计理念和目标
  - 所有接口的详细说明（IPlugin、IPluginInfo、IDataProvider、ITaskManager、ILLMFacade、ILogger）
  - PluginServices 服务封装类
  - 接口导入指南
  - 接口与实现的关系映射
  - 最佳实践（使用接口、依赖注入、错误处理）

### 更新文档

#### 2. 主窗口文档 (docs/ui/main-window.md)
- **更新内容**:
  - **主题切换功能**:
    - 补充了主题持久化机制的详细说明（保存到 DataProvider 的 `__app_config__` 插件）
    - 更新了主题应用的代码示例
    - 补充了菜单显示格式说明
  - **窗口边缘缩放**:
    - 完善了 8 个方向缩放的详细说明
    - 补充了缩放流程图
    - 添加了光标映射表
    - 补充了实现方法列表
    - 添加了最大化限制的说明

#### 3. LLM Provider API 参考 (docs/core/llm-provider/api-reference.md)
- **更新内容**:
  - **chat() 方法**:
    - 补充了 `tools` 参数的详细说明（Function Calling）
    - 补充了 `images` 参数的详细说明（Vision 支持）
    - 添加了 Function Calling 的完整两轮对话示例
    - 添加了 Vision 功能的使用示例和注意事项
    - 明确说明了 MiniMax 不支持 Vision 功能
    - 补充了 ChatResponse 的所有属性说明

#### 4. 文档索引 (docs/README.md)
- **更新内容**:
  - 重新组织了文档结构，将接口层移到核心模块文档的最前面
  - 补充了接口层的所有文件说明
  - 添加了接口层的文档链接

#### 5. 系统架构概述 (docs/architecture/overview.md)
- **更新内容**:
  - **抽象接口层部分**:
    - 补充了接口层的设计目标说明
    - 添加了完整的接口清单表格（包含文件、说明、实现类）
    - 添加了接口导入指南代码示例
    - 添加了接口层概述文档的交叉引用链接

#### 6. IPlugin 接口 (docs/core/plugin-system/iplugin.md)
- **更新内容**:
  - **Widget 缓存机制**:
    - 补充了缓存机制的实现细节代码
    - 扩展了缓存优势的说明（新增"内存可控"）
    - 添加了缓存失效策略的讨论
    - 添加了自定义缓存行为的完整示例
    - 补充了注意事项的详细说明

### 文档质量提升

#### 统一改进
1. **代码示例**: 为新增功能添加了完整可运行的代码示例
2. **流程图**: 使用 mermaid 图表展示复杂流程（主题切换、边缘缩放、缓存机制）
3. **表格**: 用表格清晰展示接口映射、光标映射等信息
4. **交叉引用**: 确保文档之间有充分的交叉链接
5. **注意事项**: 明确标注重要注意事项和陷阱（如 MiniMax 不支持 Vision）

#### 格式优化
1. 统一使用三重反引号代码块
2. 规范使用粗体、斜体等 Markdown 格式
3. 保持章节结构的清晰和一致
4. 确保所有标题都有对应的说明内容

### 文档覆盖范围

#### 新增功能说明
- ✅ 接口层设计理念和实现
- ✅ 主题切换的完整机制（包括持久化）
- ✅ 窗口边缘缩放的 8 个方向实现
- ✅ LLM Function Calling 的完整流程
- ✅ LLM Vision 功能的使用方法
- ✅ Widget 缓存机制的详细实现

#### 文档完整性检查
- ✅ 所有核心组件都有详细文档
- ✅ 所有 API 都有参数说明和示例
- ✅ 所有新功能都有使用指南
- ✅ 文档之间有充分的交叉引用
- ✅ 提供了清晰的导入和使用指南

### 待补充的文档

以下文档需要在后续版本中补充：

1. **Core Interfaces 详细文档**
   - `docs/core/interfaces/i_plugin.md` - IPlugin 接口详细文档（目前合并在 overview.md 中）
   - `docs/core/interfaces/i_plugin_info.md` - IPluginInfo 接口详细文档
   - `docs/core/interfaces/i_data_provider.md` - IDataProvider 接口详细文档
   - `docs/core/interfaces/i_task_manager.md` - ITaskManager 接口详细文档
   - `docs/core/interfaces/i_llm_facade.md` - ILLMFacade 接口详细文档
   - `docs/core/interfaces/i_logger.md` - ILogger 接口详细文档（已有基础版，可扩展）
   - `docs/core/interfaces/plugin_services.md` - PluginServices 类详细文档

   > 注：上述接口说明目前综合在 `docs/core/interfaces/overview.md` 中，如需独立文档请使用 .md 后缀。

2. **插件系统扩展文档**
   - `docs/core/plugin-system/plugin-manager.md` - PluginManager 详细文档（已有部分内容，可扩展）
   - `docs/core/plugin-system/plugin-identity.md` - PluginIdentity 详细文档

### 使用建议

#### 文档阅读顺序
1. **初学者**: 从 `docs/README.md` 开始，按入门路径阅读
2. **插件开发者**: 重点阅读接口层概述和插件系统文档
3. **框架开发者**: 阅读所有核心模块文档，了解实现细节

#### 文档更新原则
1. **同步更新**: 代码变更时同步更新文档
2. **示例验证**: 所有代码示例都应该可以运行
3. **交叉引用**: 新文档时添加相关文档的链接
4. **版本标记**: 重大变更时在文档中标记版本号

---

## 变更总结

### 新增文档: 1 个
- ✅ `docs/core/interfaces/overview.md` - 接口层概述

### 更新文档: 5 个
- ✅ `docs/ui/main-window.md` - 主窗口
- ✅ `docs/core/llm-provider/api-reference.md` - LLM Provider API 参考
- ✅ `docs/README.md` - 文档索引
- ✅ `docs/architecture/overview.md` - 系统架构概述
- ✅ `docs/core/plugin-system/iplugin.md` - IPlugin 接口

### 文档质量提升
- ✅ 补充了 6 个新增功能的详细说明
- ✅ 添加了 10+ 个代码示例
- ✅ 添加了 5 个流程图
- ✅ 完善了 3 个功能的使用指南
- ✅ 补充了多个交叉引用链接

---

*本文档记录了 InstructionX 技术文档的所有更新历史*