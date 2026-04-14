#!/bin/bash
################################################################################
# 测试：统计报告输出
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/test_helpers.sh"

summary_output() {
    local task_file="$1"
    (cd "$TEST_DIR" && bash "$PROJECT_DIR/skill/scripts/summarize_progress.sh" "$task_file" 2>&1)
}

value_of() {
    local output="$1"
    local label="$2"
    echo "$output" | awk -F': ' -v label="$label" '$1 == label {print $2; exit}'
}

describe "统计报告输出测试"

setup_test_env
create_test_taskboard
it "应正确计算总任务数"
result=$(summary_output "$TASK_BOARD")
assert_equals "5" "$(value_of "$result" "总任务")"
teardown_test_env

setup_test_env
create_test_taskboard
it "应正确计算 OPEN 任务数"
result=$(summary_output "$TASK_BOARD")
assert_equals "3" "$(value_of "$result" "OPEN")"
teardown_test_env

setup_test_env
create_test_taskboard
it "应正确计算 DONE 任务数"
result=$(summary_output "$TASK_BOARD")
assert_equals "1" "$(value_of "$result" "DONE")"
teardown_test_env

setup_test_env
create_test_taskboard
it "应正确计算 VERIFIED 任务数"
result=$(summary_output "$TASK_BOARD")
assert_equals "1" "$(value_of "$result" "VERIFIED")"
teardown_test_env

setup_test_env
create_test_taskboard
it "IN_PROGRESS 初始应为 0"
result=$(summary_output "$TASK_BOARD")
assert_equals "0" "$(value_of "$result" "IN_PROGRESS")"
teardown_test_env

setup_test_env
create_empty_taskboard
it "空任务板总数应为 0"
result=$(summary_output "$TASK_BOARD")
assert_equals "0" "$(value_of "$result" "总任务")"
teardown_test_env

setup_test_env
create_empty_taskboard
it "空任务板 OPEN 应为 0"
result=$(summary_output "$TASK_BOARD")
assert_equals "0" "$(value_of "$result" "OPEN")"
teardown_test_env

setup_test_env
create_all_done_taskboard
it "全部完成任务板 OPEN 应为 0"
result=$(summary_output "$TASK_BOARD")
assert_equals "0" "$(value_of "$result" "OPEN")"
teardown_test_env

setup_test_env
create_test_taskboard
it "统计输出应为单行纯数字（无脏值）"
result=$(summary_output "$TASK_BOARD")
value=$(value_of "$result" "OPEN")
if [[ "$value" =~ ^[0-9]+$ ]]; then
    pass
else
    fail "输出不是纯数字: [$value]"
fi
teardown_test_env

setup_test_env
create_test_taskboard
it "REJECTED 初始应为 0"
result=$(summary_output "$TASK_BOARD")
assert_equals "0" "$(value_of "$result" "REJECTED")"
teardown_test_env

print_summary
