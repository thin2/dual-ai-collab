#!/bin/bash
# select_next_task.sh - 查找最高优先级的、依赖已满足的 OPEN 任务
# 用法: bash select_next_task.sh [任务板路径]
set -e

TASK_FILE="${1:-planning/codex-tasks.md}"

if [ ! -f "$TASK_FILE" ]; then
    echo "ERROR: 任务板不存在: $TASK_FILE"
    exit 1
fi

# 输出所有 OPEN 任务及其优先级和依赖，按优先级排序
awk '
    /## 任务 #[0-9]+:/ {
        match($0, /#([0-9]+):/, arr); task_num = arr[1]
        in_task = 1; is_open = 0; priority = 9; deps = "无"
    }
    in_task && /\*\*状态\*\*: OPEN/ { is_open = 1 }
    in_task && /\*\*优先级\*\*: P([0-9])/ { match($0, /P([0-9])/, p); priority = p[1] }
    in_task && /\*\*依赖任务\*\*:/ { gsub(/.*\*\*依赖任务\*\*: */, ""); deps = $0 }
    in_task && /^---$/ {
        if (is_open) printf "%d|%s|%s\n", priority, task_num, deps
        in_task = 0
    }
' "$TASK_FILE" | sort -t'|' -k1 -n
