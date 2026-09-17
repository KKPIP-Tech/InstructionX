#!/bin/bash
# InstructionX 安装向导（macOS 原生版，bash 3.2+）。
#
# 面向大夫 / 教师 / 艺术家等非技术用户：双击 setup.command 即可安装、升级与维护运行环境。
#
# 为什么用原生脚本：向导必须在「电脑上连 Python 都没有」的机器上运行，因此本脚本不依赖
# Python，界面由 bash + ANSI 自己绘制；Windows 版是同样界面的 setup.ps1（两份脚本读取
# 同一份文案 setup_text/*.txt，保证两平台界面逐字一致）。Python 只在「安装」动作中被 uv
# 安装，用于运行应用本身。
#
# 首次安装成功后自动创建桌面启动器（~/Desktop/InstructionX.app，双击直接启动、不开
# Terminal），卸载时删除；向导内的「启动应用」保留运行输出，仅作调试用途。
#
# 用法：
#   ./setup.sh                  打开向导（自动准备 uv / Python / 界面依赖）
#   ./setup.sh --check          只做体检并打印文本报告（不启动界面）
#   ./setup.sh --state          打印环境状态（key=value，供排错与自动化）
#   ./setup.sh --preview menu   渲染一次指定界面后退出（两平台一致性比对用）
#   ./setup.sh --dry-run        试运行：只展示将要执行的命令
#   ./setup.sh --yes            自动确认所有提问
#   ./setup.sh --lang en        英文界面
#   ./setup.sh --no-color       关闭彩色输出
#
# 兼容性：macOS 自带 bash 3.2（无关联数组、无 ${var,,}、read -t 只接受整数），
# 本脚本刻意只使用 bash 3.2 可用语法。

set -u

# ============================================================================
# 1. 常量（与 setup.ps1 保持同名同值：单一事实来源）
# ============================================================================

#: 界面宽度（规则线长度，两个平台一致）
RULE_WIDTH=78
#: 项目根目录（脚本所在目录）
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PROJECT_ROOT="$SCRIPT_DIR"
#: 共享文案目录
TEXT_DIR="$PROJECT_ROOT/setup_text"
#: 向导日志（面向用户的可反馈文件，与文档约定一致）
LOG_FILE="$PROJECT_ROOT/logs/tui_setup.log"
#: 界面语言偏好（两平台共用的运行时文件）
LANG_FILE="$PROJECT_ROOT/.tui/lang"
#: 升级临时工作目录
WORK_DIR="$PROJECT_ROOT/.tui/work"
#: 应用虚拟环境目录
APP_VENV="$PROJECT_ROOT/.venv"
#: 框架要求的 Python 版本
REQUIRED_PYTHON="3.14"
#: 初次安装：按 uv.lock 精确安装，不装项目自身与测试依赖
SYNC_ARGS="sync --no-dev --no-install-project"
#: 修复 / 升级依赖：增量安装，绝不使用 uv sync（会删除插件自装依赖）
PIP_ARGS="pip install -r requirements.txt"
#: 关键依赖（安装后自检）
REQUIRED_IMPORTS="PySide6 numpy requests orjson mcp packaging"
#: 升级覆盖时必须保留的目录（用户数据与本地环境）
PRESERVE_DIRS="config data logs plugin custom_plugin .venv .tui temp"
#: 升级覆盖时跳过的仓库元数据
SKIP_DIRS=".git __pycache__"
#: 彻底卸载时删除的目录（程序文件不在此列）
UNINSTALL_DIRS=".venv config data logs .tui"
#: 桌面启动器（.app 包：首次安装成功后创建、卸载时删除；双击直接启动、不开 Terminal）
DESKTOP_APP_NAME="InstructionX.app"
#: 官方资源
ZIP_URL="https://codeload.github.com/KKPIP-Tech/InstructionX/zip/refs/heads/main"
UV_INSTALL_CMD="curl -LsSf https://astral.sh/uv/install.sh | sh"
PYTHON_URL="https://www.python.org/downloads/"
#: 超时（秒）
TIMEOUT_PROBE=30
TIMEOUT_DOWNLOAD=600
#: 磁盘剩余空间下限（KB，低于此值提醒；2GB）
MIN_FREE_DISK_KB=2097152
#: 命令输出重绘节流（每 N 行刷新一次界面）
REDRAW_EVERY=5
#: 装饰字符（用 UTF-8 字节构造，脚本正文保持纯 ASCII，避免编码差异）
RULE_CHAR=$(printf '\xe2\x94\x80')
CURSOR_MARK=$(printf '\xe2\x96\xb8')
TITLE_SEP=$(printf '\xc2\xb7')
#: ANSI 颜色
ESC=$(printf '\033')

#: 运行时状态
UI_LANG="zh"
TEXT_FILE=""
LOG_LINES=""
COLOR_ENABLED=0

# ============================================================================
# 2. 文案（读取 setup_text/<语言>.txt，与 setup.ps1 共用同一份数据）
# ============================================================================

load_text() {
    # 读取某语言文案，装载为 T_<key> 变量（点号换成下划线）
    local lang="$1"
    TEXT_FILE="$TEXT_DIR/$lang.txt"
    if [ ! -f "$TEXT_FILE" ]; then
        printf 'Missing text file: %s\n' "$TEXT_FILE" >&2
        exit 2
    fi
    local line key value name
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}          # 兼容 CRLF 文案文件（Windows 侧编辑过也不影响）
        case "$line" in
            ''|\#*) continue ;;
        esac
        key=${line%%=*}
        value=${line#*=}
        value=${value//\\n/$'\n'}
        name="T_${key//./_}"
        printf -v "$name" '%s' "$value"
    done < "$TEXT_FILE"
}

t() {
    # 取词并替换 {name} 占位符：t key [name=value ...]
    local key="$1"
    shift
    local name="T_${key//./_}"
    local value=""
    eval "value=\${$name-}"
    if [ -z "$value" ]; then
        printf '%s' "$key"
        return
    fi
    local pair pkey pvalue
    for pair in "$@"; do
        pkey=${pair%%=*}
        pvalue=${pair#*=}
        value=${value//\{$pkey\}/$pvalue}
    done
    printf '%s' "$value"
}

detect_system_language() {
    # 推断界面语言：参数 > .tui/lang > 系统区域 > 英文
    if [ "$OPT_LANG" = "zh" ] || [ "$OPT_LANG" = "en" ]; then
        printf '%s' "$OPT_LANG"
        return
    fi
    if [ -f "$LANG_FILE" ]; then
        local saved
        saved=$(tr -d '[:space:]' < "$LANG_FILE" | tr '[:upper:]' '[:lower:]')
        case "$saved" in
            zh|en) printf '%s' "$saved"; return ;;
        esac
    fi
    local locale_value="${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}"
    case "$locale_value" in
        zh*|*Chinese*) printf 'zh'; return ;;
        en*) printf 'en'; return ;;
    esac
    local apple_locale
    apple_locale=$(defaults read -g AppleLocale 2>/dev/null || true)
    case "$apple_locale" in
        zh*) printf 'zh'; return ;;
    esac
    printf 'en'
}

# ============================================================================
# 3. 终端与绘制（两个平台的输出必须逐字一致）
# ============================================================================

init_console() {
    # 启用彩色输出（非终端或 --no-color 时自动降级，界面结构不变）
    COLOR_ENABLED=0
    if [ "$OPT_NO_COLOR" = "1" ]; then
        return
    fi
    if [ -t 1 ]; then
        COLOR_ENABLED=1
    fi
}

colorize() {
    # colorize <tone> <text>
    local tone="$1"
    local text="$2"
    if [ "$COLOR_ENABLED" != "1" ] || [ -z "$tone" ]; then
        printf '%s' "$text"
        return
    fi
    local code=""
    case "$tone" in
        ok) code='32' ;;
        warn) code='33' ;;
        fail) code='31' ;;
        info) code='36' ;;
        title) code='1;36' ;;
        dim) code='90' ;;
        accent) code='1;37' ;;
    esac
    if [ -z "$code" ]; then
        printf '%s' "$text"
        return
    fi
    printf '%s[%sm%s%s[0m' "$ESC" "$code" "$text" "$ESC"
}

out_line() {
    # 输出一行界面文本：out_line [tone] <text>
    local tone=""
    if [ "$#" -ge 2 ]; then
        tone="$1"
        shift
    fi
    printf '%s\n' "$(colorize "$tone" "$1")"
}

rule() {
    # 输出分隔线
    local line=""
    local index=0
    while [ "$index" -lt "$RULE_WIDTH" ]; do
        line="$line$RULE_CHAR"
        index=$((index + 1))
    done
    out_line dim "$line"
}

clear_screen() {
    if [ -t 1 ]; then
        clear
    fi
}

platform_label() {
    printf 'macOS %s' "$(sw_vers -productVersion 2>/dev/null || printf 'unknown')"
}

