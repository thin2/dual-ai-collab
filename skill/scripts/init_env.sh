#!/bin/bash
# init_env.sh - 初始化工作环境（薄封装）
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/task_manager.py" init "$@"
