#!/bin/bash
################################################################################
# 测试：任务领取和优先级调度
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/test_helpers.sh"

find_next_task() {
    local task_file="$1"
    (cd "$TEST_DIR" && bash "$PROJECT_DIR/skill/scripts/select_next_task.sh" "$task_file" 2>/dev/null)
}

extract_task_id() {
    local selection="$1"
    echo "$selection" | cut -d'|' -f2
}

describe "任务领取和优先级调度测试"

setup_test_env
create_test_taskboard
it "应能从任务板中领取 OPEN 任务"
result=$(find_next_task "$TASK_BOARD")
assert_not_empty "$result"
teardown_test_env

setup_test_env
create_test_taskboard
it "应优先选择 P1 任务（P1 在 P3 之后出现）"
result=$(find_next_task "$TASK_BOARD")
assert_equals "002" "$(extract_task_id "$result")"
teardown_test_env

setup_test_env
create_test_taskboard
it "不应领取 DONE 状态的任务"
result=$(find_next_task "$TASK_BOARD")
assert_not_contains "$result" "|004|"
teardown_test_env

setup_test_env
create_test_taskboard
it "不应领取 VERIFIED 状态的任务"
result=$(find_next_task "$TASK_BOARD")
assert_not_contains "$result" "|005|"
teardown_test_env

setup_test_env
create_all_done_taskboard
it "全部任务完成时应返回 NO_OPEN_TASKS"
result=$(find_next_task "$TASK_BOARD")
assert_equals "NO_OPEN_TASKS" "$result"
teardown_test_env

setup_test_env
create_empty_taskboard
it "空任务板应返回 NO_OPEN_TASKS"
result=$(find_next_task "$TASK_BOARD")
assert_equals "NO_OPEN_TASKS" "$result"
teardown_test_env

it "应正确提取任务 ID"
task_id=$(extract_task_id "1|002|无")
assert_equals "002" "$task_id"

setup_test_env
cat > "$TASK_BOARD" <<'EOF'
## 任务 #010: 第一个 P1

**优先级**: P1
**状态**: OPEN
**分配给**: Codex

### 任务描述
第一个

---

## 任务 #011: 第二个 P1

**优先级**: P1
**状态**: OPEN
**分配给**: Codex

### 任务描述
第二个

---
EOF
it "多个同优先级任务应领取第一个"
result=$(find_next_task "$TASK_BOARD")
assert_equals "010" "$(extract_task_id "$result")"
teardown_test_env

setup_test_env
cat > "$TASK_BOARD" <<'EOF'
## 任务 #001: 唯一任务

**优先级**: P2
**状态**: OPEN
**分配给**: Codex

### 任务描述
唯一的 OPEN 任务

---

## 任务 #002: 已完成

**优先级**: P1
**状态**: DONE
**分配给**: Codex

### 任务描述
已完成

---
EOF
it "只有一个 OPEN 任务时应正确领取"
result=$(find_next_task "$TASK_BOARD")
assert_equals "001" "$(extract_task_id "$result")"
teardown_test_env

setup_test_env
cat > "$TASK_BOARD" <<'EOF'
## 任务 #001: 无优先级任务

**状态**: OPEN
**分配给**: Codex

### 任务描述
没有优先级标记

---

## 任务 #002: P2 任务

**优先级**: P2
**状态**: OPEN
**分配给**: Codex

### 任务描述
有优先级

---
EOF
it "无优先级标记的任务应排在有优先级的后面"
result=$(find_next_task "$TASK_BOARD")
assert_equals "002" "$(extract_task_id "$result")"
teardown_test_env

print_summary
