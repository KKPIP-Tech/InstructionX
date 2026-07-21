# ui/dialog/llm_settings/constants.py
"""LLM 设置界面命名常量模块

集中管理 ui/dialog/llm_settings/ 包内全部尺寸、超时等字面量，按用途分组。
颜色一律走 ``theme.py`` 的主题 token，本模块不存放颜色字面量。
"""

from typing import Dict, Tuple


# ==================== 主对话框尺寸（dialog 主壳使用） ====================

# 主对话框最小尺寸
DIALOG_MIN_WIDTH = 900
DIALOG_MIN_HEIGHT = 600
# 主对话框默认尺寸
DIALOG_DEFAULT_WIDTH = 1050
DIALOG_DEFAULT_HEIGHT = 700

# QSettings 组织名 / 应用名 / 上次选中实例记忆键
QSETTINGS_ORG_NAME = "LumenThread"
QSETTINGS_APP_NAME = "InstructionX-CE"
QSETTINGS_LAST_PROVIDER_KEY = "llm_settings/last_provider"

# ==================== 左侧列表面板 ====================

# 左侧栏固定宽度
SIDEBAR_WIDTH = 248
# 左侧栏布局边距（左/上/右/下）与控件间距
SIDEBAR_MARGIN_H = 12
SIDEBAR_MARGIN_TOP = 14
SIDEBAR_MARGIN_BOTTOM = 12
SIDEBAR_SPACING = 8
# 搜索框高度
SEARCH_EDIT_HEIGHT = 34
# 列表区顶部留白与底部添加按钮行上边距
SIDEBAR_LIST_TOP_GAP = 4
ADD_PROVIDER_ROW_TOP_MARGIN = 4
# 列表行间距（px）与列表项固定高度
LIST_ROW_SPACING = 2
LIST_ITEM_HEIGHT = 36
# 列表项 sizeHint 宽度（仅需一个稳定值，实际随栏宽拉伸）
LIST_ITEM_HINT_WIDTH = 200
# 列表项内边距（水平）与元素间距
LIST_ITEM_MARGIN_H = 10
LIST_ITEM_SPACING = 10
# 列表项品牌图标边长与名称省略宽度
LIST_ITEM_ICON_PX = 20
LIST_ITEM_NAME_ELIDE_WIDTH = 130
# 「＋ 添加提供商」按钮高度
ADD_PROVIDER_BUTTON_HEIGHT = 32

# ==================== 开关控件 ====================

# 标准开关尺寸
SWITCH_WIDTH = 38
SWITCH_HEIGHT = 22
# 模型行小开关尺寸
MODEL_SWITCH_WIDTH = 34
MODEL_SWITCH_HEIGHT = 20
# 开关滑块动画时长（毫秒）
SWITCH_ANIM_DURATION_MS = 140

# ==================== 徽章与分隔线 ====================

# 类型徽章固定高度
BADGE_HEIGHT = 20
# 分隔线厚度（1px hairline）
HAIRLINE_HEIGHT = 1

# ==================== 详情面板 ====================

# 头部品牌图标边长与名称字号
HEADER_ICON_PX = 22
HEADER_NAME_FONT_PX = 17
# 头部布局边距（左/上/右/下）与间距；右侧边距较小（给更多菜单按钮留紧凑空间）
HEADER_MARGIN_H = 24
HEADER_MARGIN_RIGHT = 20
HEADER_MARGIN_TOP = 16
HEADER_MARGIN_BOTTOM = 14
HEADER_SPACING = 12
# 更多菜单按钮尺寸
MORE_BUTTON_SIZE = 28
# 输入框统一高度
INPUT_HEIGHT = 34
# 密钥明文切换按钮尺寸与眼睛图标边长
EYE_BUTTON_SIZE = 32
EYE_ICON_SIZE = 18
# 「检测」按钮尺寸
CHECK_BUTTON_WIDTH = 76
CHECK_BUTTON_HEIGHT = 32
# 「重置」按钮尺寸
RESET_BUTTON_WIDTH = 64
RESET_BUTTON_HEIGHT = 32
# 详情内容区边距（左/上/右/下）与分区间距
CONTENT_MARGIN_H = 24
CONTENT_MARGIN_TOP = 20
CONTENT_MARGIN_BOTTOM = 24
SECTION_GAP = 24
FIELD_GAP = 8
# 分区标题与内容的间距
SECTION_CONTENT_GAP = 16
# 检测状态文案上方间距与字段块间距
CHECK_STATUS_TOP_GAP = 6
FIELD_BLOCK_GAP = 12
# 默认模型区行间距
DEFAULT_MODEL_ROW_GAP = 10
# 模型分组标题 / 空态提示内边距
GROUP_CAPTION_MARGIN_LEFT = 4
GROUP_CAPTION_MARGIN_TOP = 12
GROUP_CAPTION_MARGIN_BOTTOM = 4
EMPTY_HINT_MARGIN_BOTTOM = 12
# 管理工具条内边距与间距
MANAGE_BAR_MARGIN_H = 10
MANAGE_BAR_MARGIN_V = 4
MANAGE_BAR_SPACING = 10
# 模型行固定高度与行内边距/间距
MODEL_ROW_HEIGHT = 44
MODEL_ROW_MARGIN_LEFT = 10
MODEL_ROW_MARGIN_RIGHT = 6
MODEL_ROW_SPACING = 10
# 模型行删除按钮尺寸
ROW_DELETE_BUTTON_SIZE = 26
# 模型区标题栏按钮高度（↻ 刷新 / ＋ 添加 / 管理）
MODELS_HEADER_BUTTON_HEIGHT = 30
# 模型区标题栏「↻ 刷新」小按钮宽度
MODELS_REFRESH_BUTTON_WIDTH = 36
# 管理工具条「删除选中」按钮高度
MANAGE_DELETE_BUTTON_HEIGHT = 28
# 默认模型区字段标签固定宽度
DEFAULT_MODEL_LABEL_WIDTH = 110