write_header() {
    rule
    out_line title " $(t app.title)  ${TITLE_SEP}  $(t app.subtitle)"
    out_line dim " $(platform_label) ${TITLE_SEP} $(t "lang.name.$UI_LANG")"
    rule
}

write_footer() {
    # write_footer [page]：输出底部按键提示；页面页脚带「Esc 返回」提示，主菜单不带
    rule
    if [ "${1:-}" = "page" ]; then
        out_line dim " $(t ui.footer_page)"
    else
        out_line dim " $(t ui.footer)"
    fi
    rule
}

token_to_char() {
    # 把 u+XXXX 的十六进制码位转成对应字符的 UTF-8 字节
    # （bash 3.2 的 printf 不支持 \uXXXX，因此手工编码，保证 macOS 自带 bash 也能跑）
    local code=$((16#$1))
    if [ "$code" -lt 128 ]; then
        printf '%b' "$(printf '\\x%02x' "$code")"
    elif [ "$code" -lt 2048 ]; then
        printf '%b' "$(printf '\\x%02x\\x%02x' $((192 + code / 64)) $((128 + code % 64)))"
    else
        printf '%b' "$(printf '\\x%02x\\x%02x\\x%02x' $((224 + code / 4096)) \
            $((128 + (code / 64) % 64)) $((128 + code % 64)))"
    fi
}

set_key_queue() {
    # 注入脚本化按键序列（--keys 使用），用于无终端环境复现与回归测试界面流程
    KEY_QUEUE="$1"
    KEY_QUEUE_COUNT=$(printf '%s' "$1" | awk -F',' '{print NF}')
    USE_KEY_QUEUE=1
}

read_key() {
    # 读取一个按键并归一化为动作名，结果写入全局变量 READ_KEY_RESULT。
    # 不能用 stdout 返回值：调用方若写成 $(read_key)，函数会在子 Shell 中执行，
    # KEY_QUEUE 的弹出操作无法回流父 Shell，队列永远排不空（实测任意 --keys 序列死循环）。
    if [ "${USE_KEY_QUEUE:-0}" = "1" ]; then
        pop_key_queue
    else
        read_console_key
    fi
    READ_KEY_RESULT=$(normalize_key "$RAW_KEY")
}

pop_key_queue() {
    # 从脚本化按键队列（--keys）弹出一个 token，结果写入 RAW_KEY；队列耗尽按「退出」处理。
    # 本函数直接修改 KEY_QUEUE / KEY_QUEUE_COUNT，必须以普通方式调用（不能放进 $() 中）
    RAW_KEY='quit'
    local token=""
    while [ "$KEY_QUEUE_COUNT" -gt 0 ]; do
        token=$(printf '%s' "$KEY_QUEUE" | cut -d',' -f1)
        KEY_QUEUE=$(printf '%s' "$KEY_QUEUE" | cut -d',' -f2-)
        KEY_QUEUE_COUNT=$((KEY_QUEUE_COUNT - 1))
        token=$(printf '%s' "$token" | tr -d '[:space:]')
        [ -z "$token" ] && continue
        RAW_KEY="$token"
        return
    done
}

read_console_key() {
    # 从控制台读取一个原始按键（含方向键转义序列与 UTF-8 多字节字符），结果写入 RAW_KEY；
    # 没有可读输入（非交互环境或输入结束）时按「退出」处理，避免死循环
    RAW_KEY='quit'
    local key=""
    IFS= read -rsn1 key || return
    if [ "$key" = "$ESC" ]; then
        local rest=""
        # bash 3.2 的 read -t 只接受整数秒；方向键会立即送来后续字节，裸 Esc 最多等 1 秒
        IFS= read -rsn2 -t 1 rest || rest=""
        case "$rest" in
            '[A') RAW_KEY='up' ;;
            '[B') RAW_KEY='down' ;;
            *) RAW_KEY='escape' ;;
        esac
        return
    fi
    # bash 3.2 的 read -n1 按字节读（bash 4+ 按字符读）：首字节 >= 0xC2 是 UTF-8 多字节
    # 字符的前导字节（如全角数字），需按其指示的总长度补齐后续字节才能正确匹配
    if [ "$(printf '%s' "$key" | wc -c | tr -d ' ')" -eq 1 ]; then
        local byte extra=1 more=""
        byte=$(printf '%s' "$key" | od -An -tu1 | awk '{print $1; exit}')
        if [ -n "$byte" ] && [ "$byte" -ge 194 ] 2>/dev/null; then
            [ "$byte" -ge 224 ] && extra=2
            [ "$byte" -ge 240 ] && extra=3
            IFS= read -rsn"$extra" -t 1 more || true
            key="$key$more"
        fi
    fi
    RAW_KEY="$key"
}

normalize_key() {
    # 把原始按键归一化为动作名：up / down / enter / escape / refresh / lang / zh / en /
    # quit / yes / no / 数字字符。队列 token 与真实按键走同一条归一化路径，
    # 保证 --keys 自动化与人工按键完全等价（与 setup.ps1 的 -Keys 行为一致）
    local key="$1"
    case "$key" in
        up|down|enter|escape|quit|yes|no) printf '%s' "$key"; return ;;
    esac
    # u+XXXX token：按码位构造字符（供测试注入全角数字等，避免命令行编码干扰）
    case "$key" in
        u+[0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F])
            key=$(token_to_char "${key#u+}")
            ;;
    esac
    # 中文输入法「全角」模式下数字键产生全角字符（U+FF11–U+FF19，UTF-8 为 EF BC 91–99），
    # 必须归一化为半角，否则表现为「按了没反应」。按字节十六进制比较，脚本正文保持纯 ASCII
    if [ "$(printf '%s' "$key" | wc -c | tr -d ' ')" -eq 3 ]; then
        case "$(printf '%s' "$key" | od -An -tx1 | tr -d ' \n')" in
            efbc91) key='1' ;; efbc92) key='2' ;; efbc93) key='3' ;;
            efbc94) key='4' ;; efbc95) key='5' ;; efbc96) key='6' ;;
            efbc97) key='7' ;; efbc98) key='8' ;; efbc99) key='9' ;;
        esac
    fi
    case "$key" in
        '') printf 'enter'; return ;;
        [1-9]) printf '%s' "$key"; return ;;
    esac
    case "$(printf '%s' "$key" | tr '[:upper:]' '[:lower:]')" in
        r) printf 'refresh' ;;
        l) printf 'lang' ;;
        z) printf 'zh' ;;
        e) printf 'en' ;;
        q) printf 'quit' ;;
        y) printf 'yes' ;;
        n) printf 'no' ;;
        b) printf 'escape' ;;
        *) printf '' ;;
    esac
}

wait_any_key() {
    # 非交互动作模式（--action）不等待按键，避免在终端里挂起向导（对齐 setup.ps1 的 NonInteractive）
    if [ "${ACTION_MODE:-0}" = "1" ]; then
        return
    fi
    printf '\n'
    out_line dim " $(t ui.press_any)"
    IFS= read -rsn1 _ || true
}

# ============================================================================
# 4. 日志与结果
# ============================================================================

add_log() {
    # add_log <level> <message>：写入内存缓冲（供「正在执行」页展示）与 logs/tui_setup.log
    local level="$1"
    local message="$2"
    local prefix='* '
    case "$level" in
        warn) prefix='! ' ;;
        error) prefix='x ' ;;
        cmd) prefix='$ ' ;;
        output) prefix='  ' ;;
    esac
    local line
    while IFS= read -r line || [ -n "$line" ]; do
        if [ -z "$line" ] && [ "$level" = "output" ]; then
            continue
        fi
        LOG_LINES="$LOG_LINES$prefix$line
"
        write_wizard_log "$prefix$line"
        # 非交互动作模式（--action）没有界面，必须把过程打到标准输出，脚本与 CI 才能看到进展
        if [ "${ACTION_MODE:-0}" = "1" ]; then
            printf '%s\n' "$prefix$line"
        fi
    done <<EOF
$message
EOF
    LOG_LINES=$(printf '%s' "$LOG_LINES" | tail -n 400)
}

write_wizard_log() {
    # 追加写入向导日志文件（失败不影响主流程）
    local dir
    dir=$(dirname "$LOG_FILE")
    [ -d "$dir" ] || mkdir -p "$dir" 2>/dev/null || true
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "$LOG_FILE" 2>/dev/null || true
}

set_status() {
    # set_status <tone> <message>：记录一条用户可见的结果
    local tone="$1"
    local level="info"
    case "$tone" in
        fail) level="error" ;;
        warn) level="warn" ;;
    esac
    add_log "$level" "$2"
}

# ============================================================================
# 5. 命令执行（dry-run 一律只展示命令）
# ============================================================================

