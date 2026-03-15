#!/bin/bash
# detect_stall.sh - 检测 Codex 进程是否卡死
# 用法: bash detect_stall.sh <PID> <任务编号>
set -e

CODEX_PID="$1"
TASK_NUM="$2"
LOG_FILE=".dual-ai-collab/logs/task-${TASK_NUM}.log"
PID_FILE=".dual-ai-collab/logs/task-${TASK_NUM}.pid"

if [ -z "$CODEX_PID" ] || [ -z "$TASK_NUM" ]; then
    echo "用法: bash detect_stall.sh <PID> <任务编号>"
    exit 1
fi

# 1. 进程是否还活着
if ! kill -0 "$CODEX_PID" 2>/dev/null; then
    wait "$CODEX_PID" 2>/dev/null
    EXIT_CODE=$?
    [ $EXIT_CODE -eq 0 ] && echo "SUCCESS" || echo "FAILED (exit code: $EXIT_CODE)"
    exit 0
fi

# 2. 最近 2 分钟内是否有代码文件被修改
RECENT_CHANGES=$(find . \( -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.jsx' \
    -o -name '*.tsx' -o -name '*.go' -o -name '*.rs' -o -name '*.java' \
    -o -name '*.c' -o -name '*.cpp' -o -name '*.vue' -o -name '*.svelte' \) \
    -not -path './node_modules/*' -not -path './.git/*' \
    -newer "$PID_FILE" 2>/dev/null | head -5)

# 3. 日志文件是否还在增长
LOG_SIZE=$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)

if [ -n "$RECENT_CHANGES" ]; then
    echo "ACTIVE - 文件有变动"
    touch "$PID_FILE"
elif [ "$LOG_SIZE" -gt "${LAST_LOG_SIZE:-0}" ]; then
    echo "ACTIVE - 日志在增长 (${LOG_SIZE} bytes)"
else
    echo "STALLED"
fi
