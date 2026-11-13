#!/bin/bash
# InstructionX native Setup double-click launcher.
set -u
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
if [ -x /bin/bash ]; then
    exec /bin/bash "$SCRIPT_DIR/setup.sh" "$@"
fi
exec sh "$SCRIPT_DIR/setup.sh" "$@"
