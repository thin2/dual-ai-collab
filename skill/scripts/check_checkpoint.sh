#!/bin/bash
# check_checkpoint.sh - 检查并输出 checkpoint 状态（薄封装）
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/task_manager.py" checkpoint-check "$@"
