#!/bin/bash
# select_next_task.sh - 查找依赖已满足的 OPEN 任务
# 用法: bash select_next_task.sh [--parallel] [任务板路径]
# 默认返回最高优先级的第一个可执行任务
# --parallel 返回所有无依赖的可并行任务
set -e

PARALLEL=false
TASK_FILE="planning/codex-tasks.md"

for arg in "$@"; do
    case "$arg" in
        --parallel) PARALLEL=true ;;
        *) TASK_FILE="$arg" ;;
    esac
done

if [ ! -f "$TASK_FILE" ]; then
    echo "ERROR: 任务板不存在: $TASK_FILE"
    exit 1
fi

# 提取所有 OPEN 任务：优先级|任务号|依赖
OPEN_TASKS=$(awk '
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
' "$TASK_FILE" | sort -t'|' -k1 -n)

if [ -z "$OPEN_TASKS" ]; then
    echo "NO_OPEN_TASKS"
    exit 0
fi

# 检查单个依赖任务是否已完成（DONE 或 VERIFIED）
check_dep_satisfied() {
    local dep_num="$1"
    local dep_status
    dep_status=$(awk -v id="$dep_num" '
        $0 ~ "## 任务 #0*" id ":" { found=1 }
        found && /\*\*状态\*\*:/ {
            gsub(/.*\*\*状态\*\*: */, ""); gsub(/ *$/, ""); print; exit
        }
    ' "$TASK_FILE")
    [ "$dep_status" = "DONE" ] || [ "$dep_status" = "VERIFIED" ]
}

# 检查一个任务的所有依赖是否满足
all_deps_satisfied() {
    local deps="$1"
    if [ "$deps" = "无" ] || [ -z "$deps" ]; then
        return 0
    fi
    local dep_num
    for dep_num in $(echo "$deps" | grep -oP '#\d+' | sed 's/#//'); do
        if ! check_dep_satisfied "$dep_num"; then
            return 1
        fi
    done
    return 0
}

# 过滤出依赖已满足的任务
RESULT=""
while IFS='|' read -r priority task_num deps; do
    if all_deps_satisfied "$deps"; then
        if [ "$PARALLEL" = true ]; then
            # --parallel 模式：只返回无依赖的任务
            if [ "$deps" = "无" ] || [ -z "$deps" ]; then
                RESULT="${RESULT}${priority}|${task_num}|${deps}\n"
            fi
        else
            # 默认模式：返回第一个可执行任务
            echo "${priority}|${task_num}|${deps}"
            exit 0
        fi
    fi
done <<< "$OPEN_TASKS"

if [ "$PARALLEL" = true ]; then
    if [ -n "$RESULT" ]; then
        echo -e "$RESULT" | sed '/^$/d'
    else
        echo "NO_PARALLEL_TASKS"
    fi
else
    echo "NO_EXECUTABLE_TASKS"
fi
