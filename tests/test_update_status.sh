#!/bin/bash
################################################################################
# 测试：状态转换
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/test_helpers.sh"

# 从 codex-auto-worker.sh 中提取 update_task_status 函数
update_task_status() {
    local task_id="$1"
    local old_status="$2"
    local new_status="$3"
    local task_file="$4"

    sed -i "/## 任务 #${task_id}:/,/^---$/ s/\*\*状态\*\*: ${old_status}/\*\*状态\*\*: ${new_status}/" "$task_file"
}

# ═══════════════════════════════════════════
# 测试开始
# ═══════════════════════════════════════════

describe "状态转换测试"

# --- 测试 1：OPEN -> IN_PROGRESS ---
setup_test_env
create_test_taskboard

it "OPEN -> IN_PROGRESS 状态转换"
update_task_status "001" "OPEN" "IN_PROGRESS" "$TASK_BOARD"
result=$(awk '/## 任务 #001:/,/^---$/' "$TASK_BOARD" | grep '状态')
assert_contains "$result" "IN_PROGRESS"

teardown_test_env

# --- 测试 2：IN_PROGRESS -> DONE ---
setup_test_env
create_test_taskboard
update_task_status "001" "OPEN" "IN_PROGRESS" "$TASK_BOARD"

it "IN_PROGRESS -> DONE 状态转换"
update_task_status "001" "IN_PROGRESS" "DONE" "$TASK_BOARD"
result=$(awk '/## 任务 #001:/,/^---$/' "$TASK_BOARD" | grep '状态')
assert_contains "$result" "DONE"

teardown_test_env

# --- 测试 3：IN_PROGRESS -> OPEN（回退） ---
setup_test_env
create_test_taskboard
update_task_status "002" "OPEN" "IN_PROGRESS" "$TASK_BOARD"

it "IN_PROGRESS -> OPEN 回退（执行失败场景）"
update_task_status "002" "IN_PROGRESS" "OPEN" "$TASK_BOARD"
result=$(awk '/## 任务 #002:/,/^---$/' "$TASK_BOARD" | grep '状态')
assert_contains "$result" "OPEN"

teardown_test_env

# --- 测试 4：状态更新不影响其他任务 ---
setup_test_env
create_test_taskboard

it "状态更新不应影响其他任务"
update_task_status "001" "OPEN" "IN_PROGRESS" "$TASK_BOARD"
# 验证 #002 仍然是 OPEN
result=$(awk '/## 任务 #002:/,/^---$/' "$TASK_BOARD" | grep '状态')
assert_contains "$result" "OPEN"

teardown_test_env

# --- 测试 5：DONE -> VERIFIED ---
setup_test_env
create_test_taskboard

it "DONE -> VERIFIED 状态转换（审计通过）"
update_task_status "004" "DONE" "VERIFIED" "$TASK_BOARD"
result=$(awk '/## 任务 #004:/,/^---$/' "$TASK_BOARD" | grep '状态')
assert_contains "$result" "VERIFIED"

teardown_test_env

# --- 测试 6：DONE -> REJECTED ---
setup_test_env
create_test_taskboard

it "DONE -> REJECTED 状态转换（审计拒绝）"
update_task_status "004" "DONE" "REJECTED" "$TASK_BOARD"
result=$(awk '/## 任务 #004:/,/^---$/' "$TASK_BOARD" | grep '状态')
assert_contains "$result" "REJECTED"

teardown_test_env

# --- 测试 7：连续状态转换 OPEN -> IN_PROGRESS -> DONE ---
setup_test_env
create_test_taskboard

it "连续状态转换 OPEN -> IN_PROGRESS -> DONE"
update_task_status "003" "OPEN" "IN_PROGRESS" "$TASK_BOARD"
update_task_status "003" "IN_PROGRESS" "DONE" "$TASK_BOARD"
result=$(awk '/## 任务 #003:/,/^---$/' "$TASK_BOARD" | grep '状态')
assert_contains "$result" "DONE"

teardown_test_env

# --- 测试 8：不匹配的状态转换应无效果 ---
setup_test_env
create_test_taskboard

it "不匹配的状态转换应无效果"
# 尝试将 OPEN 直接改为 VERIFIED（跳步）
update_task_status "001" "IN_PROGRESS" "DONE" "$TASK_BOARD"
# 因为 #001 是 OPEN 不是 IN_PROGRESS，所以不应该变
result=$(awk '/## 任务 #001:/,/^---$/' "$TASK_BOARD" | grep '状态')
assert_contains "$result" "OPEN"

teardown_test_env

# 打印总结
print_summary
