#!/bin/bash
################################################################################
# 测试辅助函数
# 提供测试框架、临时环境管理和断言工具
################################################################################

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 测试计数器
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0
CURRENT_TEST=""

# 设置临时测试环境
setup_test_env() {
    TEST_DIR=$(mktemp -d)
    mkdir -p "$TEST_DIR/planning"
    mkdir -p "$TEST_DIR/.dual-ai-collab/logs"
    mkdir -p "$TEST_DIR/.dual-ai-collab/checkpoints"
    export PROJECT_ROOT="$TEST_DIR"
    export TASK_BOARD="$TEST_DIR/planning/codex-tasks.md"
    export LOG_FILE="$TEST_DIR/.dual-ai-collab/logs/worker.log"
}

# 清理临时测试环境
teardown_test_env() {
    if [ -n "${TEST_DIR:-}" ] && [ -d "$TEST_DIR" ]; then
        rm -rf "$TEST_DIR"
    fi
}

# 创建测试任务板
create_test_taskboard() {
    cat > "$TASK_BOARD" <<'EOF'
# 任务板 - 测试项目

## 任务 #001: P3 低优先级任务

**优先级**: P3
**状态**: OPEN
**分配给**: Codex

### 任务描述
这是一个 P3 低优先级测试任务

---

## 任务 #002: P1 高优先级任务

**优先级**: P1
**状态**: OPEN
**分配给**: Codex

### 任务描述
这是一个 P1 高优先级测试任务

---

## 任务 #003: P2 中优先级任务

**优先级**: P2
**状态**: OPEN
**分配给**: Codex

### 任务描述
这是一个 P2 中优先级测试任务

---

## 任务 #004: 已完成的任务

**优先级**: P1
**状态**: DONE
**分配给**: Codex

### 任务描述
这是一个已完成的任务

---

## 任务 #005: 已验收的任务

**优先级**: P2
**状态**: VERIFIED
**分配给**: Codex

### 任务描述
这是一个已验收的任务

---
EOF
}

# 创建只有已完成任务的任务板（无 OPEN 任务）
create_all_done_taskboard() {
    cat > "$TASK_BOARD" <<'EOF'
# 任务板 - 全部完成

## 任务 #001: 已完成任务1

**优先级**: P1
**状态**: DONE
**分配给**: Codex

### 任务描述
已完成

---

## 任务 #002: 已验收任务

**优先级**: P2
**状态**: VERIFIED
**分配给**: Codex

### 任务描述
已验收

---
EOF
}

# 创建空任务板
create_empty_taskboard() {
    cat > "$TASK_BOARD" <<'EOF'
# 任务板 - 空

暂无任务。
EOF
}

# 测试框架函数
describe() {
    echo ""
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}📋 $1${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

it() {
    CURRENT_TEST="$1"
    TESTS_RUN=$((TESTS_RUN + 1))
}

pass() {
    TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}✅ $CURRENT_TEST${NC}"
}

fail() {
    TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}❌ $CURRENT_TEST${NC}"
    if [ -n "${1:-}" ]; then
        echo -e "     ${RED}原因: $1${NC}"
    fi
}

# 断言函数
assert_equals() {
    local expected="$1"
    local actual="$2"
    if [ "$expected" = "$actual" ]; then
        pass
    else
        fail "期望 [$expected] 但得到 [$actual]"
    fi
}

assert_contains() {
    local haystack="$1"
    local needle="$2"
    if echo "$haystack" | grep -q "$needle"; then
        pass
    else
        fail "输出不包含 [$needle]"
    fi
}

assert_not_contains() {
    local haystack="$1"
    local needle="$2"
    if ! echo "$haystack" | grep -q "$needle"; then
        pass
    else
        fail "输出不应包含 [$needle]"
    fi
}

assert_empty() {
    local value="$1"
    if [ -z "$value" ]; then
        pass
    else
        fail "期望为空但得到 [$value]"
    fi
}

assert_not_empty() {
    local value="$1"
    if [ -n "$value" ]; then
        pass
    else
        fail "期望非空但得到空值"
    fi
}

assert_file_exists() {
    local file="$1"
    if [ -f "$file" ]; then
        pass
    else
        fail "文件不存在: $file"
    fi
}

assert_exit_code() {
    local expected="$1"
    local actual="$2"
    if [ "$expected" -eq "$actual" ]; then
        pass
    else
        fail "期望退出码 $expected 但得到 $actual"
    fi
}

# 打印测试总结
print_summary() {
    echo ""
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}📊 测试结果${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  总数:   $TESTS_RUN"
    echo -e "  ${GREEN}通过:   $TESTS_PASSED${NC}"
    echo -e "  ${RED}失败:   $TESTS_FAILED${NC}"
    echo ""

    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "${GREEN}🎉 所有测试通过！${NC}"
        return 0
    else
        echo -e "${RED}💥 有 $TESTS_FAILED 个测试失败${NC}"
        return 1
    fi
}
