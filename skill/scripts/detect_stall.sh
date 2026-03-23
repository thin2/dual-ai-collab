#!/bin/bash
# detect_stall.sh - 检测 Codex 进程是否卡死
# 用法: bash detect_stall.sh <任务编号> <PID> [任务板路径]
# 输出: SUCCESS | FAILED | ACTIVE | STALLED
# 使用状态文件持久化上次日志大小，支持增量比较
set -e

TASK_NUM="$1"
CODEX_PID="$2"
TASK_FILE="${3:-planning/codex-tasks.md}"
LOG_FILE=".dual-ai-collab/logs/task-${TASK_NUM}.log"
STATE_FILE=".dual-ai-collab/logs/task-${TASK_NUM}.stall-state"

if [ -z "$TASK_NUM" ] || [ -z "$CODEX_PID" ]; then
    echo "用法: bash detect_stall.sh <任务编号> <PID> [任务板路径]"
    exit 1
fi

resolve_stall_minutes() {
    if [ ! -f "$TASK_FILE" ]; then
        echo 3
        return
    fi

    local custom_minutes
    custom_minutes=$(awk -v id="$TASK_NUM" '
        $0 ~ "## 任务 #0*" id ":" { found=1 }
        found && /\*\*卡死阈值\*\*:/ {
            line = $0
            gsub(/.*\*\*卡死阈值\*\*: */, "", line)
            gsub(/[^0-9].*$/, "", line)
            if (line != "") print line
            exit
        }
        found && /^---$/ { exit }
    ' "$TASK_FILE")
    if [ -n "$custom_minutes" ]; then
        echo "$custom_minutes"
        return
    fi

    local execution_level
    execution_level=$(awk -v id="$TASK_NUM" '
        $0 ~ "## 任务 #0*" id ":" { found=1 }
        found && /\*\*执行级别\*\*:/ {
            line = $0
            gsub(/.*\*\*执行级别\*\*: */, "", line)
            gsub(/ *$/, "", line)
            print line
            exit
        }
        found && /^---$/ { exit }
    ' "$TASK_FILE")

    case "$execution_level" in
        heavy) echo 10 ;;
        normal) echo 5 ;;
        quick|"") echo 3 ;;
        *) echo 3 ;;
    esac
}

STALL_MINUTES=$(resolve_stall_minutes)

if ! kill -0 "$CODEX_PID" 2>/dev/null; then
    EXIT_FILE=".dual-ai-collab/logs/task-${TASK_NUM}.exit"
    if [ -f "$EXIT_FILE" ]; then
        EXIT_CODE=$(cat "$EXIT_FILE")
    else
        EXIT_CODE=1
    fi
    rm -f "$STATE_FILE"
    [ "$EXIT_CODE" -eq 0 ] 2>/dev/null && echo "SUCCESS" || echo "FAILED (exit code: ${EXIT_CODE})"
    exit 0
fi

RECENT_CHANGES=$(find . \( -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.jsx' \
    -o -name '*.tsx' -o -name '*.go' -o -name '*.rs' -o -name '*.java' \
    -o -name '*.c' -o -name '*.cpp' -o -name '*.vue' -o -name '*.svelte' \
    -o -name '*.html' -o -name '*.css' \) \
    -not -path './node_modules/*' -not -path './.git/*' \
    -mmin "-${STALL_MINUTES}" 2>/dev/null | head -5)

if [ -n "$RECENT_CHANGES" ]; then
    LOG_SIZE=$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)
    printf '%s\n' "$LOG_SIZE" > "$STATE_FILE"
    echo "ACTIVE"
    exit 0
fi

LOG_SIZE=$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)
LAST_LOG_SIZE=0
[ -f "$STATE_FILE" ] && LAST_LOG_SIZE=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
printf '%s\n' "$LOG_SIZE" > "$STATE_FILE"

if [ "$LOG_SIZE" -gt "$LAST_LOG_SIZE" ] 2>/dev/null; then
    echo "ACTIVE"
else
    echo "STALLED"
fi
