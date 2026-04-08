#!/bin/bash
# summarize_progress.sh - 统计任务板进度（薄封装）
# 用法: bash summarize_progress.sh [任务板路径]
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/task_manager.py" summary "$@"
