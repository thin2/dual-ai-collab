#!/bin/bash
################################################################################
# 测试：任务领取和优先级调度
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/test_helpers.sh"

# 从 codex-auto-worker.sh 中提取 find_next_task 函数
find_next_task() {
    local task_file="$1"
    awk '
        BEGIN { task_count = 0 }
        /## 任务 #[0-9]+:/ {
            if (in_task && task_content ~ /状态.*: OPEN/) {
                tasks[task_count] = task_header "\n" task_content
                priorities[task_count] = priority
                task_count++
            }
            in_task = 1
            task_header = $0
            task_content = ""
            priority = 9
            next
        }
        in_task && /^---$/ {
            if (task_content ~ /状态.*: OPEN/) {
                tasks[task_count] = task_header "\n" task_content
                priorities[task_count] = priority
                task_count++
            }
            in_task = 0
            task_content = ""
            next
        }
        in_task {
            task_content = task_content $0 "\n"
            if ($0 ~ /优先级.*: P1/) { priority = 1 }
            else if ($0 ~ /优先级.*: P2/) { priority = 2 }
            else if ($0 ~ /优先级.*: P3/) { priority = 3 }
        }
        END {
            if (task_count > 0) {
                min_priority = 9; min_index = -1
                for (i = 0; i < task_count; i++) {
                    if (priorities[i] < min_priority) {
                        min_priority = priorities[i]; min_index = i
                    }
                }
                if (min_index >= 0) print tasks[min_index]
            }
        }
    ' "$task_file"
}

extract_task_id() {
    local task_header="$1"
    echo "$task_header" | grep -oP '任务 #\K\d+'
}

# ═══════════════════════════════════════════
# 测试开始
# ═══════════════════════════════════════════

describe "任务领取和优先级调度测试"

# --- 测试 1：能从任务板中领取 OPEN 任务 ---
setup_test_env
create_test_taskboard

it "应能从任务板中领取 OPEN 任务"
result=$(find_next_task "$TASK_BOARD")
assert_not_empty "$result"

teardown_test_env

# --- 测试 2：优先选择 P1 任务 ---
setup_test_env
create_test_taskboard

it "应优先选择 P1 任务（P1 在 P3 之后出现）"
result=$(find_next_task "$TASK_BOARD")
assert_contains "$result" "#002"

teardown_test_env

# --- 测试 3：不领取 DONE 任务 ---
setup_test_env
create_test_taskboard

it "不应领取 DONE 状态的任务"
result=$(find_next_task "$TASK_BOARD")
assert_not_contains "$result" "#004"

teardown_test_env

# --- 测试 4：不领取 VERIFIED 任务 ---
setup_test_env
create_test_taskboard

it "不应领取 VERIFIED 状态的任务"
result=$(find_next_task "$TASK_BOARD")
assert_not_contains "$result" "#005"

teardown_test_env

# --- 测试 5：全部完成时返回空 ---
setup_test_env
create_all_done_taskboard

it "全部任务完成时应返回空结果"
result=$(find_next_task "$TASK_BOARD")
assert_empty "$result"

teardown_test_env

# --- 测试 6：空任务板返回空 ---
setup_test_env
create_empty_taskboard

it "空任务板应返回空结果"
result=$(find_next_task "$TASK_BOARD")
assert_empty "$result"

teardown_test_env

# --- 测试 7：提取任务 ID ---
it "应正确提取任务 ID"
task_id=$(extract_task_id "## 任务 #002: P1 高优先级任务")
assert_equals "002" "$task_id"

# --- 测试 8：多个同优先级任务取第一个 ---
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
assert_contains "$result" "#010"

teardown_test_env

# --- 测试 9：只有一个 OPEN 任务 ---
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
assert_contains "$result" "#001"

teardown_test_env

# --- 测试 10：无优先级标记的任务默认最低 ---
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
assert_contains "$result" "#002"

teardown_test_env

# 打印总结
print_summary
