#!/bin/bash
# detect_stall.sh - 检测 Codex 进程是否卡死（薄封装）
# 用法: bash detect_stall.sh <任务编号> <PID> [任务板路径]
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/task_manager.py" detect "$@"
