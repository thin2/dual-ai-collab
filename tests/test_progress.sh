#!/bin/bash
################################################################################
# 测试：进度统计报告（v2.1.0）
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/test_helpers.sh"

# 进度统计函数（从 Skill v2.1.0 提取）
generate_progress_stats() {
    local task_file="$1"
    awk '
        /## 任务 #/ { total++ }
        /\*\*状态\*\*: OPEN/ { open++ }
        /\*\*状态\*\*: IN_PROGRESS/ { in_progress++ }
        /\*\*状态\*\*: DONE/ { done_count++ }
        /\*\*状态\*\*: VERIFIED/ { verified++ }
        /\*\*状态\*\*: REJECTED/ { rejected++ }
        /\*\*状态\*\*: BLOCKED/ { blocked++ }
        /\*\*优先级\*\*: P1/ { p1++ }
        /\*\*优先级\*\*: P2/ { p2++ }
        /\*\*优先级\*\*: P3/ { p3++ }
        END {
            total = total + 0
            open = open + 0; in_progress = in_progress + 0
            done_count = done_count + 0; verified = verified + 0
            rejected = rejected + 0; blocked = blocked + 0
            p1 = p1 + 0; p2 = p2 + 0; p3 = p3 + 0
            completed = done_count + verified
            if (total > 0) {
                completion_rate = int(completed * 100 / total)
                if (completed > 0) {
                    audit_rate = int(verified * 100 / completed)
                } else {
                    audit_rate = 0
                }
            } else {
                completion_rate = 0
                audit_rate = 0
            }
            print "total=" total
            print "open=" open
            print "in_progress=" in_progress
            print "done=" done_count
            print "verified=" verified
            print "rejected=" rejected
            print "blocked=" blocked
            print "p1=" p1
            print "p2=" p2
            print "p3=" p3
            print "completion_rate=" completion_rate
            print "audit_rate=" audit_rate
        }
    ' "$task_file"
}

# 提取统计值的辅助函数
get_stat() {
    local stats="$1"
    local key="$2"
    echo "$stats" | grep "^${key}=" | cut -d= -f2
}

# ═══════════════════════════════════════════
# 测试开始
# ═══════════════════════════════════════════

describe "进度统计报告测试（v2.1.0）"

# --- 测试 1：标准任务板统计 ---
setup_test_env
create_test_taskboard

it "应正确统计总任务数"
stats=$(generate_progress_stats "$TASK_BOARD")
assert_equals "5" "$(get_stat "$stats" "total")"

teardown_test_env

# --- 测试 2：各状态计数 ---
setup_test_env
create_test_taskboard

it "应正确统计各状态的任务数"
stats=$(generate_progress_stats "$TASK_BOARD")
assert_equals "3" "$(get_stat "$stats" "open")"

teardown_test_env

# --- 测试 3：完成率计算 ---
setup_test_env
create_test_taskboard

it "完成率应为 40%（2/5 已完成+已验收）"
stats=$(generate_progress_stats "$TASK_BOARD")
assert_equals "40" "$(get_stat "$stats" "completion_rate")"

teardown_test_env

# --- 测试 4：审计通过率 ---
setup_test_env
create_test_taskboard

it "审计通过率应为 50%（1 VERIFIED / 2 完成）"
stats=$(generate_progress_stats "$TASK_BOARD")
assert_equals "50" "$(get_stat "$stats" "audit_rate")"

teardown_test_env

# --- 测试 5：优先级分布 ---
setup_test_env
create_test_taskboard

it "应正确统计各优先级数量"
stats=$(generate_progress_stats "$TASK_BOARD")
p1=$(get_stat "$stats" "p1")
p2=$(get_stat "$stats" "p2")
p3=$(get_stat "$stats" "p3")
# 任务板有 2 个 P1, 2 个 P2, 1 个 P3
assert_equals "2" "$p1"
assert_equals "2" "$p2"
assert_equals "1" "$p3"

teardown_test_env

# --- 测试 6：空任务板统计 ---
setup_test_env
create_empty_taskboard

it "空任务板完成率应为 0"
stats=$(generate_progress_stats "$TASK_BOARD")
assert_equals "0" "$(get_stat "$stats" "completion_rate")"

teardown_test_env

# --- 测试 7：全部验收完成 ---
setup_test_env
cat > "$TASK_BOARD" <<'EOF'
# 任务板 - 全部验收

## 任务 #001: 已验收1

**优先级**: P1
**状态**: VERIFIED
**分配给**: Codex

---

## 任务 #002: 已验收2

**优先级**: P2
**状态**: VERIFIED
**分配给**: Codex

---
EOF

it "全部验收时完成率应为 100"
stats=$(generate_progress_stats "$TASK_BOARD")
assert_equals "100" "$(get_stat "$stats" "completion_rate")"

it "全部验收时审计通过率应为 100"
stats=$(generate_progress_stats "$TASK_BOARD")
assert_equals "100" "$(get_stat "$stats" "audit_rate")"

teardown_test_env

# --- 测试 9：含 REJECTED 任务 ---
setup_test_env
cat > "$TASK_BOARD" <<'EOF'
# 任务板

## 任务 #001: 被退回

**优先级**: P1
**状态**: REJECTED
**分配给**: Codex

---

## 任务 #002: 已验收

**优先级**: P1
**状态**: VERIFIED
**分配给**: Codex

---
EOF

it "应正确统计 REJECTED 数量"
stats=$(generate_progress_stats "$TASK_BOARD")
assert_equals "1" "$(get_stat "$stats" "rejected")"

teardown_test_env

# 打印总结
print_summary
