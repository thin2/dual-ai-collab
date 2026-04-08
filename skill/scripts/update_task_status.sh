#!/bin/bash
# update_task_status.sh - 更新任务板中指定任务的状态（薄封装）
# 用法: bash update_task_status.sh <任务编号> <新状态> [任务板路径]
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/task_manager.py" update "$@"
