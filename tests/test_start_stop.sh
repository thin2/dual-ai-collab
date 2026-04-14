#!/bin/bash
################################################################################
# 测试：Skill 文件验证和环境初始化
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/test_helpers.sh"

# ═══════════════════════════════════════════
# 测试开始
# ═══════════════════════════════════════════

describe "Skill 文件验证和环境初始化测试"

# --- 测试 1：Skill 文件存在 ---
it "skill/dual-ai-collab.md 应存在"
assert_file_exists "$PROJECT_DIR/skill/dual-ai-collab.md"

# --- 测试 2：Skill 文件包含 description ---
it "Skill 文件应包含 description 字段"
result=$(grep -c "description:" "$PROJECT_DIR/skill/dual-ai-collab.md" || true)
if [ "$result" -ge 1 ]; then
    pass
else
    fail "未找到 description 字段"
fi

# --- 测试 3：Skill 文件包含触发词 ---
it "Skill 文件应包含触发词定义"
result=$(cat "$PROJECT_DIR/skill/dual-ai-collab.md")
assert_contains "$result" "双 AI 协作"

# --- 测试 4：planning 目录可自动创建 ---
setup_test_env

it "planning 目录应能自动创建"
PLAN_DIR="$TEST_DIR/planning/specs"
mkdir -p "$PLAN_DIR"
if [ -d "$PLAN_DIR" ]; then
    pass
else
    fail "目录创建失败"
fi

teardown_test_env

# --- 测试 4b：init_env.sh 应补齐流程依赖目录 ---
setup_test_env

it "init_env.sh 应创建 designs 和 progress-reports 目录"
cd "$TEST_DIR"
bash "$PROJECT_DIR/skill/scripts/init_env.sh" >/dev/null
if [ -d "$TEST_DIR/.dual-ai-collab/designs" ] && [ -d "$TEST_DIR/planning/progress-reports" ]; then
    pass
else
    fail "未创建 .dual-ai-collab/designs 或 planning/progress-reports"
fi

teardown_test_env

# --- 测试 5：日志目录可自动创建 ---
setup_test_env

it "日志目录应能自动创建"
LOG_DIR="$TEST_DIR/.dual-ai-collab/logs"
mkdir -p "$LOG_DIR"
if [ -d "$LOG_DIR" ]; then
    pass
else
    fail "目录创建失败"
fi

teardown_test_env

# --- 测试 6：PID 文件创建和清理 ---
setup_test_env

it "PID 文件应能正确创建和删除"
PID_FILE="$TEST_DIR/.dual-ai-collab/logs/codex-worker.pid"
mkdir -p "$(dirname "$PID_FILE")"
echo "12345" > "$PID_FILE"
assert_file_exists "$PID_FILE"

it "PID 文件删除后不应残留"
rm -f "$PID_FILE"
if [ ! -f "$PID_FILE" ]; then
    pass
else
    fail "PID 文件删除失败"
fi

teardown_test_env

# --- 测试 8：停止不存在的 worker 应正常退出 ---
setup_test_env

it "停止不存在的 worker 应正常退出"
LOG_DIR="$TEST_DIR/.dual-ai-collab/logs"
mkdir -p "$LOG_DIR"
result=$(cd "$TEST_DIR" && LOG_DIR="$LOG_DIR" bash -c '
    if [ ! -f "$LOG_DIR/codex-worker.pid" ]; then
        echo "没有找到运行中的 worker"
        exit 0
    fi
' 2>&1)
exit_code=$?
assert_exit_code "0" "$exit_code"

teardown_test_env

# --- 测试 9：Skill 文件包含任务板格式定义 ---
it "Skill 文件应包含任务板或真相源说明"
result=$(cat "$PROJECT_DIR/skill/dual-ai-collab.md")
if echo "$result" | grep -qE "tasks.json|codex-tasks.md"; then
    pass
else
    fail "未找到任务板或真相源说明"
fi

# --- 测试 10：references 目录存在 ---
it "skill/references/ 目录应存在"
if [ -d "$PROJECT_DIR/skill/references" ]; then
    pass
else
    fail "references 目录不存在"
fi

# --- 测试 10b：run_task.sh 应存在 ---
it "run_task.sh 应存在"
assert_file_exists "$PROJECT_DIR/skill/scripts/run_task.sh"

# --- 测试 10c：verify_task.sh 应存在 ---
it "verify_task.sh 应存在"
assert_file_exists "$PROJECT_DIR/skill/scripts/verify_task.sh"

# --- 测试 11：不应存在已废弃的脚本文件 ---
it "不应存在已废弃的 scripts 目录"
if [ ! -d "$PROJECT_DIR/scripts" ]; then
    pass
else
    fail "scripts 目录仍然存在"
fi

# 打印总结
print_summary
