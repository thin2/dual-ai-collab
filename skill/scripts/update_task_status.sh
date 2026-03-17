#!/bin/bash
# update_task_status.sh - 更新任务板中指定任务的状态
# 用法: bash update_task_status.sh <任务编号> <新状态> [任务板路径]
# 脚本自动检测当前状态，无需手动指定旧状态
set -e

TASK_NUM="$1"
NEW_STATUS="$2"
TASK_FILE="${3:-planning/codex-tasks.md}"

if [ -z "$TASK_NUM" ] || [ -z "$NEW_STATUS" ]; then
    echo "用法: bash update_task_status.sh <任务编号> <新状态> [任务板路径]"
    echo "示例: bash update_task_status.sh 001 IN_PROGRESS"
    exit 1
fi

if [ ! -f "$TASK_FILE" ]; then
    echo "ERROR: 任务板不存在: $TASK_FILE"
    exit 1
fi

# 自动检测当前状态
OLD_STATUS=$(awk -v id="$TASK_NUM" '
    $0 ~ "## 任务 #0*" id ":" { found=1 }
    found && /\*\*状态\*\*:/ {
        gsub(/.*\*\*状态\*\*: */, ""); gsub(/ *$/, ""); print; exit
    }
' "$TASK_FILE")

if [ -z "$OLD_STATUS" ]; then
    echo "ERROR: 未找到任务 #${TASK_NUM}"
    exit 1
fi

if [ "$OLD_STATUS" = "$NEW_STATUS" ]; then
    echo "SKIP: 任务 #${TASK_NUM} 已经是 ${NEW_STATUS}"
    exit 0
fi

sed -i "/## 任务 #0*${TASK_NUM}:/,/^---$/ s/\*\*状态\*\*: ${OLD_STATUS}/\*\*状态\*\*: ${NEW_STATUS}/" "$TASK_FILE"
echo "OK: 任务 #${TASK_NUM} ${OLD_STATUS} -> ${NEW_STATUS}"
