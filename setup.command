#!/bin/bash
# ============================================================================
# InstructionX 安装向导 —— macOS 双击入口
#
# 本文件只做「用系统自带 bash 运行 setup.sh」这一件事：真正的界面与逻辑在
# setup.sh（原生 TUI，不依赖 Python 与任何第三方模块）。Windows 对应入口是
# setup.bat（调用 setup.ps1，界面完全一致）。
#
# 双击运行注意事项（macOS Gatekeeper）：
#   首次运行若提示「无法打开，因为它来自身份不明的开发者」，请在
#   「系统设置 → 隐私与安全性」中点击「仍要打开」，或在终端执行：
#       chmod +x setup.command && xattr -d com.apple.quarantine setup.command
# ============================================================================
set -u

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
cd "$SCRIPT_DIR" || exit 1

if [ ! -f "$SCRIPT_DIR/setup.sh" ]; then
    printf '[X] 找不到 setup.sh（应与 setup.command 在同一目录）\n'
    read -rsn1 _ || true
    exit 1
fi

# 优先使用系统 bash（macOS 自带 3.2）；缺失时退回 sh
if [ -x /bin/bash ]; then
    /bin/bash "$SCRIPT_DIR/setup.sh" "$@"
else
    sh "$SCRIPT_DIR/setup.sh" "$@"
fi
CODE=$?

if [ "$CODE" -ne 0 ]; then
    printf '\n[X] 向导退出码: %s\n' "$CODE"
    printf '    详细过程见 logs/tui_setup.log\n'
    read -rsn1 _ || true
fi
exit "$CODE"