resolve_executable() {
    # 把命令名解析为可执行文件路径（含 macOS 常见安装目录）
    local name="$1"
    if [ -z "$name" ]; then
        printf ''
        return
    fi
    case "$name" in
        */*)
            if [ -x "$name" ]; then printf '%s' "$name"; fi
            return
            ;;
    esac
    local dir
    for dir in "$HOME/.local/bin" "/opt/homebrew/bin" "/usr/local/bin" "$HOME/.cargo/bin"; do
        if [ -x "$dir/$name" ]; then
            printf '%s' "$dir/$name"
            return
        fi
    done
    local old_ifs="$IFS"
    IFS=':'
    for dir in $PATH; do
        # macOS 上可执行文件没有扩展名；附带的 .exe 分支只为让本脚本能在
        # Windows 的 Git Bash 下跑通，便于两平台界面一致性自动化比对（对 macOS 无影响）
        if [ -x "$dir/$name" ] || [ -x "$dir/$name.exe" ]; then
            IFS="$old_ifs"
            if [ -x "$dir/$name" ]; then
                printf '%s' "$dir/$name"
            else
                printf '%s' "$dir/$name.exe"
            fi
            return
        fi
    done
    IFS="$old_ifs"
    printf ''
}

invoke_capture() {
    # invoke_capture <timeout> <cmd> [args...]：结果写入 CAP_OK / CAP_CODE / CAP_LINES
    local timeout="$1"
    shift
    CAP_OK=0
    CAP_CODE=0
    CAP_TIMEOUT=0
    CAP_LINES=""
    if [ "$OPT_DRY_RUN" = "1" ]; then
        add_log info "$(t common.dry_run): $*"
        CAP_OK=1
        return 0
    fi
    local exe
    exe=$(resolve_executable "$1")
    if [ -z "$exe" ]; then
        add_log warn "$(t log.exe_not_found): $1"
        CAP_CODE=127
        return 1
    fi
    shift
    local out_file err_file
    out_file=$(mktemp)
    err_file=$(mktemp)
    # 同样切到项目根执行（见 invoke_stream 的说明）
    ( cd "$PROJECT_ROOT" && "$exe" "$@" ) >"$out_file" 2>"$err_file" &
    local pid=$!
    # 看门狗：超时后强杀子进程（wait 会返回 137，据此判定超时）
    ( sleep "$timeout"; kill -9 "$pid" 2>/dev/null ) &
    local watchdog=$!
    wait "$pid" 2>/dev/null
    CAP_CODE=$?
    kill "$watchdog" 2>/dev/null || true
    wait "$watchdog" 2>/dev/null || true
    CAP_LINES=$(cat "$out_file" "$err_file" 2>/dev/null)
    rm -f "$out_file" "$err_file"
    if [ "$CAP_CODE" -eq 137 ]; then
        CAP_TIMEOUT=1
        add_log warn "$(t log.command_timeout seconds=$timeout): $exe"
        return 1
    fi
    if [ "$CAP_CODE" -eq 0 ]; then
        CAP_OK=1
        return 0
    fi
    return 1
}

invoke_stream() {
    # invoke_stream <title_key> <cmd> [args...]：实时输出到日志面板，返回子进程退出码
    local title_key="$1"
    shift
    local command_text="$*"
    if [ "$OPT_DRY_RUN" = "1" ]; then
        add_log info "$(t common.dry_run): $command_text"
        return 0
    fi
    add_log cmd "$command_text"
    show_running "$title_key" "$command_text"
    local exe
    exe=$(resolve_executable "$1")
    if [ -z "$exe" ]; then
        add_log warn "$(t log.exe_not_found): $1"
        return 127
    fi
    shift
    local code_file counter
    code_file=$(mktemp)
    counter=0
    # 在项目根目录下执行：uv / git 按工作目录识别项目，沿用调用者目录会误改另一个项目
    while IFS= read -r line; do
        add_log output "$line"
        counter=$((counter + 1))
        if [ $((counter % REDRAW_EVERY)) -eq 0 ]; then
            show_running "$title_key" "$command_text"
        fi
    done < <(cd "$PROJECT_ROOT" && { "$exe" "$@" 2>&1; printf '%s' "$?" > "$code_file"; })
    local code
    code=$(cat "$code_file" 2>/dev/null || printf '0')
    rm -f "$code_file"
    add_log info "$(t log.exit_code code=$code)"
    return "${code:-0}"
}

# ============================================================================
# 6. 环境状态采集
# ============================================================================

get_uv_path() {
    resolve_executable uv
}

get_framework_version() {
    # 读取 core/version.py 的 VERSION 常量
    local file="$PROJECT_ROOT/core/version.py"
    [ -f "$file" ] || return 0
    sed -n "s/^VERSION[[:space:]]*=[[:space:]]*[\"']\([^\"']*\)[\"'].*/\1/p" "$file" | head -n 1
}

venv_python() {
    printf '%s/bin/python' "$APP_VENV"
}

get_missing_imports() {
    # 在应用环境中检查关键依赖，输出缺失模块（空格分隔）
    local python
    python=$(venv_python)
    if [ ! -x "$python" ]; then
        printf '%s' "$REQUIRED_IMPORTS"
        return
    fi
    local code quoted=""
    local name
    for name in $REQUIRED_IMPORTS; do
        quoted="$quoted'$name', "
    done
    code="import importlib.util as u, json;print(json.dumps([n for n in [${quoted%, }] if u.find_spec(n) is None]))"
    if ! invoke_capture "$TIMEOUT_PROBE" "$python" -c "$code"; then
        printf '%s' "$REQUIRED_IMPORTS"
        return
    fi
    local json_text
    json_text=$(printf '%s' "$CAP_LINES" | tail -n 1)
    json_text=$(printf '%s' "$json_text" | tr -d '[]" ')
    printf '%s' "${json_text//,/ }"
}

get_dir_size() {
    # 目录占用字节数（du -sk 输出 KB）
    local path="$1"
    [ -d "$path" ] || { printf '0'; return; }
    du -sk "$path" 2>/dev/null | awk '{print $1 * 1024}' | head -n 1
}

format_size() {
    # 字节数 → 人类可读（B / KB / MB / GB / TB）
    awk -v bytes="$1" 'BEGIN {
        split("B KB MB GB TB", units, " ");
        value = bytes + 0;
        for (i = 1; i <= 5; i++) {
            if (value < 1024 || i == 5) {
                if (i == 1) printf "%.0f %s", value, units[i];
                else printf "%.1f %s", value, units[i];
                exit;
            }
            value = value / 1024;
        }
    }'
}

collect_state() {
    # 采集环境状态到 ST_* 全局变量（界面与体检共用）
    ST_UV_PATH=$(get_uv_path)
    ST_UV_VERSION=""
    ST_VENV_EXISTS=0
    ST_PYTHON_EXISTS=0
    ST_PYTHON_VERSION=""
    ST_MISSING=""
    ST_FRAMEWORK=$(get_framework_version)
    ST_HAS_LOCK=0
    ST_HAS_REQUIREMENTS=0
    ST_GIT_AVAILABLE=0
    ST_GIT_BRANCH=""
    ST_GIT_COMMIT=""
    ST_GIT_DIRTY=0
    ST_VENV_BYTES=0
    ST_PLATFORM=$(platform_label)
    [ -f "$PROJECT_ROOT/uv.lock" ] && ST_HAS_LOCK=1
    [ -f "$PROJECT_ROOT/requirements.txt" ] && ST_HAS_REQUIREMENTS=1
    [ -f "$APP_VENV/pyvenv.cfg" ] && ST_VENV_EXISTS=1
    [ -x "$(venv_python)" ] && ST_PYTHON_EXISTS=1
    if [ -n "$ST_UV_PATH" ]; then
        if invoke_capture "$TIMEOUT_PROBE" "$ST_UV_PATH" --version; then
            ST_UV_VERSION=$(printf '%s' "$CAP_LINES" | head -n 1)
        fi
    fi
    if [ "$ST_VENV_EXISTS" = "1" ] && [ "$ST_PYTHON_EXISTS" = "1" ]; then
        if invoke_capture "$TIMEOUT_PROBE" "$(venv_python)" -c 'import sys;print(".".join(str(p) for p in sys.version_info[:3]))'; then
            ST_PYTHON_VERSION=$(printf '%s' "$CAP_LINES" | tail -n 1)
        fi
        ST_MISSING=$(get_missing_imports)
    elif [ "$ST_VENV_EXISTS" = "1" ]; then
        ST_MISSING="python"
    fi
    if [ -d "$PROJECT_ROOT/.git" ] && [ -n "$(resolve_executable git)" ]; then
        ST_GIT_AVAILABLE=1
        if invoke_capture "$TIMEOUT_PROBE" git rev-parse --abbrev-ref HEAD; then
            ST_GIT_BRANCH=$(printf '%s' "$CAP_LINES" | head -n 1)
        fi
        if invoke_capture "$TIMEOUT_PROBE" git rev-parse --short HEAD; then
            ST_GIT_COMMIT=$(printf '%s' "$CAP_LINES" | head -n 1)
        fi
        if invoke_capture "$TIMEOUT_PROBE" git status --porcelain; then
            [ -n "$CAP_LINES" ] && ST_GIT_DIRTY=1
        fi
    fi
    if [ "$ST_VENV_EXISTS" = "1" ]; then
        ST_VENV_BYTES=$(get_dir_size "$APP_VENV")
    fi
}

