#!/bin/bash
# update_task_status.sh - 更新任务板中指定任务的状态
# 用法: bash update_task_status.sh <任务编号> <旧状态> <新状态> [任务板路径]
set -e

TASK_NUM="$1"
OLD_STATUS="$2"
NEW_STATUS="$3"
TASK_FILE="${4:-planning/codex-tasks.md}"

if [ -z "$TASK_NUM" ] || [ -z "$OLD_STATUS" ] || [ -z "$NEW_STATUS" ]; then
    echo "用法: bash update_task_status.sh <任务编号> <旧状态> <新状态> [任务板路径]"
    echo "示例: bash update_task_status.sh 001 OPEN IN_PROGRESS"
    exit 1
fi

if [ ! -f "$TASK_FILE" ]; then
    echo "ERROR: 任务板不存在: $TASK_FILE"
    exit 1
fi

sed -i "/## 任务 #${TASK_NUM}:/,/^---$/ s/\*\*状态\*\*: ${OLD_STATUS}/\*\*状态\*\*: ${NEW_STATUS}/" "$TASK_FILE"
echo "OK: 任务 #${TASK_NUM} ${OLD_STATUS} -> ${NEW_STATUS}"
