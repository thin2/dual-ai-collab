#!/bin/bash
# run_task.sh - 启动/查询/终止任务运行（薄封装）
# 用法:
#   bash run_task.sh start <任务编号> <提示词> [--backend direct|plugin] [--workdir DIR]
#   bash run_task.sh status <任务编号>
#   bash run_task.sh stop <任务编号>
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTION="${1:-}"

case "$ACTION" in
    start)
        shift
        exec python3 "$SCRIPT_DIR/run_task.py" start "$@"
        ;;
    status)
        shift
        exec python3 "$SCRIPT_DIR/run_task.py" status "$@"
        ;;
    stop)
        shift
        exec python3 "$SCRIPT_DIR/run_task.py" stop "$@"
        ;;
    *)
        echo "用法: bash run_task.sh <start|status|stop> ..." >&2
        exit 1
        ;;
esac