env_ready() {
    if [ "$ST_VENV_EXISTS" = "1" ] && [ "$ST_PYTHON_EXISTS" = "1" ] && [ -z "$ST_MISSING" ]; then
        return 0
    fi
    return 1
}

# ============================================================================
# 7. 屏幕绘制
# ============================================================================

menu_keys() {
    printf 'menu.status menu.install menu.upgrade menu.manage menu.doctor menu.cleanup menu.launch menu.language menu.help'
}

menu_pages() {
    printf 'status install upgrade manage doctor cleanup launch language help'
}

show_menu() {
    # show_menu <index>：绘制主菜单（选中项以 ▸ 标记）
    local index="$1"
    clear_screen
    write_header
    local keys pages number=1
    keys=$(menu_keys)
    pages=$(menu_pages)
    local key page
    for key in $keys; do
        page=$(printf '%s' "$pages" | cut -d' ' -f "$number")
        if [ "$number" -eq "$index" ]; then
            out_line accent "  $number ${CURSOR_MARK} $(t "$key")"
        else
            out_line "" "  $number   $(t "$key")"
        fi
        number=$((number + 1))
    done
    write_footer
}

page_title() {
    # page_title <title_key> [explain_key]
    out_line title " $(t "$1")"
    if [ "$#" -ge 2 ] && [ -n "$2" ]; then
        out_line dim " $(t "$2")"
    fi
    rule
}

action_list() {
    # action_list <label> [tone] ...：编号即快捷键
    local number=1
    while [ "$#" -gt 0 ]; do
        local label="$1"
        local tone=""
        if [ "$#" -ge 2 ]; then
            tone="$2"
            shift
        fi
        shift
        out_line "$tone" "  $number $label"
        number=$((number + 1))
    done
}

show_status_page() {
    collect_state
    clear_screen
    write_header
    page_title menu.status status.header
    local uv_text="$ST_UV_VERSION"
    [ -n "$uv_text" ] || uv_text=$(t common.not_installed)
    local py_text="$ST_PYTHON_VERSION"
    [ -n "$py_text" ] || py_text=$(t common.not_installed)
    out_line "" "  $(t status.uv): $uv_text"
    out_line "" "  $(t status.python): $py_text"
    out_line "" "  $(t status.venv): $(venv_text)"
    out_line "" "  $(t status.deps): $(deps_text)"
    local framework="$ST_FRAMEWORK"
    [ -n "$framework" ] || framework=$(t common.unknown)
    out_line "" "  $(t status.framework): $framework"
    out_line "" "  $(t status.git): $(git_text)"
    out_line "" "  $(t status.platform): $ST_PLATFORM"
    out_line "" "  $(t status.path): $PROJECT_ROOT"
    if [ "$ST_VENV_BYTES" -gt 0 ]; then
        out_line "" "  $(t manage.disk_usage): $(format_size "$ST_VENV_BYTES")"
    fi
    rule
    if env_ready; then
        out_line warn " $(t status.next_hint_ready)"
    else
        out_line warn " $(t status.next_hint_missing)"
    fi
    action_list "$(t menu.install)" accent "$(t menu.doctor)" "" "$(t menu.launch)" ""
    write_footer page
}

venv_text() {
    if env_ready; then
        t status.venv_ready
    elif [ "$ST_VENV_EXISTS" = "1" ]; then
        t status.venv_broken
    else
        t status.venv_missing
    fi
}

deps_text() {
    if [ -z "$ST_MISSING" ]; then
        t common.installed
    else
        printf '%s' "$ST_MISSING"
    fi
}

git_text() {
    if [ "$ST_GIT_AVAILABLE" != "1" ]; then
        t common.unknown
        return
    fi
    local text="$ST_GIT_BRANCH"
    if [ -n "$ST_GIT_COMMIT" ]; then
        text="$text @ $ST_GIT_COMMIT"
    fi
    if [ "$ST_GIT_DIRTY" = "1" ]; then
        text="$text *"
    fi
    printf '%s' "$text"
}

show_running() {
    # show_running <title_key> <command>
    # 非交互动作模式（--action）不渲染全屏页，过程输出由 add_log 负责（对齐 setup.ps1 的 NonInteractive）
    if [ "${ACTION_MODE:-0}" = "1" ]; then
        return
    fi
    clear_screen
    write_header
    page_title "$1"
    out_line accent "  \$ $2"
    rule
    printf '%s\n' "$LOG_LINES" | tail -n 12 | while IFS= read -r line; do
        [ -n "$line" ] && out_line dim "  $line"
    done
    rule
    out_line dim " $(t ui.abort_hint)"
}

show_result() {
    # show_result <tone> <message_key> [name=value ...]
    local tone="$1"
    local key="$2"
    shift 2
    rule
    out_line "$tone" " $(t "$key" "$@")"
    wait_any_key
}

read_confirm() {
    # read_confirm <message_key> [danger]：是 / 否确认（--yes 时自动确认）
    local key="$1"
    if [ "$OPT_YES" = "1" ]; then
        add_log info "$(t "$key") -> --yes"
        return 0
    fi
    local tone="warn"
    [ "${2:-}" = "danger" ] && tone="fail"
    rule
    out_line "$tone" " $(t common.confirm)"
    out_line "" " $(t "$key")"
    out_line dim " $(t ui.dialog_keys)"
    local answer
    while true; do
        read_key
        answer="$READ_KEY_RESULT"
        case "$answer" in
            yes|enter) return 0 ;;
            no|escape|quit) return 1 ;;
        esac
    done
}

# ============================================================================
# 8. 动作：安装与修复
# ============================================================================

is_first_install() {
    [ ! -f "$APP_VENV/pyvenv.cfg" ]
}

ensure_uv() {
    # 确保 uv 可用；缺失时先征得用户同意再执行官方安装脚本
    if [ -n "$(get_uv_path)" ]; then
        return 0
    fi
    add_log warn "$(t install.need_uv_confirm)"
    if ! read_confirm install.need_uv_confirm; then
        add_log warn "$(t common.cancel)"
        return 1
    fi
    add_log info "$(t install.uv_install_cmd cmd="$UV_INSTALL_CMD")"
    invoke_stream install.step_uv sh -c "$UV_INSTALL_CMD" || true
    if [ -z "$(get_uv_path)" ]; then
        set_status fail "$(t install.uv_manual cmd="$UV_INSTALL_CMD")"
        return 1
    fi
    return 0
}

prepare_python() {
    # 准备 Python：失败只警告（系统已有解释器时后续步骤仍可成功）
    local uv
    uv=$(get_uv_path)
    [ -n "$uv" ] || uv=uv
    if ! invoke_stream install.step_python "$uv" python install "$REQUIRED_PYTHON"; then
        add_log warn "$(t install.python_download_hint url="$PYTHON_URL")"
        return 1
    fi
    return 0
}

is_lock_usable() {
    # uv.lock 是否可用（存在、非空、且是 uv 的 TOML 锁文件）
    # 空文件或半截文件会让 uv sync 直接报 "Failed to parse uv.lock"，用户看不懂；
    # 这里提前识别并回退到 uv pip install -r requirements.txt，保证安装仍能完成。
    local lock="$PROJECT_ROOT/uv.lock"
    [ -s "$lock" ] || return 1
    head -n 1 "$lock" | grep -q '^version =' || return 1
    return 0
}

install_dependencies() {
    # 初次安装用 uv sync；已有环境或锁文件不可用时用 uv pip install（不删除插件自装依赖）
    local uv
    uv=$(get_uv_path)
    [ -n "$uv" ] || uv=uv
    if is_first_install; then
        if is_lock_usable; then
            invoke_stream install.step_deps "$uv" sync --no-dev --no-install-project
            return $?
        fi
        add_log warn "$(t log.lock_unusable): uv.lock"
    fi
    invoke_stream install.step_deps "$uv" pip install -r requirements.txt
    return $?
}

verify_result() {
    # 自检关键组件：VERIFY_OK=1 表示可用，VERIFY_MISSING 为缺失清单
    VERIFY_OK=0
    if [ ! -x "$(venv_python)" ]; then
        VERIFY_MISSING="$REQUIRED_IMPORTS"
        return 1
    fi
    VERIFY_MISSING=$(get_missing_imports)
    if [ -z "$VERIFY_MISSING" ]; then
        VERIFY_OK=1
        return 0
    fi
    return 1
}

