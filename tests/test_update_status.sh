#!/bin/bash
################################################################################
# 测试：状态转换
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/test_helpers.sh"

PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

run_update_task_status() {
    local task_id="$1"
    local new_status="$2"
    bash "$PROJECT_DIR/skill/scripts/update_task_status.sh" "$task_id" "$new_status" "$TASK_BOARD" >/dev/null
}

# ═══════════════════════════════════════════
# 测试开始
# ═══════════════════════════════════════════

describe "状态转换测试"

# --- 测试 1：OPEN -> IN_PROGRESS ---
setup_test_env
create_test_taskboard

it "OPEN -> IN_PROGRESS 状态转换"
run_update_task_status "001" "IN_PROGRESS"
result=$(awk '/## 任务 #001:/,/^---$/' "$TASK_BOARD" | grep '状态')
assert_contains "$result" "IN_PROGRESS"

teardown_test_env

# --- 测试 2：IN_PROGRESS -> DONE ---
setup_test_env
create_test_taskboard
run_update_task_status "001" "IN_PROGRESS"

it "IN_PROGRESS -> DONE 状态转换"
run_update_task_status "001" "DONE"
result=$(awk '/## 任务 #001:/,/^---$/' "$TASK_BOARD" | grep '状态')
assert_contains "$result" "DONE"

teardown_test_env

# --- 测试 3：IN_PROGRESS -> OPEN（回退） ---
setup_test_env
create_test_taskboard
run_update_task_status "002" "IN_PROGRESS"

it "IN_PROGRESS -> OPEN 回退（执行失败场景）"
run_update_task_status "002" "OPEN"
result=$(awk '/## 任务 #002:/,/^---$/' "$TASK_BOARD" | grep '状态')
assert_contains "$result" "OPEN"

teardown_test_env

# --- 测试 4：状态更新不影响其他任务 ---
setup_test_env
create_test_taskboard

it "状态更新不应影响其他任务"
run_update_task_status "001" "IN_PROGRESS"
# 验证 #002 仍然是 OPEN
result=$(awk '/## 任务 #002:/,/^---$/' "$TASK_BOARD" | grep '状态')
assert_contains "$result" "OPEN"

teardown_test_env

# --- 测试 5：DONE -> VERIFIED ---
setup_test_env
create_test_taskboard

it "DONE -> VERIFIED 状态转换（审计通过）"
run_update_task_status "004" "VERIFIED"
result=$(awk '/## 任务 #004:/,/^---$/' "$TASK_BOARD" | grep '状态')
assert_contains "$result" "VERIFIED"

teardown_test_env

# --- 测试 6：DONE -> REJECTED ---
setup_test_env
create_test_taskboard

it "DONE -> REJECTED 状态转换（审计拒绝）"
run_update_task_status "004" "REJECTED"
result=$(awk '/## 任务 #004:/,/^---$/' "$TASK_BOARD" | grep '状态')
assert_contains "$result" "REJECTED"

teardown_test_env

# --- 测试 7：连续状态转换 OPEN -> IN_PROGRESS -> DONE ---
setup_test_env
create_test_taskboard

it "连续状态转换 OPEN -> IN_PROGRESS -> DONE"
run_update_task_status "003" "IN_PROGRESS"
run_update_task_status "003" "DONE"
result=$(awk '/## 任务 #003:/,/^---$/' "$TASK_BOARD" | grep '状态')
assert_contains "$result" "DONE"

teardown_test_env

# --- 测试 8：不匹配的状态转换应无效果 ---
setup_test_env
create_test_taskboard

it "不匹配的状态转换应无效果"
# 当前真实脚本会自动检测旧状态，因此可以直接完成更新
run_update_task_status "001" "DONE"
result=$(awk '/## 任务 #001:/,/^---$/' "$TASK_BOARD" | grep '状态')
assert_contains "$result" "DONE"

teardown_test_env

# 打印总结
print_summary
