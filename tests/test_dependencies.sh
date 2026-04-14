#!/bin/bash
################################################################################
# 测试：任务依赖管理
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/test_helpers.sh"

select_task() {
    local task_file="$1"
    (cd "$TEST_DIR" && bash "$PROJECT_DIR/skill/scripts/select_next_task.sh" "$task_file" 2>/dev/null)
}

selected_id() {
    echo "$1" | cut -d'|' -f2
}

create_deps_taskboard() {
    cat > "$TASK_BOARD" <<'EOF'
# 任务板 - 依赖测试

## 任务 #001: 基础模块

**优先级**: P1
**状态**: VERIFIED
**分配给**: Codex
**依赖任务**: 无

---

## 任务 #002: 依赖 #001 的任务

**优先级**: P1
**状态**: OPEN
**分配给**: Codex
**依赖任务**: #001

---

## 任务 #003: 依赖 #002 的任务

**优先级**: P1
**状态**: OPEN
**分配给**: Codex
**依赖任务**: #002

---

## 任务 #004: 无依赖的 P2 任务

**优先级**: P2
**状态**: OPEN
**分配给**: Codex
**依赖任务**: 无

---
EOF
}

describe "任务依赖管理测试（v2.1.0）"

setup_test_env
create_deps_taskboard
it "无依赖任务存在时应可正常领取"
result=$(select_task "$TASK_BOARD")
assert_not_empty "$result"
teardown_test_env

setup_test_env
create_deps_taskboard
it "依赖已 VERIFIED 的任务应被视为可执行"
result=$(select_task "$TASK_BOARD")
assert_equals "002" "$(selected_id "$result")"
teardown_test_env

setup_test_env
create_deps_taskboard
it "应跳过依赖未满足的任务"
result=$(select_task "$TASK_BOARD")
assert_not_contains "$result" "|003|"
teardown_test_env

setup_test_env
cat > "$TASK_BOARD" <<'EOF'
# 任务板 - 全部阻塞

## 任务 #001: 阻塞任务

**优先级**: P1
**状态**: OPEN
**依赖任务**: #099

---

## 任务 #002: 也阻塞

**优先级**: P2
**状态**: OPEN
**依赖任务**: #098

---
EOF
it "所有依赖未满足时应返回 NO_EXECUTABLE_TASKS"
result=$(select_task "$TASK_BOARD")
assert_equals "NO_EXECUTABLE_TASKS" "$result"
teardown_test_env

setup_test_env
cat > "$TASK_BOARD" <<'EOF'
# 任务板 - 多重依赖

## 任务 #001: 基础1

**优先级**: P1
**状态**: DONE
**依赖任务**: 无

---

## 任务 #002: 基础2

**优先级**: P1
**状态**: VERIFIED
**依赖任务**: 无

---

## 任务 #003: 组合任务

**优先级**: P1
**状态**: OPEN
**依赖任务**: #001, #002

---
EOF
it "多重依赖全部满足时应可领取"
result=$(select_task "$TASK_BOARD")
assert_equals "003" "$(selected_id "$result")"
teardown_test_env

setup_test_env
cat > "$TASK_BOARD" <<'EOF'
# 任务板 - 多重依赖部分未满足

## 任务 #001: 基础1

**优先级**: P1
**状态**: DONE
**依赖任务**: 无

---

## 任务 #002: 基础2

**优先级**: P1
**状态**: OPEN
**依赖任务**: 无

---

## 任务 #003: 组合任务

**优先级**: P1
**状态**: OPEN
**依赖任务**: #001, #002

---
EOF
it "多重依赖部分未满足时应优先选择真正可执行的任务"
result=$(select_task "$TASK_BOARD")
assert_equals "002" "$(selected_id "$result")"
teardown_test_env

print_summary
