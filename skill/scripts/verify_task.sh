#!/bin/bash
# verify_task.sh - 提取并执行任务验收标准中的可执行命令（薄封装）
# 用法:
#   bash verify_task.sh extract <任务编号> [任务板路径]
#   bash verify_task.sh run <任务编号> [任务板路径] [--workdir DIR]
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTION="${1:-}"

case "$ACTION" in
    extract)
        shift
        exec python3 "$SCRIPT_DIR/verify_task.py" extract "$@"
        ;;
    run)
        shift
        exec python3 "$SCRIPT_DIR/verify_task.py" run "$@"
        ;;
    *)
        echo "用法: bash verify_task.sh <extract|run> ..." >&2
        exit 1
        ;;
esac
