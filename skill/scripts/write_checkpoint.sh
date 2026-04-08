#!/bin/bash
# write_checkpoint.sh - 统一写入/更新 checkpoint 状态（薄封装）
# 用法: bash write_checkpoint.sh <phase> [key=value ...]
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/task_manager.py" checkpoint-write "$@"
