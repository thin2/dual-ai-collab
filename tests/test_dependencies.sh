#!/bin/bash
################################################################################
# 测试：任务依赖管理（v2.1.0）
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/test_helpers.sh"

# 依赖检查函数（从 Skill v2.1.0 提取）
check_deps() {
    local task_file="$1"
    local deps="$2"
    # 无依赖则通过
    if [ -z "$deps" ] || [ "$deps" = "无" ] || [ "$deps" = "-" ]; then
        return 0
    fi
    # 提取依赖任务编号，检查是否均为 DONE 或 VERIFIED
    for dep in $(echo "$deps" | grep -oP '#\d+' | sed 's/#//'); do
        local dep_status
        dep_status=$(awk -v id="$dep" '
            $0 ~ "## 任务 #0*" id ":" { found=1 }
            found && /\*\*状态\*\*:/ { gsub(/.*\*\*状态\*\*: */, ""); gsub(/ *$/, ""); print; exit }
        ' "$task_file")
        if [ "$dep_status" != "DONE" ] && [ "$dep_status" != "VERIFIED" ]; then
            return 1
        fi
    done
    return 0
}

# 带依赖检查的任务领取
find_next_task_with_deps() {
    local task_file="$1"
    # 提取所有 OPEN 任务及其依赖
    local task_ids=()
    local task_priorities=()
    local task_deps=()

    while IFS='|' read -r id priority deps; do
        task_ids+=("$id")
        task_priorities+=("$priority")
        task_deps+=("$deps")
    done < <(awk '
        /## 任务 #[0-9]+:/ {
            id = ""; priority = 9; deps = "无"; status = ""
            match($0, /#([0-9]+):/, a); id = a[1]
            in_task = 1; next
        }
        in_task && /\*\*优先级\*\*:/ {
            if ($0 ~ /P1/) priority = 1
            else if ($0 ~ /P2/) priority = 2
            else if ($0 ~ /P3/) priority = 3
        }
        in_task && /\*\*状态\*\*:/ {
            gsub(/.*\*\*状态\*\*: */, ""); gsub(/ *$/, ""); status = $0
        }
        in_task && /\*\*依赖任务\*\*:/ {
            gsub(/.*\*\*依赖任务\*\*: */, ""); gsub(/ *$/, ""); deps = $0
        }
        in_task && /^---$/ {
            if (status == "OPEN") print id "|" priority "|" deps
            in_task = 0
        }
    ' "$task_file")

    # 按优先级排序，取依赖满足的第一个
    local best_id=""
    local best_priority=9
    for i in "${!task_ids[@]}"; do
        if [ "${task_priorities[$i]}" -lt "$best_priority" ]; then
            if check_deps "$task_file" "${task_deps[$i]}"; then
                best_priority="${task_priorities[$i]}"
                best_id="${task_ids[$i]}"
            fi
        fi
    done
    echo "$best_id"
}

# 创建带依赖的任务板
create_deps_taskboard() {
    cat > "$TASK_BOARD" <<'EOF'
# 任务板 - 依赖测试

## 任务 #001: 基础模块

**优先级**: P1
**状态**: VERIFIED
**分配给**: Codex
**依赖任务**: 无

### 任务描述
基础模块，已验收

---

## 任务 #002: 依赖 #001 的任务

**优先级**: P1
**状态**: OPEN
**分配给**: Codex
**依赖任务**: #001

### 任务描述
依赖已验收的 #001

---

## 任务 #003: 依赖 #002 的任务

**优先级**: P1
**状态**: OPEN
**分配给**: Codex
**依赖任务**: #002

### 任务描述
依赖未完成的 #002

---

## 任务 #004: 无依赖的 P2 任务

**优先级**: P2
**状态**: OPEN
**分配给**: Codex
**依赖任务**: 无

### 任务描述
独立任务

---
EOF
}

# ═══════════════════════════════════════════
# 测试开始
# ═══════════════════════════════════════════

describe "任务依赖管理测试（v2.1.0）"

# --- 测试 1：无依赖返回通过 ---
setup_test_env
create_deps_taskboard

it "无依赖的任务应通过检查"
check_deps "$TASK_BOARD" "无"
assert_exit_code 0 $?

teardown_test_env

# --- 测试 2：空依赖返回通过 ---
it "空依赖应通过检查"
check_deps "/dev/null" ""
assert_exit_code 0 $?

# --- 测试 3：横杠依赖返回通过 ---
it "横杠(-)依赖应通过检查"
check_deps "/dev/null" "-"
assert_exit_code 0 $?

# --- 测试 4：依赖已 VERIFIED 任务通过 ---
setup_test_env
create_deps_taskboard

it "依赖已 VERIFIED 的任务应通过检查"
check_deps "$TASK_BOARD" "#001"
assert_exit_code 0 $?

teardown_test_env

# --- 测试 5：依赖未完成任务不通过 ---
setup_test_env
create_deps_taskboard

it "依赖未完成(OPEN)的任务应不通过检查"
check_deps "$TASK_BOARD" "#002"
result=$?
assert_equals "1" "$result"

teardown_test_env

# --- 测试 6：带依赖的任务领取 - 跳过依赖未满足 ---
setup_test_env
create_deps_taskboard

it "应跳过依赖未满足的任务，选取依赖满足的"
result=$(find_next_task_with_deps "$TASK_BOARD")
assert_equals "002" "$result"

teardown_test_env

# --- 测试 7：所有任务依赖未满足时返回空 ---
setup_test_env
cat > "$TASK_BOARD" <<'EOF'
# 任务板 - 全部阻塞

## 任务 #001: 阻塞任务

**优先级**: P1
**状态**: OPEN
**分配给**: Codex
**依赖任务**: #099

### 任务描述
依赖不存在的任务

---
EOF

it "所有依赖未满足时应返回空"
result=$(find_next_task_with_deps "$TASK_BOARD")
assert_empty "$result"

teardown_test_env

# --- 测试 8：多重依赖全部满足 ---
setup_test_env
cat > "$TASK_BOARD" <<'EOF'
# 任务板 - 多重依赖

## 任务 #001: 基础A

**优先级**: P1
**状态**: VERIFIED
**分配给**: Codex
**依赖任务**: 无

---

## 任务 #002: 基础B

**优先级**: P1
**状态**: VERIFIED
**分配给**: Codex
**依赖任务**: 无

---

## 任务 #003: 依赖AB

**优先级**: P1
**状态**: OPEN
**分配给**: Codex
**依赖任务**: #001, #002

### 任务描述
依赖两个已验收的任务

---
EOF

it "多重依赖全部 VERIFIED 时应通过"
check_deps "$TASK_BOARD" "#001, #002"
assert_exit_code 0 $?

teardown_test_env

# --- 测试 9：多重依赖部分未满足 ---
setup_test_env
cat > "$TASK_BOARD" <<'EOF'
# 任务板 - 部分满足

## 任务 #001: 已验收

**优先级**: P1
**状态**: VERIFIED
**分配给**: Codex
**依赖任务**: 无

---

## 任务 #002: 未完成

**优先级**: P1
**状态**: OPEN
**分配给**: Codex
**依赖任务**: 无

---

## 任务 #003: 依赖两个

**优先级**: P1
**状态**: OPEN
**分配给**: Codex
**依赖任务**: #001, #002

---
EOF

it "多重依赖部分未满足时应不通过"
check_deps "$TASK_BOARD" "#001, #002"
result=$?
assert_equals "1" "$result"

teardown_test_env

# 打印总结
print_summary
