#!/bin/bash
################################################################################
# 测试：统计报告输出
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/test_helpers.sh"

# 从 codex-auto-worker.sh 提取统计逻辑
count_by_status() {
    local status="$1"
    local task_file="$2"
    awk "/\\*\\*状态\\*\\*: ${status}|状态: ${status}/ {count++} END {print count+0}" "$task_file"
}

count_total() {
    local task_file="$1"
    awk '/## 任务 #/ {count++} END {print count+0}' "$task_file"
}

# ═══════════════════════════════════════════
# 测试开始
# ═══════════════════════════════════════════

describe "统计报告输出测试"

# --- 测试 1：总任务数 ---
setup_test_env
create_test_taskboard

it "应正确计算总任务数"
result=$(count_total "$TASK_BOARD")
assert_equals "5" "$result"

teardown_test_env

# --- 测试 2：OPEN 任务数 ---
setup_test_env
create_test_taskboard

it "应正确计算 OPEN 任务数"
result=$(count_by_status "OPEN" "$TASK_BOARD")
assert_equals "3" "$result"

teardown_test_env

# --- 测试 3：DONE 任务数 ---
setup_test_env
create_test_taskboard

it "应正确计算 DONE 任务数"
result=$(count_by_status "DONE" "$TASK_BOARD")
assert_equals "1" "$result"

teardown_test_env

# --- 测试 4：VERIFIED 任务数 ---
setup_test_env
create_test_taskboard

it "应正确计算 VERIFIED 任务数"
result=$(count_by_status "VERIFIED" "$TASK_BOARD")
assert_equals "1" "$result"

teardown_test_env

# --- 测试 5：IN_PROGRESS 初始为 0 ---
setup_test_env
create_test_taskboard

it "IN_PROGRESS 初始应为 0"
result=$(count_by_status "IN_PROGRESS" "$TASK_BOARD")
assert_equals "0" "$result"

teardown_test_env

# --- 测试 6：空任务板统计 ---
setup_test_env
create_empty_taskboard

it "空任务板总数应为 0"
result=$(count_total "$TASK_BOARD")
assert_equals "0" "$result"

teardown_test_env

# --- 测试 7：空任务板 OPEN 数 ---
setup_test_env
create_empty_taskboard

it "空任务板 OPEN 应为 0"
result=$(count_by_status "OPEN" "$TASK_BOARD")
assert_equals "0" "$result"

teardown_test_env

# --- 测试 8：全部完成任务板统计 ---
setup_test_env
create_all_done_taskboard

it "全部完成任务板 OPEN 应为 0"
result=$(count_by_status "OPEN" "$TASK_BOARD")
assert_equals "0" "$result"

teardown_test_env

# --- 测试 9：统计输出无脏值（单行纯数字） ---
setup_test_env
create_test_taskboard

it "统计输出应为单行纯数字（无脏值）"
result=$(count_by_status "OPEN" "$TASK_BOARD")
# 确保结果是纯数字
if [[ "$result" =~ ^[0-9]+$ ]]; then
    pass
else
    fail "输出不是纯数字: [$result]"
fi

teardown_test_env

# --- 测试 10：REJECTED 初始为 0 ---
setup_test_env
create_test_taskboard

it "REJECTED 初始应为 0"
result=$(count_by_status "REJECTED" "$TASK_BOARD")
assert_equals "0" "$result"

teardown_test_env

# 打印总结
print_summary
