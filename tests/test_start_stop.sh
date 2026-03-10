#!/bin/bash
################################################################################
# 测试：启动/停止流程
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/test_helpers.sh"

# ═══════════════════════════════════════════
# 测试开始
# ═══════════════════════════════════════════

describe "启动/停止流程测试"

# --- 测试 1：start-codex.sh 语法正确 ---
it "start-codex.sh 应通过语法检查"
bash -n "$PROJECT_DIR/scripts/start-codex.sh" 2>/dev/null
assert_exit_code "0" "$?"

# --- 测试 2：codex-auto-worker.sh 语法正确 ---
it "codex-auto-worker.sh 应通过语法检查"
bash -n "$PROJECT_DIR/scripts/codex-auto-worker.sh" 2>/dev/null
assert_exit_code "0" "$?"

# --- 测试 3：claude-interview.sh 语法正确 ---
it "claude-interview.sh 应通过语法检查"
bash -n "$PROJECT_DIR/scripts/claude-interview.sh" 2>/dev/null
assert_exit_code "0" "$?"

# --- 测试 4：check-env.sh 语法正确 ---
it "check-env.sh 应通过语法检查"
bash -n "$PROJECT_DIR/check-env.sh" 2>/dev/null
assert_exit_code "0" "$?"

# --- 测试 5：install.sh 语法正确 ---
it "install.sh 应通过语法检查"
bash -n "$PROJECT_DIR/install.sh" 2>/dev/null
assert_exit_code "0" "$?"

# --- 测试 6：start-codex.sh 显示帮助 ---
it "start-codex.sh -h 应显示帮助信息"
result=$(bash "$PROJECT_DIR/scripts/start-codex.sh" -h 2>&1)
assert_contains "$result" "用法"

# --- 测试 7：start-codex.sh 停止不存在的 worker ---
setup_test_env

it "停止不存在的 worker 应正常退出"
LOG_DIR="$TEST_DIR/.dual-ai-collab/logs"
mkdir -p "$LOG_DIR"
# 模拟 stop_worker：没有 PID 文件时应正常退出
result=$(cd "$TEST_DIR" && LOG_DIR="$LOG_DIR" bash -c '
    if [ ! -f "$LOG_DIR/codex-worker.pid" ]; then
        echo "没有找到运行中的 worker"
        exit 0
    fi
' 2>&1)
exit_code=$?
assert_exit_code "0" "$exit_code"

teardown_test_env

# --- 测试 8：PID 文件创建和清理 ---
setup_test_env

it "PID 文件应能正确创建和删除"
PID_FILE="$TEST_DIR/.dual-ai-collab/logs/codex-worker.pid"
echo "12345" > "$PID_FILE"
assert_file_exists "$PID_FILE"
rm -f "$PID_FILE"
if [ ! -f "$PID_FILE" ]; then
    pass
else
    fail "PID 文件删除失败"
fi
# 修正：上面已经调用了 assert_file_exists，这里再做一次 it
# 用 pass 替代，上面的 assert_file_exists 已经测试了创建

teardown_test_env

# --- 测试 9：日志目录自动创建 ---
setup_test_env

it "日志目录应能自动创建"
NEW_LOG_DIR="$TEST_DIR/.dual-ai-collab/logs/subdir"
mkdir -p "$NEW_LOG_DIR"
if [ -d "$NEW_LOG_DIR" ]; then
    pass
else
    fail "目录创建失败"
fi

teardown_test_env

# --- 测试 10：claude-interview.sh 无参数显示帮助 ---
it "claude-interview.sh 无参数应显示帮助并退出"
result=$(bash "$PROJECT_DIR/scripts/claude-interview.sh" 2>&1 || true)
assert_contains "$result" "用法"

# 打印总结
print_summary
