#!/bin/bash
# select_next_task.sh - 查找依赖已满足的 OPEN 任务（薄封装）
# 用法: bash select_next_task.sh [--parallel] [任务板路径]
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/task_manager.py" select "$@"
