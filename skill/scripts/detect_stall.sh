#!/bin/bash
# detect_stall.sh - 检测 Codex 进程是否卡死
# 用法: bash detect_stall.sh <任务编号> <PID>
# 输出: SUCCESS | FAILED | ACTIVE | STALLED
# 使用状态文件持久化上次日志大小，支持增量比较
set -e

TASK_NUM="$1"
CODEX_PID="$2"
LOG_FILE=".dual-ai-collab/logs/task-${TASK_NUM}.log"
PID_FILE=".dual-ai-collab/logs/task-${TASK_NUM}.pid"
STATE_FILE=".dual-ai-collab/logs/task-${TASK_NUM}.stall-state"

if [ -z "$TASK_NUM" ] || [ -z "$CODEX_PID" ]; then
    echo "用法: bash detect_stall.sh <任务编号> <PID>"
    exit 1
fi

# 1. 进程是否还活着
if ! kill -0 "$CODEX_PID" 2>/dev/null; then
    # 进程已退出，检查退出码（通过 pid 文件标记或默认判定）
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

# 2. 最近 2 分钟内是否有代码文件被修改
RECENT_CHANGES=$(find . \( -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.jsx' \
    -o -name '*.tsx' -o -name '*.go' -o -name '*.rs' -o -name '*.java' \
    -o -name '*.c' -o -name '*.cpp' -o -name '*.vue' -o -name '*.svelte' \
    -o -name '*.html' -o -name '*.css' \) \
    -not -path './node_modules/*' -not -path './.git/*' \
    -mmin -2 2>/dev/null | head -5)

if [ -n "$RECENT_CHANGES" ]; then
    # 有文件变动，更新状态文件
    LOG_SIZE=$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)
    echo "$LOG_SIZE" > "$STATE_FILE"
    echo "ACTIVE"
    exit 0
fi

# 3. 日志文件是否还在增长（与上次记录比较）
LOG_SIZE=$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)
LAST_LOG_SIZE=0
[ -f "$STATE_FILE" ] && LAST_LOG_SIZE=$(cat "$STATE_FILE" 2>/dev/null || echo 0)

# 更新状态文件
echo "$LOG_SIZE" > "$STATE_FILE"

if [ "$LOG_SIZE" -gt "$LAST_LOG_SIZE" ] 2>/dev/null; then
    echo "ACTIVE"
else
    echo "STALLED"
fi
