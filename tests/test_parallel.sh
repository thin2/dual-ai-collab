#!/bin/bash
################################################################################
# 测试：并行任务识别
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/test_helpers.sh"

find_parallel_tasks() {
    local task_file="$1"
    (cd "$TEST_DIR" && bash "$PROJECT_DIR/skill/scripts/select_next_task.sh" --parallel "$task_file" 2>/dev/null)
}

describe "并行任务识别测试（v2.1.0）"

setup_test_env
cat > "$TASK_BOARD" <<'EOF'
# 任务板 - 并行测试

## 任务 #001: 独立任务A

**优先级**: P1
**状态**: OPEN
**分配给**: Codex
**依赖任务**: 无

---

## 任务 #002: 独立任务B

**优先级**: P2
**状态**: OPEN
**分配给**: Codex
**依赖任务**: 无

---

## 任务 #003: 有依赖任务

**优先级**: P1
**状态**: OPEN
**分配给**: Codex
**依赖任务**: #001

---
EOF
it "应识别出无依赖的 OPEN 任务"
result=$(find_parallel_tasks "$TASK_BOARD")
count=$(echo "$result" | grep -c '|')
assert_equals "2" "$count"
teardown_test_env

setup_test_env
cat > "$TASK_BOARD" <<'EOF'
# 任务板

## 任务 #001: 独立A

**优先级**: P1
**状态**: OPEN
**依赖任务**: 无

---

## 任务 #002: 独立B

**优先级**: P2
**状态**: OPEN
**依赖任务**: -

---

## 任务 #003: 有依赖

**优先级**: P1
**状态**: OPEN
**依赖任务**: #001

---
EOF
it "并行任务应包含 #001"
result=$(find_parallel_tasks "$TASK_BOARD")
assert_contains "$result" "|001|"

it "并行任务应包含 #002"
assert_contains "$result" "|002|"

it "并行任务不应包含有依赖的 #003"
assert_not_contains "$result" "|003|"
teardown_test_env

setup_test_env
cat > "$TASK_BOARD" <<'EOF'
# 任务板

## 任务 #001: 已完成

**优先级**: P1
**状态**: DONE
**依赖任务**: 无

---

## 任务 #002: OPEN 独立

**优先级**: P2
**状态**: OPEN
**依赖任务**: 无

---
EOF
it "不应包含非 OPEN 状态的无依赖任务"
result=$(find_parallel_tasks "$TASK_BOARD")
assert_not_contains "$result" "|001|"
assert_contains "$result" "|002|"
teardown_test_env

setup_test_env
cat > "$TASK_BOARD" <<'EOF'
# 任务板

## 任务 #001: 有依赖A

**优先级**: P1
**状态**: OPEN
**依赖任务**: #099

---

## 任务 #002: 有依赖B

**优先级**: P2
**状态**: OPEN
**依赖任务**: #098

---
EOF
it "全部有依赖时应返回 NO_PARALLEL_TASKS"
result=$(find_parallel_tasks "$TASK_BOARD")
assert_equals "NO_PARALLEL_TASKS" "$result"
teardown_test_env

setup_test_env
create_empty_taskboard
it "空任务板应返回 NO_OPEN_TASKS"
result=$(find_parallel_tasks "$TASK_BOARD")
assert_equals "NO_OPEN_TASKS" "$result"
teardown_test_env

print_summary