# ==================== 表单对话框（_BaseFormDialog） ====================

# 表单对话框最小宽度与布局边距/间距
FORM_DIALOG_MIN_WIDTH = 400
FORM_DIALOG_MARGIN = 20
FORM_DIALOG_SPACING = 10
# 表单输入框 / 按钮高度
FORM_INPUT_HEIGHT = 34
FORM_BUTTON_HEIGHT = 32
# 表单字段间留白与按钮行上方留白
FORM_FIELD_GAP = 4
FORM_BUTTONS_TOP_GAP = 8

# ==================== 模型类型分组 ====================

# 模型主类型键（由 capabilities 推导，见 widgets._model_primary_type）
MODEL_TYPE_CHAT = "chat"
MODEL_TYPE_VISION = "vision"
MODEL_TYPE_EMBEDDING = "embedding"
MODEL_TYPE_RERANK = "rerank"

# 模型类型分组（分组顺序即展示顺序）
MODEL_TYPE_GROUPS: Tuple[Tuple[str, str], ...] = (
    (MODEL_TYPE_CHAT, "对话"),
    (MODEL_TYPE_VISION, "视觉"),
    (MODEL_TYPE_EMBEDDING, "嵌入"),
    (MODEL_TYPE_RERANK, "重排序"),
)
# 类型键 -> 中文标签
MODEL_TYPE_LABELS: Dict[str, str] = dict(MODEL_TYPE_GROUPS)

# 自定义实例（无关联预设）的类型徽章文案
CUSTOM_PROVIDER_TYPE_LABEL = "自定义"

# ==================== 时间与超时 ====================

# 单模型健康检查探测超时（秒，workers.py 使用）
MODEL_CHECK_TIMEOUT_S = 15.0
# 面板卸载/切换实例时回收 Worker 的最长等待时间（毫秒）
WORKER_STOP_WAIT_MS = 3000

# ==================== Provider 编辑器 / 模型编辑对话框 ====================

# Provider 添加/编辑实例对话框最小宽度
EDITOR_DIALOG_WIDTH = 480
# MODE_CREATE 两页流程的默认高度（完整显示全部类型项）
EDITOR_DIALOG_CREATE_HEIGHT = 460
# 编辑器「选择类型」页预设列表项高度与图标尺寸
PRESET_ITEM_HEIGHT = 56
PRESET_ICON_SIZE = 32
# 新建实例 id 的随机短码长度（uuid4 hex 前缀）
INSTANCE_ID_SUFFIX_LENGTH = 8
# 自定义实例 id 前缀
CUSTOM_INSTANCE_ID_PREFIX = "custom"

# 模型编辑对话框最小宽度
MODEL_EDIT_DIALOG_WIDTH = 500
# 定价币种选项（与 model_schema.DEFAULT_CURRENCY 闭集一致）
CURRENCY_OPTIONS: Tuple[str, ...] = ("$", "¥", "€")
# 上下文长度输入上限（tokens）
CONTEXT_LENGTH_MAX = 10_000_000
# 定价输入上限（每百万 tokens）与小数位数
PRICE_SPIN_MAX = 100000.0
PRICE_SPIN_DECIMALS = 4
# 上下文长度换算为 K 的除数（如 131072 → 128K）
TOKENS_PER_K = 1024

# ==================== 健康检查 / 模型同步对话框 ====================

# 健康检查对话框默认尺寸
HEALTH_DIALOG_WIDTH = 560
HEALTH_DIALOG_HEIGHT = 520
# 模型同步对话框默认尺寸
SYNC_DIALOG_WIDTH = 640
SYNC_DIALOG_HEIGHT = 560
# 两对话框布局边距与控件间距
SUB_DIALOG_MARGIN = 20
SUB_DIALOG_SPACING = 10
# 状态/错误简述省略宽度（px，超出部分以省略号截断，完整文案走 tooltip）
STATUS_TEXT_ELIDE_WIDTH = 260