run_install() {
    # run_install [repair-only]
    local repair_only="${1:-}"
    local first=0
    if is_first_install; then
        first=1
        add_log info "$(t install.first_time)"
    else
        add_log info "$(t install.repair)"
    fi
    if [ "$repair_only" != "repair-only" ]; then
        if ! ensure_uv; then
            show_result fail common.failed
            return
        fi
        prepare_python || true
    elif [ -z "$(get_uv_path)" ]; then
        set_status fail "$(t common.not_installed)"
        show_result fail common.failed
        return
    fi
    install_dependencies || true
    if verify_result; then
        if [ "$first" = "1" ]; then
            create_desktop_launcher || true
        fi
        if [ "$repair_only" = "repair-only" ]; then
            show_result ok install.repaired
        else
            show_result ok install.success
        fi
        return
    fi
    show_result fail install.verify_failed detail="$VERIFY_MISSING"
}

# ============================================================================
# 9. 动作：升级框架
# ============================================================================

upgrade_mode() {
    # git：有仓库且 git 可用；否则 zip（下载官方压缩包覆盖）
    if [ -d "$PROJECT_ROOT/.git" ] && [ -n "$(resolve_executable git)" ]; then
        printf 'git'
        return
    fi
    printf 'zip'
}

local_changes() {
    # 已跟踪文件的本地修改（未跟踪文件不影响 git pull）
    if invoke_capture "$TIMEOUT_PROBE" git status --porcelain --untracked-files=no; then
        printf '%s' "$CAP_LINES"
    fi
}

clean_work_dir() {
    [ "$OPT_DRY_RUN" = "1" ] && return
    [ -d "$WORK_DIR" ] && rm -rf "$WORK_DIR"
}

download_archive() {
    # 取升级用的代码压缩包：默认下载，--archive 指定时直接用本地包（离线升级）；ARCHIVE 为空表示失败
    ARCHIVE=""
    if [ -n "$OPT_ARCHIVE" ]; then
        if [ ! -f "$OPT_ARCHIVE" ]; then
            add_log error "$(t log.archive_missing): $OPT_ARCHIVE"
            return 1
        fi
        add_log info "$(t log.archive_local): $OPT_ARCHIVE"
        ARCHIVE="$OPT_ARCHIVE"
        return 0
    fi
    if [ "$OPT_DRY_RUN" = "1" ]; then
        add_log info "$(t common.dry_run): $ZIP_URL"
        return 1
    fi
    mkdir -p "$WORK_DIR" || return 1
    ARCHIVE="$WORK_DIR/InstructionX-main.zip"
    if ! curl -fsSL --max-time "$TIMEOUT_DOWNLOAD" -o "$ARCHIVE" "$ZIP_URL"; then
        add_log error "$(t log.download_failed)"
        ARCHIVE=""
        return 1
    fi
    return 0
}

