#!/bin/bash
# summarize_progress.sh - 统计任务板进度
# 用法: bash summarize_progress.sh [任务板路径]
set -e

TASK_FILE="${1:-planning/codex-tasks.md}"

if [ ! -f "$TASK_FILE" ]; then
    echo "ERROR: 任务板不存在: $TASK_FILE"
    exit 1
fi

TOTAL=$(awk '/## 任务 #[0-9]+:/' "$TASK_FILE" | wc -l)
OPEN=$(awk '/\*\*状态\*\*: OPEN/ {c++} END {print c+0}' "$TASK_FILE")
IN_PROGRESS=$(awk '/\*\*状态\*\*: IN_PROGRESS/ {c++} END {print c+0}' "$TASK_FILE")
DONE=$(awk '/\*\*状态\*\*: DONE/ {c++} END {print c+0}' "$TASK_FILE")
VERIFIED=$(awk '/\*\*状态\*\*: VERIFIED/ {c++} END {print c+0}' "$TASK_FILE")
REJECTED=$(awk '/\*\*状态\*\*: REJECTED/ {c++} END {print c+0}' "$TASK_FILE")

COMPLETED=$((DONE + VERIFIED))
COMPLETION_RATE=$(awk "BEGIN { printf \"%.1f\", ($COMPLETED / ($TOTAL > 0 ? $TOTAL : 1)) * 100 }")

AUDITED=$((VERIFIED + REJECTED))
AUDIT_RATE=$(awk "BEGIN { printf \"%.1f\", ($VERIFIED / ($AUDITED > 0 ? $AUDITED : 1)) * 100 }")

echo "总任务: $TOTAL"
echo "OPEN: $OPEN"
echo "IN_PROGRESS: $IN_PROGRESS"
echo "DONE: $DONE"
echo "VERIFIED: $VERIFIED"
echo "REJECTED: $REJECTED"
echo "完成率: ${COMPLETION_RATE}%"
echo "审计通过率: ${AUDIT_RATE}%"
