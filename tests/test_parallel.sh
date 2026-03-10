#!/bin/bash
################################################################################
# 测试：并行任务识别（v2.1.0）
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/test_helpers.sh"

# 识别可并行执行的独立任务（从 Skill v2.1.0 提取）
find_parallel_tasks() {
    local task_file="$1"
    awk '
        /## 任务 #[0-9]+:/ {
            id = ""; status = ""; deps = "无"
            match($0, /#([0-9]+):/, a); id = a[1]
            in_task = 1; next
        }
        in_task && /\*\*状态\*\*:/ {
            if ($0 ~ /OPEN/) status = "OPEN"
        }
        in_task && /\*\*依赖任务\*\*:/ {
            gsub(/.*\*\*依赖任务\*\*: */, ""); gsub(/ *$/, ""); deps = $0
        }
        in_task && /^---$/ {
            if (status == "OPEN" && (deps == "无" || deps == "-" || deps == "")) {
                print id
            }
            in_task = 0
        }
    ' "$task_file"
}

# ═══════════════════════════════════════════
# 测试开始
# ═══════════════════════════════════════════

describe "并行任务识别测试（v2.1.0）"

# --- 测试 1：识别无依赖的 OPEN 任务 ---
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
count=$(echo "$result" | wc -l)
assert_equals "2" "$count"

teardown_test_env

# --- 测试 2：结果包含正确的任务 ID ---
setup_test_env
cat > "$TASK_BOARD" <<'EOF'
# 任务板

## 任务 #001: 独立A

**优先级**: P1
**状态**: OPEN
**分配给**: Codex
**依赖任务**: 无

---

## 任务 #002: 独立B

**优先级**: P2
**状态**: OPEN
**分配给**: Codex
**依赖任务**: -

---

## 任务 #003: 有依赖

**优先级**: P1
**状态**: OPEN
**分配给**: Codex
**依赖任务**: #001

---
EOF

it "并行任务应包含 #001"
result=$(find_parallel_tasks "$TASK_BOARD")
assert_contains "$result" "001"

it "并行任务应包含 #002"
assert_contains "$result" "002"

it "并行任务不应包含有依赖的 #003"
assert_not_contains "$result" "003"

teardown_test_env

# --- 测试 3：排除非 OPEN 状态的任务 ---
setup_test_env
cat > "$TASK_BOARD" <<'EOF'
# 任务板

## 任务 #001: 已完成

**优先级**: P1
**状态**: DONE
**分配给**: Codex
**依赖任务**: 无

---

## 任务 #002: OPEN 独立

**优先级**: P2
**状态**: OPEN
**分配给**: Codex
**依赖任务**: 无

---
EOF

it "不应包含非 OPEN 状态的无依赖任务"
result=$(find_parallel_tasks "$TASK_BOARD")
assert_not_contains "$result" "001"
assert_contains "$result" "002"

teardown_test_env

# --- 测试 4：全部有依赖时返回空 ---
setup_test_env
cat > "$TASK_BOARD" <<'EOF'
# 任务板

## 任务 #001: 有依赖A

**优先级**: P1
**状态**: OPEN
**分配给**: Codex
**依赖任务**: #099

---

## 任务 #002: 有依赖B

**优先级**: P2
**状态**: OPEN
**分配给**: Codex
**依赖任务**: #098

---
EOF

it "全部有依赖时应返回空"
result=$(find_parallel_tasks "$TASK_BOARD")
assert_empty "$result"

teardown_test_env

# --- 测试 5：空任务板 ---
setup_test_env
create_empty_taskboard

it "空任务板应返回空"
result=$(find_parallel_tasks "$TASK_BOARD")
assert_empty "$result"

teardown_test_env

# 打印总结
print_summary
