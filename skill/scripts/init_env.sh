#!/bin/bash
# init_env.sh - 初始化工作环境
set -e

mkdir -p planning/specs
mkdir -p planning/audit-reports
mkdir -p .dual-ai-collab/logs
mkdir -p .dual-ai-collab/checkpoints

echo "ENV_READY"
