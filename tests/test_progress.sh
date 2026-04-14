#!/bin/bash
################################################################################
# 测试：进度统计报告
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

describe "进度统计报告测试（v2.1.0）"

setup_test_env
create_test_taskboard
it "应正确统计总任务数"
stats=$(summary_output "$TASK_BOARD")
assert_equals "5" "$(value_of "$stats" "总任务")"
teardown_test_env

setup_test_env
create_test_taskboard
it "应正确统计各状态的任务数"
stats=$(summary_output "$TASK_BOARD")
assert_equals "3" "$(value_of "$stats" "OPEN")"
teardown_test_env

setup_test_env
create_test_taskboard
it "完成率应为 40.0%（2/5 已完成+已验收）"
stats=$(summary_output "$TASK_BOARD")
assert_equals "40.0%" "$(value_of "$stats" "完成率")"
teardown_test_env

setup_test_env
create_test_taskboard
it "审计通过率应为 100.0%（1 VERIFIED / 1 已审计任务）"
stats=$(summary_output "$TASK_BOARD")
assert_equals "100.0%" "$(value_of "$stats" "审计通过率")"
teardown_test_env

setup_test_env
cat > "$TASK_BOARD" <<'EOF'
# 任务板

## 任务 #001: 已验收1

**优先级**: P1
**状态**: VERIFIED

---

## 任务 #002: 已验收2

**优先级**: P2
**状态**: VERIFIED

---
EOF
it "全部验收时完成率应为 100.0%"
stats=$(summary_output "$TASK_BOARD")
assert_equals "100.0%" "$(value_of "$stats" "完成率")"

it "全部验收时审计通过率应为 100.0%"
stats=$(summary_output "$TASK_BOARD")
assert_equals "100.0%" "$(value_of "$stats" "审计通过率")"
teardown_test_env

setup_test_env
cat > "$TASK_BOARD" <<'EOF'
# 任务板

## 任务 #001: 被退回

**优先级**: P1
**状态**: REJECTED

---

## 任务 #002: 已验收

**优先级**: P1
**状态**: VERIFIED

---
EOF
it "应正确统计 REJECTED 数量"
stats=$(summary_output "$TASK_BOARD")
assert_equals "1" "$(value_of "$stats" "REJECTED")"
teardown_test_env

setup_test_env
create_empty_taskboard
it "空任务板完成率应为 0.0%"
stats=$(summary_output "$TASK_BOARD")
assert_equals "0.0%" "$(value_of "$stats" "完成率")"
teardown_test_env

print_summary
