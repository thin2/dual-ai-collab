#!/bin/bash
# write_checkpoint.sh - 统一写入/更新 checkpoint 状态
# 用法: bash write_checkpoint.sh <phase> [key=value ...]
# 示例: bash write_checkpoint.sh developing current_task=3 total_tasks=8
set -e

PHASE="$1"
shift || true

CHECKPOINT_DIR=".dual-ai-collab/checkpoints"
STATE_FILE="$CHECKPOINT_DIR/state.json"

if [ -z "$PHASE" ]; then
    echo "用法: bash write_checkpoint.sh <phase> [key=value ...]"
    echo "phase: interview|spec_generated|tasks_created|user_approved|developing|auditing|fixing"
    exit 1
fi

mkdir -p "$CHECKPOINT_DIR"

# 如果已有 state.json，读取现有字段作为基础
if [ -f "$STATE_FILE" ]; then
    EXISTING=$(cat "$STATE_FILE")
else
    EXISTING="{}"
fi

# 构建 JSON：更新 phase 和 updated_at，保留其他字段
UPDATED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# 用 awk 构建 JSON（不依赖 jq）
NEW_JSON=$(echo "$EXISTING" | awk -v phase="$PHASE" -v ts="$UPDATED_AT" '
BEGIN { FS=OFS="" }
{
    gsub(/"phase" *: *"[^"]*"/, "\"phase\": \"" phase "\"")
    gsub(/"updated_at" *: *"[^"]*"/, "\"updated_at\": \"" ts "\"")
    if (index($0, "\"phase\"") == 0) {
        gsub(/\{/, "{ \"phase\": \"" phase "\", \"updated_at\": \"" ts "\", ")
    }
    if (index($0, "\"updated_at\"") == 0) {
        gsub(/"phase" *: *"[^"]*"/, "\"phase\": \"" phase "\", \"updated_at\": \"" ts "\"")
    }
    print
}')

# 如果是全新文件，构建完整 JSON
if [ "$EXISTING" = "{}" ]; then
    NEW_JSON="{\"phase\": \"$PHASE\", \"updated_at\": \"$UPDATED_AT\""
    for kv in "$@"; do
        key="${kv%%=*}"
        val="${kv#*=}"
        NEW_JSON="$NEW_JSON, \"$key\": \"$val\""
    done
    NEW_JSON="$NEW_JSON}"
else
    # 追加额外 key=value 参数
    for kv in "$@"; do
        key="${kv%%=*}"
        val="${kv#*=}"
        if echo "$NEW_JSON" | grep -q "\"$key\""; then
            NEW_JSON=$(echo "$NEW_JSON" | sed "s/\"$key\" *: *\"[^\"]*\"/\"$key\": \"$val\"/")
        else
            NEW_JSON=$(echo "$NEW_JSON" | sed "s/}$/, \"$key\": \"$val\"}/")
        fi
    done
fi

echo "$NEW_JSON" > "$STATE_FILE"
echo "CHECKPOINT: phase=$PHASE updated_at=$UPDATED_AT"
