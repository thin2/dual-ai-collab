#!/bin/bash
# check_checkpoint.sh - 检查并输出 checkpoint 状态
set -e

STATE_FILE=".dual-ai-collab/checkpoints/state.json"

if [ -f "$STATE_FILE" ]; then
    echo "CHECKPOINT_FOUND"
    cat "$STATE_FILE"
else
    echo "NO_CHECKPOINT"
fi
