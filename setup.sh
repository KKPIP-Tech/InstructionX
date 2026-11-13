#!/bin/bash
# InstructionX native Setup launcher. No TUI is implemented in this file.
set -u
PROJECT_ROOT=$(cd "$(dirname "$0")" && pwd)
SYSTEM=$(uname -s)
MACHINE=$(uname -m)
case "$SYSTEM/$MACHINE" in
    MINGW64_NT-*/x86_64|MSYS_NT-*/x86_64|CYGWIN_NT-*/x86_64)
        ASSET_NAME="instructionx-setup-windows-x86_64.exe" ;;
    MINGW64_NT-*/aarch64|MINGW64_NT-*/arm64|MSYS_NT-*/aarch64|MSYS_NT-*/arm64)
        ASSET_NAME="instructionx-setup-windows-aarch64.exe" ;;
    Darwin/x86_64) ASSET_NAME="instructionx-setup-macos-x86_64" ;;
    Darwin/arm64|Darwin/aarch64) ASSET_NAME="instructionx-setup-macos-aarch64" ;;
    Linux/x86_64|Linux/amd64) ASSET_NAME="instructionx-setup-linux-x86_64" ;;
    Linux/aarch64|Linux/arm64) ASSET_NAME="instructionx-setup-linux-aarch64" ;;
    *) printf 'Unsupported platform: %s/%s\n' "$SYSTEM" "$MACHINE" >&2; exit 1 ;;
esac
NATIVE="$PROJECT_ROOT/tools/setup/$ASSET_NAME"
if [ ! -f "$NATIVE" ]; then
    printf 'Bundled native Setup is missing: tools/setup/%s\n' "$ASSET_NAME" >&2
    printf 'Restore the original Release archive.\n' >&2
    exit 1
fi
if [ ! -x "$NATIVE" ]; then
    chmod +x "$NATIVE"
fi
exec "$NATIVE" "$@"