extract_archive() {
    # 解压并返回仓库根目录（ARCHIVE_ROOT 为空表示失败）
    ARCHIVE_ROOT=""
    local target="$WORK_DIR/src"
    rm -rf "$target"
    mkdir -p "$target" || return 1
    if ! extract_zip "$ARCHIVE" "$target"; then
        add_log error "$(t log.extract_failed)"
        return 1
    fi
    local count=0
    local item
    for item in "$target"/*; do
        [ -d "$item" ] || continue
        ARCHIVE_ROOT="$item"
        count=$((count + 1))
    done
    if [ "$count" -ne 1 ]; then
        add_log error "$(t log.archive_layout)"
        ARCHIVE_ROOT=""
        return 1
    fi
    return 0
}

extract_zip() {
    # 解压 zip：依次尝试 unzip（macOS 自带）→ ditto（macOS 备选）→ tar（bsdtar 可读 zip）
    local archive="$1"
    local target="$2"
    local code=1
    if command -v unzip >/dev/null 2>&1; then
        unzip -q "$archive" -d "$target"
        code=$?
        # Info-ZIP 对「压缩包内路径使用反斜杠」（Windows 上打包的常见情况）等情况
        # 只给警告并返回 1，但文件其实已经解压成功——不能因此判定失败
        if [ "$code" -le 1 ] && [ -n "$(ls -A "$target" 2>/dev/null)" ]; then
            return 0
        fi
    fi
    if command -v ditto >/dev/null 2>&1 && ditto -x -k "$archive" "$target"; then
        return 0
    fi
    if command -v tar >/dev/null 2>&1 && tar -xf "$archive" -C "$target" \
        && [ -n "$(ls -A "$target" 2>/dev/null)" ]; then
        return 0
    fi
    return 1
}

is_preserved_name() {
    local name="$1"
    local item
    for item in $PRESERVE_DIRS $SKIP_DIRS; do
        [ "$item" = "$name" ] && return 0
    done
    return 1
}

overlay_files() {
    # 把新代码覆盖到项目根（保留用户数据与本地环境）
    local root="$1"
    local copied=0
    local item name
    for item in "$root"/* "$root"/.[!.]*; do
        [ -e "$item" ] || continue
        name=$(basename "$item")
        if is_preserved_name "$name"; then
            continue
        fi
        if cp -R "$item" "$PROJECT_ROOT/" 2>/dev/null; then
            copied=$((copied + 1))
        else
            add_log warn "$(t log.overwrite_failed name="$name")"
        fi
    done
    add_log info "$(t log.overwrite_done count="$copied"); $(t log.preserved items="$PRESERVE_DIRS")"
}

run_upgrade() {
    local before mode
    before=$(get_framework_version)
    mode=$(upgrade_mode)
    if [ "$mode" = "git" ]; then
        local changes
        changes=$(local_changes)
        if ! invoke_stream upgrade.title git pull --ff-only; then
            local detail="$changes"
            [ -n "$detail" ] || detail="git pull failed"
            show_result warn upgrade.local_changes detail="$(printf '%s' "$detail" | head -n 1)"
            return
        fi
    else
        if ! read_confirm upgrade.need_git_confirm; then
            add_log warn "$(t common.cancel)"
            return
        fi
        if ! download_archive || ! extract_archive; then
            show_result fail common.failed
            clean_work_dir
            return
        fi
        overlay_files "$ARCHIVE_ROOT"
    fi
    install_dependencies || true
    clean_work_dir
    if verify_result; then
        show_result ok upgrade.success version="$(get_framework_version)"
        return
    fi
    show_result fail install.verify_failed detail="$VERIFY_MISSING"
}

# ============================================================================
# 10. 动作：一键体检
# ============================================================================

folder_check() {
    # 配置 / 数据目录可写性：返回空串表示正常，否则返回原因
    if [ "$OPT_DRY_RUN" = "1" ]; then
        return 0
    fi
    local name folder probe
    for name in config data; do
        folder="$PROJECT_ROOT/$name"
        if ! mkdir -p "$folder" 2>/dev/null; then
            printf '%s: cannot create\n' "$name"
            return 0
        fi
        probe="$folder/.write_probe"
        if ! printf 'ok' > "$probe" 2>/dev/null; then
            printf '%s: not writable\n' "$name"
            return 0
        fi
        rm -f "$probe" 2>/dev/null || true
    done
    return 0
}

network_check() {
    # 能否访问软件源（PyPI）
    if [ "$OPT_DRY_RUN" = "1" ]; then
        return 0
    fi
    curl -fsS -m 5 -o /dev/null https://pypi.org/simple/ 2>/dev/null
}

free_disk_kb() {
    df -k "$PROJECT_ROOT" 2>/dev/null | awk 'NR==2 {print $4}'
}

run_doctor() {
    # 采集 9 项检查：CHECKS 每项为 key|tone|detail|advice
    collect_state
    CHECKS=()
    local uv_advice=""
    if [ -z "$ST_UV_PATH" ]; then
        uv_advice="doctor.advice_install_uv"
        CHECKS+=("doctor.check_uv|fail|$ST_UV_VERSION|$uv_advice")
    else
        CHECKS+=("doctor.check_uv|ok|$ST_UV_VERSION|")
    fi
    local py_tone="fail" py_advice="doctor.advice_install_uv"
    if [ -n "$ST_PYTHON_VERSION" ]; then
        py_tone="ok"
        py_advice=""
    elif [ -n "$ST_UV_PATH" ]; then
        py_tone="warn"
        py_advice="doctor.advice_run_install"
    fi
    CHECKS+=("doctor.check_python|$py_tone|$ST_PYTHON_VERSION|$py_advice")
    if env_ready; then
        CHECKS+=("doctor.check_venv|ok|$APP_VENV|")
        CHECKS+=("doctor.check_imports|ok|$(printf '%s' "$REQUIRED_IMPORTS" | tr ' ' ',')|")
    else
        CHECKS+=("doctor.check_venv|fail|$APP_VENV|doctor.advice_run_install")
        CHECKS+=("doctor.check_imports|fail|$ST_MISSING|doctor.advice_run_install")
    fi
    if [ "$OPT_DRY_RUN" = "1" ]; then
        CHECKS+=("doctor.check_writable|ok|dry-run|")
    else
        local folder_problem
        folder_problem=$(folder_check)
        if [ -n "$folder_problem" ]; then
            CHECKS+=("doctor.check_writable|fail|$folder_problem|doctor.advice_free_disk")
        else
            CHECKS+=("doctor.check_writable|ok||")
        fi
    fi
    local missing_files=""
    [ "$ST_HAS_REQUIREMENTS" = "1" ] || missing_files="requirements.txt"
    if [ "$ST_HAS_LOCK" != "1" ]; then
        if [ -n "$missing_files" ]; then missing_files="$missing_files, "; fi
        missing_files="${missing_files}uv.lock"
    fi
    if [ -n "$missing_files" ]; then
        CHECKS+=("doctor.check_lock|warn|$missing_files|doctor.advice_run_install")
    else
        CHECKS+=("doctor.check_lock|ok||")
    fi
    if [ "$OPT_DRY_RUN" = "1" ]; then
        CHECKS+=("doctor.check_network|ok|dry-run|")
    elif network_check; then
        CHECKS+=("doctor.check_network|ok|pypi.org|")
    else
        CHECKS+=("doctor.check_network|warn||doctor.advice_check_network")
    fi
    CHECKS+=("doctor.check_platform|ok|$ST_PLATFORM|")
    local free_kb
    free_kb=$(free_disk_kb)
    if [ -z "$free_kb" ]; then
        CHECKS+=("doctor.check_disk|warn||")
    elif [ "$free_kb" -lt "$MIN_FREE_DISK_KB" ]; then
        CHECKS+=("doctor.check_disk|warn|$(format_size $((free_kb * 1024)))|doctor.advice_free_disk")
    else
        CHECKS+=("doctor.check_disk|ok|$(format_size $((free_kb * 1024)))|")
    fi
}

check_name() {
    t "$1" python="$REQUIRED_PYTHON" platform="$ST_PLATFORM"
}

check_advice_text() {
    # check_advice_text <advice_key>
    [ -n "$1" ] || return 0
    t "$1" platform="$ST_PLATFORM" python="$REQUIRED_PYTHON"
}

count_problems() {
    local item count=0
    for item in "${CHECKS[@]}"; do
        case "$item" in
            *"|ok|"*) ;;
            *) count=$((count + 1)) ;;
        esac
    done
    printf '%s' "$count"
}

show_doctor_page() {
    clear_screen
    write_header
    page_title doctor.title doctor.explain
    run_doctor
    local item key tone detail advice mark
    for item in "${CHECKS[@]}"; do
        IFS='|' read -r key tone detail advice <<< "$item"
        case "$tone" in
            ok) mark='OK ' ;;
            warn) mark='!  ' ;;
            *) mark='X  ' ;;
        esac
        local line="  $mark$(check_name "$key")"
        [ -n "$detail" ] && line="$line  ($detail)"
        out_line "$tone" "$line"
        local advice_text
        advice_text=$(check_advice_text "$advice")
        if [ -n "$advice_text" ]; then
            out_line dim "       $(t doctor.advice advice="$advice_text")"
        fi
    done
    rule
    local problems
    problems=$(count_problems)
    if [ "$problems" -eq 0 ]; then
        out_line ok " $(t doctor.all_ok)"
    else
        out_line warn " $(t doctor.has_problems count="$problems")"
    fi
    action_list "$(t menu.doctor)" accent
    write_footer page
}

run_doctor_action() {
    run_doctor
    local problems
    problems=$(count_problems)
    if [ "$problems" -eq 0 ]; then
        set_status ok "$(t doctor.all_ok)"
        return
    fi
    set_status warn "$(t doctor.has_problems count="$problems")"
    local item key tone detail advice
    for item in "${CHECKS[@]}"; do
        IFS='|' read -r key tone detail advice <<< "$item"
        [ "$tone" = "ok" ] && continue
        add_log warn "$(check_name "$key") -> $(check_advice_text "$advice")"
    done
}

# ============================================================================
# 11. 动作：环境管理、清理、启动
# ============================================================================

desktop_app_path() {
    # 桌面启动器（.app 包）的完整路径
    printf '%s/Desktop/%s' "$HOME" "$DESKTOP_APP_NAME"
}

create_desktop_launcher() {
    # 首次安装成功后创建桌面启动器（已存在则跳过）：
    # .app 包双击直接启动应用、不开 Terminal；图标由 assets/logo.png 尽力转换
    local app_path
    app_path=$(desktop_app_path)
    if [ "$OPT_DRY_RUN" = "1" ]; then
        add_log info "$(t common.dry_run): $(t log.shortcut_create) $app_path"
        return 0
    fi
    [ -e "$app_path" ] && return 0
    if ! mkdir -p "$app_path/Contents/MacOS" "$app_path/Contents/Resources" 2>/dev/null; then
        add_log warn "$(t log.shortcut_failed): $app_path"
        return 1
    fi
    write_launcher_plist "$app_path"
    write_launcher_script "$app_path/Contents/MacOS"
    build_launcher_icon "$app_path/Contents/Resources" || true
    add_log info "$(t log.shortcut_created path="$app_path")"
    return 0
}

write_launcher_plist() {
    # 生成 .app 包的 Info.plist（$1 = .app 包路径）
    cat > "$1/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>InstructionX</string>
    <key>CFBundleDisplayName</key>
    <string>InstructionX</string>
    <key>CFBundleIdentifier</key>
    <string>tech.kkpip.instructionx</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIconFile</key>
    <string>icon</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF
}

write_launcher_script() {
    # 生成启动脚本（$1 = Contents/MacOS 目录）：exec 让 Python 进程接替，脚本不驻留
    cat > "$1/launcher" <<EOF
#!/bin/bash
exec "$APP_VENV/bin/python" "$PROJECT_ROOT/main.py"
EOF
    chmod +x "$1/launcher"
}

build_launcher_icon() {
    # 把 assets/logo.png 转成 icon.icns（$1 = Contents/Resources 目录）。
    # sips / iconutil 均为 macOS 自带工具；缺失或失败时跳过（仅影响图标，不影响启动）
    local logo="$PROJECT_ROOT/assets/logo.png"
    [ -f "$logo" ] || return 1
    command -v sips >/dev/null 2>&1 || return 1
    command -v iconutil >/dev/null 2>&1 || return 1
    local iconset="$WORK_DIR/icon.iconset"
    rm -rf "$iconset"
    mkdir -p "$iconset" || return 1
    local pair size name
    for pair in 16:icon_16x16 32:icon_16x16@2x 32:icon_32x32 64:icon_32x32@2x \
        128:icon_128x128 256:icon_128x128@2x 256:icon_256x256 512:icon_256x256@2x \
        512:icon_512x512 1024:icon_512x512@2x; do
        size=${pair%%:*}
        name=${pair#*:}
        sips -z "$size" "$size" "$logo" --out "$iconset/$name.png" >/dev/null 2>&1 || return 1
    done
    iconutil -c icns "$iconset" -o "$1/icon.icns" 2>/dev/null || return 1
    rm -rf "$iconset"
    return 0
}

remove_desktop_launcher() {
    # 删除桌面启动器（卸载时调用；不存在视为成功）
    local app_path
    app_path=$(desktop_app_path)
    if [ "$OPT_DRY_RUN" = "1" ]; then
        add_log info "$(t common.dry_run): $(t log.shortcut_remove) $app_path"
        return 0
    fi
    [ -e "$app_path" ] || return 0
    if rm -rf "$app_path" 2>/dev/null; then
        add_log info "$(t log.shortcut_deleted path="$app_path")"
    else
        add_log warn "$(t log.delete_failed path="$app_path")"
    fi
}

remove_app_venv() {
    if [ "$OPT_DRY_RUN" = "1" ]; then
        add_log info "$(t common.dry_run): $(t log.delete_env) $APP_VENV"
        return 0
    fi
    if [ ! -d "$APP_VENV" ]; then
        return 0
    fi
    if rm -rf "$APP_VENV" 2>/dev/null; then
        add_log info "$(t log.deleted path="$APP_VENV")"
        return 0
    fi
    add_log error "$(t log.delete_failed path="$APP_VENV")"
    return 1
}

run_rebuild() {
    read_confirm manage.rebuild_confirm || return
    remove_app_venv || { show_result fail common.failed; return; }
    run_install
}

run_refresh_deps() {
    install_dependencies || true
    if verify_result; then
        show_result ok manage.refresh_done
        return
    fi
    show_result fail install.verify_failed detail="$VERIFY_MISSING"
}

run_clean_cache() {
    local uv
    uv=$(get_uv_path)
    [ -n "$uv" ] || uv=uv
    if invoke_stream manage.clear_cache "$uv" cache clean; then
        local cache_dir="${UV_CACHE_DIR:-$HOME/.cache/uv}"
        set_status ok "$(t manage.clear_cache_done path="$cache_dir")"
        show_result ok manage.clear_cache_done path="$cache_dir"
        return
    fi
    show_result fail common.failed
}

open_folder() {
    local name="$1"
    local folder="$PROJECT_ROOT/$name"
    mkdir -p "$folder" 2>/dev/null || true
    if [ "$OPT_DRY_RUN" = "1" ]; then
        add_log info "$(t common.dry_run): $(t log.open_folder) $folder"
        return
    fi
    if open "$folder" 2>/dev/null; then
        add_log info "$folder"
        return
    fi
    add_log warn "$(t log.open_folder_failed)"
}

run_remove_venv() {
    read_confirm manage.remove_venv_confirm || return
    if remove_app_venv; then
        show_result ok manage.remove_venv_done
        return
    fi
    show_result fail common.failed
}

run_recreate_shortcut() {
    # 重建桌面启动器（误删后恢复；先删后建，图标或路径变更也能刷新）。
    # 启动器指向 .venv 的解释器，环境未安装时引导用户先执行「安装 / 修复环境」
    collect_state
    if [ "$ST_VENV_EXISTS" != "1" ] || [ "$ST_PYTHON_EXISTS" != "1" ]; then
        show_result warn launch.need_install
        return
    fi
    remove_desktop_launcher
    if create_desktop_launcher; then
        show_result ok manage.recreate_shortcut_done
        return
    fi
    show_result fail common.failed
}

run_clean_temp() {
    clean_work_dir
    set_status ok "$(t cleanup.temp_done)"
    show_result ok cleanup.temp_done
}

run_uninstall() {
    read_confirm cleanup.uninstall_warning danger || return
    read_confirm cleanup.uninstall_confirm danger || return
    local name target failed=""
    for name in $UNINSTALL_DIRS; do
        target="$PROJECT_ROOT/$name"
        [ -e "$target" ] || continue
        if [ "$OPT_DRY_RUN" = "1" ]; then
            add_log info "$(t common.dry_run): $(t log.delete_env) $target"
            continue
        fi
        if rm -rf "$target" 2>/dev/null; then
            add_log info "$(t log.deleted path="$target")"
        else
            failed="$failed $name"
            add_log error "$(t log.delete_failed path="$target")"
        fi
    done
    # 桌面启动器随卸载一并删除，避免残留指向已删除环境的失效入口
    remove_desktop_launcher
    if [ -n "$failed" ]; then
        show_result fail common.failed detail="$failed"
        return
    fi
    show_result ok cleanup.uninstall_done
}

run_launch() {
    collect_state
    if ! env_ready; then
        set_status warn "$(t launch.need_install)"
        show_result warn launch.need_install
        return
    fi
    add_log info "$(t launch.starting)"
    invoke_stream launch.title "$(venv_python)" "$PROJECT_ROOT/main.py"
    show_result ok launch.exit_code code="$?"
}

# ============================================================================
# 12. 页面
# ============================================================================

show_install_page() {
    clear_screen
    write_header
    page_title install.title install.explain
    if is_first_install; then
        out_line warn " $(t install.first_time)"
    else
        out_line warn " $(t install.repair)"
    fi
    rule
    out_line dim " $(t install.plan)"
    out_line "" "   1. $(t install.step_uv)"
    out_line "" "   2. $(t install.step_python python="$REQUIRED_PYTHON")"
    out_line "" "   3. $(t install.step_venv)"
    out_line "" "   4. $(t install.step_deps)"
    out_line "" "   5. $(t install.step_verify)"
    rule
    local uv
    uv=$(get_uv_path)
    [ -n "$uv" ] || uv=uv
    if is_first_install; then
        out_line dim "   \$ $uv $SYNC_ARGS"
    else
        out_line dim "   \$ $uv $PIP_ARGS"
    fi
    rule
    action_list "$(t menu.install)" accent "$(t manage.refresh_deps)" ""
    write_footer page
}

show_upgrade_page() {
    collect_state
    clear_screen
    write_header
    page_title upgrade.title upgrade.explain
    local framework="$ST_FRAMEWORK"
    [ -n "$framework" ] || framework=$(t common.unknown)
    out_line "" " $(t upgrade.current_version): $framework"
    if [ "$(upgrade_mode)" = "git" ]; then
        out_line "" " $(t upgrade.with_git)"
        local changes
        changes=$(local_changes | head -n 1)
        if [ -n "$changes" ]; then
            out_line warn " $(t upgrade.local_changes detail="$changes")"
        fi
    else
        out_line "" " $(t upgrade.without_git)"
    fi
    out_line dim " $(t upgrade.preserve items="$PRESERVE_DIRS")"
    rule
    action_list "$(t menu.upgrade)" accent "$(t common.refresh)" ""
    write_footer page
}

show_manage_page() {
    collect_state
    clear_screen
    write_header
    page_title manage.title
    local size
    if [ "$ST_VENV_BYTES" -gt 0 ]; then
        size=$(format_size "$ST_VENV_BYTES")
    else
        size=$(t common.unknown)
    fi
    out_line "" " $(t manage.disk_usage): $size"
    out_line "" " $(t status.venv): $(venv_text)"
    rule
    action_list "$(t manage.rebuild)" warn \
        "$(t manage.refresh_deps)" "" \
        "$(t manage.clear_cache)" "" \
        "$(t manage.open_config)" "" \
        "$(t manage.open_data)" "" \
        "$(t manage.open_logs)" "" \
        "$(t manage.recreate_shortcut)" "" \
        "$(t manage.remove_venv)" fail
    write_footer page
}

show_cleanup_page() {
    clear_screen
    write_header
    page_title cleanup.title cleanup.explain
    out_line fail " $(t cleanup.uninstall_warning)"
    rule
    action_list "$(t cleanup.temp)" "" "$(t manage.clear_cache)" "" "$(t cleanup.uninstall)" fail
    write_footer page
}

show_launch_page() {
    collect_state
    clear_screen
    write_header
    page_title launch.title launch.explain
    if env_ready; then
        out_line ok " $(t launch.starting)"
        out_line dim "   $(venv_python)"
    else
        out_line warn " $(t launch.need_install)"
    fi
    rule
    action_list "$(t menu.launch)" accent
    write_footer page
}

show_language_page() {
    clear_screen
    write_header
    page_title menu.language
    if [ "$UI_LANG" = "zh" ]; then
        out_line accent "  1 ${CURSOR_MARK} $(t lang.name.zh)"
        out_line "" "  2   $(t lang.name.en)"
    else
        out_line "" "  1   $(t lang.name.zh)"
        out_line accent "  2 ${CURSOR_MARK} $(t lang.name.en)"
    fi
    rule
    out_line dim " $(t ui.lang_hint)"
    write_footer page
}

show_help_page() {
    clear_screen
    write_header
    page_title help.title
    local line
    while IFS= read -r line; do
        out_line "" " $line"
    done <<EOF
$(t help.body)
EOF
    rule
    out_line dim " $LOG_FILE"
    write_footer page
}

show_page() {
    case "$1" in
        status) show_status_page ;;
        install) show_install_page ;;
        upgrade) show_upgrade_page ;;
        manage) show_manage_page ;;
        doctor) show_doctor_page ;;
        cleanup) show_cleanup_page ;;
        launch) show_launch_page ;;
        language) show_language_page ;;
        help) show_help_page ;;
        *) show_menu 1 ;;
    esac
}

set_language() {
    # 切换界面语言并持久化到 .tui/lang（两平台共用）
    local target="$1"
    UI_LANG="$target"
    load_text "$target"
    if [ "$OPT_DRY_RUN" != "1" ]; then
        if mkdir -p "$(dirname "$LANG_FILE")" 2>/dev/null && printf '%s' "$target" > "$LANG_FILE"; then
            add_log info "$(t log.lang_saved)"
        else
            add_log warn "$(t log.lang_save_failed)"
        fi
    fi
}

# ============================================================================
# 13. 页面动作与主循环
# ============================================================================

run_page_action() {
    # run_page_action <page> <key>
    local page="$1"
    local key="$2"
    case "$page:$key" in
        status:1) run_install ;;
        status:2) run_doctor_action ;;
        status:3) run_launch ;;
        install:1) run_install ;;
        install:2) run_install repair-only ;;
        upgrade:1) run_upgrade ;;
        manage:1) run_rebuild ;;
        manage:2) run_refresh_deps ;;
        manage:3) run_clean_cache ;;
        manage:4) open_folder config ;;
        manage:5) open_folder data ;;
        manage:6) open_folder logs ;;
        manage:7) run_recreate_shortcut ;;
        manage:8) run_remove_venv ;;
        doctor:1) run_doctor_action ;;
        cleanup:1) run_clean_temp ;;
        cleanup:2) run_clean_cache ;;
        cleanup:3) run_uninstall ;;
        launch:1) run_launch ;;
    esac
}

start_page() {
    # 进入某页面并处理按键；返回 1 表示用户按 q 退出整个向导
    local page="$1"
    if [ "$page" = "help" ]; then
        show_help_page
        # 走 read_key：--keys 队列可驱动（与 setup.ps1 的 -Keys 一致），输入结束时安全返回
        read_key
        return 0
    fi
    while true; do
        show_page "$page"
        local key
        read_key
        key="$READ_KEY_RESULT"
        case "$key" in
            quit) return 1 ;;
            escape|enter|no) return 0 ;;
            refresh) continue ;;
            lang)
                if [ "$UI_LANG" = "zh" ]; then set_language en; else set_language zh; fi
                continue
                ;;
            zh|en)
                set_language "$key"
                continue
                ;;
        esac
        if [ "$page" = "language" ]; then
            case "$key" in
                1) set_language zh; return 0 ;;
                2) set_language en; return 0 ;;
            esac
            continue
        fi
        run_page_action "$page" "$key"
    done
}

start_wizard() {
    # 向导主循环：菜单选择 → 页面 → 动作
    local index=1
    local keys pages count=9
    keys=$(menu_keys)
    pages=$(menu_pages)
    add_log info "$(t app.title) ${TITLE_SEP} $(platform_label)"
    while true; do
        show_menu "$index"
        local key
        read_key
        key="$READ_KEY_RESULT"
        case "$key" in
            quit) return 0 ;;
            up) index=$((index - 1)); [ "$index" -lt 1 ] && index=$count; continue ;;
            down) index=$((index + 1)); [ "$index" -gt "$count" ] && index=1; continue ;;
            refresh) continue ;;
            lang)
                if [ "$UI_LANG" = "zh" ]; then set_language en; else set_language zh; fi
                continue
                ;;
            zh|en)
                set_language "$key"
                continue
                ;;
        esac
        case "$key" in
            [1-9]) index="$key" ;;
            enter) ;;
            *) continue ;;
        esac
        local page
        page=$(printf '%s' "$pages" | cut -d' ' -f "$index")
        if ! start_page "$page"; then
            return 0
        fi
    done
}

# ============================================================================
# 14. 文本模式（体检报告 / 状态导出 / 界面预览）
# ============================================================================

run_text_check() {
    # 打印文本版体检报告：0 全部通过；1 存在异常项
    printf '== %s %s %s ==\n' "$(t app.title)" "$TITLE_SEP" "$(t doctor.title)"
    printf '   %s\n' "$PROJECT_ROOT"
    run_doctor
    local item key tone detail advice failed=0
    for item in "${CHECKS[@]}"; do
        IFS='|' read -r key tone detail advice <<< "$item"
        case "$tone" in
            ok) mark='[OK]' ;;
            warn) mark='[!] ' ;;
            *) mark='[X] ' ;;
        esac
        local line="$mark $(check_name "$key")"
        [ -n "$detail" ] && line="$line -- $detail"
        printf '%s\n' "$line"
        local advice_text
        advice_text=$(check_advice_text "$advice")
        if [ -n "$advice_text" ]; then
            printf '     %s\n' "$(t doctor.advice advice="$advice_text")"
        fi
        [ "$tone" = "fail" ] && failed=$((failed + 1))
    done
    local problems
    problems=$(count_problems)
    if [ "$failed" -gt 0 ]; then
        printf '=> %s\n' "$(t doctor.has_problems count="$problems")"
        return 1
    fi
    printf '=> %s\n' "$(t doctor.all_ok)"
    return 0
}

run_state_dump() {
    # 打印环境状态（key=value，供排错与自动化测试解析）
    collect_state
    printf 'project_root=%s\n' "$PROJECT_ROOT"
    printf 'uv_path=%s\n' "$ST_UV_PATH"
    printf 'uv_version=%s\n' "$ST_UV_VERSION"
    printf 'venv_exists=%s\n' "$([ "$ST_VENV_EXISTS" = "1" ] && printf True || printf False)"
    printf 'python_exists=%s\n' "$([ "$ST_PYTHON_EXISTS" = "1" ] && printf True || printf False)"
    printf 'python_version=%s\n' "$ST_PYTHON_VERSION"
    printf 'framework_version=%s\n' "$ST_FRAMEWORK"
    printf 'has_lock=%s\n' "$([ "$ST_HAS_LOCK" = "1" ] && printf True || printf False)"
    printf 'has_requirements=%s\n' "$([ "$ST_HAS_REQUIREMENTS" = "1" ] && printf True || printf False)"
    printf 'git_available=%s\n' "$([ "$ST_GIT_AVAILABLE" = "1" ] && printf True || printf False)"
    printf 'git_branch=%s\n' "$ST_GIT_BRANCH"
    printf 'git_commit=%s\n' "$ST_GIT_COMMIT"
    printf 'git_dirty=%s\n' "$([ "$ST_GIT_DIRTY" = "1" ] && printf True || printf False)"
    printf 'venv_bytes=%s\n' "$ST_VENV_BYTES"
    printf 'platform=%s\n' "$ST_PLATFORM"
    printf 'missing_imports=%s\n' "$(printf '%s' "$ST_MISSING" | tr ' ' ',')"
    if env_ready; then
        printf 'env_ready=True\n'
    else
        printf 'env_ready=False\n'
    fi
}

run_preview() {
    # 渲染一次指定界面后退出（不读键盘）：供无终端环境验证与两平台一致性比对
    local target="$1"
    if [ "$target" = "menu" ]; then
        show_menu 1
    else
        show_page "$target"
    fi
}

run_action() {
    # 非交互执行单个动作（自动化与远程排错用，配合 --yes）：0 成功；1 失败
    ACTION_MODE=1
    case "$1" in
        doctor)
            run_text_check
            return $?
            ;;
        clean-temp)
            clean_work_dir
            add_log info "$(t cleanup.temp_done)"
            return 0
            ;;
        uninstall)
            run_uninstall
            # dry-run 不真正删除，以「流程是否走完」判定结果，否则会因 .venv 仍在而误报失败
            [ "$OPT_DRY_RUN" = "1" ] && return 0
            if [ -e "$APP_VENV" ]; then return 1; fi
            return 0
            ;;
        install) run_install ;;
        repair) run_install repair-only ;;
        upgrade) run_upgrade ;;
        *)
            add_log error "Unknown action: $1"
            return 2
            ;;
    esac
    collect_state
    if env_ready; then
        return 0
    fi
    return 1
}

print_usage() {
    # 用法文本同样来自共享文案表，保证脚本正文纯 ASCII
    t cli.usage
    printf '\n'
}

# ============================================================================
# 15. 入口
# ============================================================================

OPT_CHECK=0
OPT_STATE=0
OPT_PREVIEW=""
OPT_ACTION=""
OPT_DRY_RUN=0
OPT_YES=0
OPT_LANG=""
OPT_NO_COLOR=0
OPT_HELP=0
OPT_ARCHIVE=""
OPT_KEYS=""
ACTION_MODE=0
KEY_QUEUE=""
KEY_QUEUE_COUNT=0
USE_KEY_QUEUE=0
#: read_key 的结果载体（不能用 stdout 返回，见 read_key 注释）
READ_KEY_RESULT=""
RAW_KEY=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --check|-check) OPT_CHECK=1 ;;
        --state|-state) OPT_STATE=1 ;;
        --preview|-preview) shift; OPT_PREVIEW="${1:-}" ;;
        --preview=*) OPT_PREVIEW="${1#*=}" ;;
        --action|-action) shift; OPT_ACTION="${1:-}" ;;
        --action=*) OPT_ACTION="${1#*=}" ;;
        --archive|-archive) shift; OPT_ARCHIVE="${1:-}" ;;
        --archive=*) OPT_ARCHIVE="${1#*=}" ;;
        --keys|-keys) shift; OPT_KEYS="${1:-}" ;;
        --keys=*) OPT_KEYS="${1#*=}" ;;
        --dry-run|--dryrun|-dryrun) OPT_DRY_RUN=1 ;;
        --yes|-yes) OPT_YES=1 ;;
        --lang|-lang) shift; OPT_LANG="${1:-}" ;;
        --lang=*) OPT_LANG="${1#*=}" ;;
        --no-color|-no-color) OPT_NO_COLOR=1 ;;
        --help|-h) OPT_HELP=1 ;;
        *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
    esac
    shift
done

init_console
UI_LANG=$(detect_system_language)
load_text "$UI_LANG"

# --help 必须放在加载文案之后：用法文本取自共享文案表
if [ "$OPT_HELP" = "1" ]; then
    print_usage
    exit 0
fi

if [ "$OPT_STATE" = "1" ]; then
    run_state_dump
    exit 0
fi
if [ "$OPT_CHECK" = "1" ]; then
    run_text_check
    exit $?
fi
if [ -n "$OPT_PREVIEW" ]; then
    run_preview "$OPT_PREVIEW"
    exit 0
fi
if [ -n "$OPT_ACTION" ]; then
    run_action "$OPT_ACTION"
    exit $?
fi
if [ -n "$OPT_KEYS" ]; then
    # 脚本化按键驱动真实界面循环（无终端环境复现/回归测试）：--keys "8,2,1,q"
    set_key_queue "$OPT_KEYS"
fi
start_wizard
exit 0
