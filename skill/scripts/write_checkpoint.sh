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

case "$PHASE" in
    interview|spec_generated|tasks_created|user_approved|developing|auditing|fixing) ;;
    *)
        echo "ERROR: 无效的 phase 值: $PHASE"
        echo "允许: interview|spec_generated|tasks_created|user_approved|developing|auditing|fixing"
        exit 1
        ;;
esac

mkdir -p "$CHECKPOINT_DIR"

UPDATED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

python3 - "$STATE_FILE" "$PHASE" "$UPDATED_AT" "$@" <<'PY'
import json
import re
import shutil
import sys
from pathlib import Path

state_file = Path(sys.argv[1])
phase = sys.argv[2]
updated_at = sys.argv[3]
extra_args = sys.argv[4:]

data = {}
if state_file.exists():
    try:
        with state_file.open("r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            data.update(loaded)
    except json.JSONDecodeError:
        backup = state_file.with_suffix(state_file.suffix + ".corrupted")
        shutil.copy2(state_file, backup)
        print(
            f"WARNING: 现有 checkpoint 非法，已备份到 {backup.name}，将重新生成。",
            file=sys.stderr,
        )

allowed = {
    "spec_file",
    "task_file",
    "current_task",
    "total_tasks",
    "completed_tasks",
    "fix_round",
}

for item in extra_args:
    if "=" not in item:
        print(f"ERROR: 非法参数 '{item}'，必须使用 key=value 格式。", file=sys.stderr)
        sys.exit(1)
    key, value = item.split("=", 1)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        print(f"ERROR: 非法字段名 '{key}'。", file=sys.stderr)
        sys.exit(1)
    if key not in allowed:
        print(
            f"WARNING: 未知字段 '{key}' 被忽略（允许: {', '.join(sorted(allowed))}）",
            file=sys.stderr,
        )
        continue
    data[key] = value

data["phase"] = phase
data["updated_at"] = updated_at

ordered = {"phase": data["phase"], "updated_at": data["updated_at"]}
for key in ("spec_file", "task_file", "current_task", "total_tasks", "completed_tasks", "fix_round"):
    value = data.get(key)
    if value not in (None, ""):
        ordered[key] = value

with state_file.open("w", encoding="utf-8") as f:
    json.dump(ordered, f, ensure_ascii=False, indent=2)
    f.write("\n")
PY

echo "CHECKPOINT: phase=$PHASE updated_at=$UPDATED_AT"
