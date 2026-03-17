#!/bin/bash
################################################################################
# 测试：真实脚本黑盒测试（直接调用 skill/scripts/*.sh）
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/test_helpers.sh"

describe "真实脚本黑盒测试"

# ═══════════════════════════════════════════
# update_task_status.sh 测试
# ═══════════════════════════════════════════

setup_test_env
it "update_task_status.sh 应能两参数更新状态"
mkdir -p "$TEST_DIR/planning"
cat > "$TEST_DIR/planning/codex-tasks.md" << 'EOF'
## 任务 #001: 测试任务

**状态**: OPEN
**优先级**: P1
**依赖任务**: 无

---
EOF
result=$(cd "$TEST_DIR" && bash "$PROJECT_DIR/skill/scripts/update_task_status.sh" 001 IN_PROGRESS "$TEST_DIR/planning/codex-tasks.md" 2>&1)
assert_contains "$result" "OK"
# 验证文件中状态已更新
file_content=$(cat "$TEST_DIR/planning/codex-tasks.md")
assert_contains "$file_content" "IN_PROGRESS"
teardown_test_env

setup_test_env
it "update_task_status.sh 对不存在的任务应报错"
mkdir -p "$TEST_DIR/planning"
cat > "$TEST_DIR/planning/codex-tasks.md" << 'EOF'
## 任务 #001: 测试任务

**状态**: OPEN

---
EOF
result=$(cd "$TEST_DIR" && bash "$PROJECT_DIR/skill/scripts/update_task_status.sh" 999 DONE "$TEST_DIR/planning/codex-tasks.md" 2>&1)
assert_contains "$result" "ERROR"
teardown_test_env

setup_test_env
it "update_task_status.sh 相同状态应跳过"
mkdir -p "$TEST_DIR/planning"
cat > "$TEST_DIR/planning/codex-tasks.md" << 'EOF'
## 任务 #001: 测试任务

**状态**: DONE

---
EOF
result=$(cd "$TEST_DIR" && bash "$PROJECT_DIR/skill/scripts/update_task_status.sh" 001 DONE "$TEST_DIR/planning/codex-tasks.md" 2>&1)
assert_contains "$result" "SKIP"
teardown_test_env

# ═══════════════════════════════════════════
# select_next_task.sh 测试
# ═══════════════════════════════════════════

setup_test_env
it "select_next_task.sh 应返回依赖已满足的任务"
mkdir -p "$TEST_DIR/planning"
cat > "$TEST_DIR/planning/codex-tasks.md" << 'EOF'
## 任务 #001: 基础任务

**状态**: DONE
**优先级**: P1
**依赖任务**: 无

---

## 任务 #002: 依赖任务

**状态**: OPEN
**优先级**: P1
**依赖任务**: #001

---
EOF
result=$(bash "$PROJECT_DIR/skill/scripts/select_next_task.sh" "$TEST_DIR/planning/codex-tasks.md" 2>&1)
assert_contains "$result" "002"
teardown_test_env

setup_test_env
it "select_next_task.sh 应跳过依赖未满足的任务"
mkdir -p "$TEST_DIR/planning"
cat > "$TEST_DIR/planning/codex-tasks.md" << 'EOF'
## 任务 #001: 基础任务

**状态**: OPEN
**优先级**: P1
**依赖任务**: 无

---

## 任务 #002: 依赖任务

**状态**: OPEN
**优先级**: P1
**依赖任务**: #001

---
EOF
result=$(bash "$PROJECT_DIR/skill/scripts/select_next_task.sh" "$TEST_DIR/planning/codex-tasks.md" 2>&1)
# 应该返回 001（无依赖），不返回 002（依赖未满足）
assert_contains "$result" "001"
if echo "$result" | grep -q "002"; then
    fail "不应返回依赖未满足的任务 #002"
else
    pass
fi
teardown_test_env

setup_test_env
it "select_next_task.sh --parallel 应只返回无依赖任务"
mkdir -p "$TEST_DIR/planning"
cat > "$TEST_DIR/planning/codex-tasks.md" << 'EOF'
## 任务 #001: 独立任务A

**状态**: OPEN
**优先级**: P1
**依赖任务**: 无

---

## 任务 #002: 依赖任务

**状态**: OPEN
**优先级**: P1
**依赖任务**: #001

---

## 任务 #003: 独立任务B

**状态**: OPEN
**优先级**: P2
**依赖任务**: 无

---
EOF
result=$(bash "$PROJECT_DIR/skill/scripts/select_next_task.sh" --parallel "$TEST_DIR/planning/codex-tasks.md" 2>&1)
assert_contains "$result" "001"
assert_contains "$result" "003"
teardown_test_env

setup_test_env
it "select_next_task.sh 无 OPEN 任务时应返回 NO_OPEN_TASKS"
mkdir -p "$TEST_DIR/planning"
cat > "$TEST_DIR/planning/codex-tasks.md" << 'EOF'
## 任务 #001: 已完成

**状态**: DONE
**优先级**: P1
**依赖任务**: 无

---
EOF
result=$(bash "$PROJECT_DIR/skill/scripts/select_next_task.sh" "$TEST_DIR/planning/codex-tasks.md" 2>&1)
assert_contains "$result" "NO_OPEN_TASKS"
teardown_test_env

# ═══════════════════════════════════════════
# write_checkpoint.sh 测试
# ═══════════════════════════════════════════

setup_test_env
it "write_checkpoint.sh 应创建 state.json"
cd "$TEST_DIR"
result=$(bash "$PROJECT_DIR/skill/scripts/write_checkpoint.sh" developing 2>&1)
assert_contains "$result" "CHECKPOINT"
assert_file_exists "$TEST_DIR/.dual-ai-collab/checkpoints/state.json"
teardown_test_env

setup_test_env
it "write_checkpoint.sh 应支持额外 key=value 参数"
cd "$TEST_DIR"
bash "$PROJECT_DIR/skill/scripts/write_checkpoint.sh" developing current_task=3 total_tasks=8 > /dev/null 2>&1
content=$(cat "$TEST_DIR/.dual-ai-collab/checkpoints/state.json")
assert_contains "$content" "developing"
assert_contains "$content" "current_task"
teardown_test_env

# ═══════════════════════════════════════════
# detect_stall.sh 测试
# ═══════════════════════════════════════════

setup_test_env
it "detect_stall.sh 对已退出进程应返回 SUCCESS 或 FAILED"
mkdir -p "$TEST_DIR/.dual-ai-collab/logs"
# 启动一个立即退出的进程获取 PID
bash -c "exit 0" &
DEAD_PID=$!
wait $DEAD_PID 2>/dev/null
touch "$TEST_DIR/.dual-ai-collab/logs/task-001.log"
touch "$TEST_DIR/.dual-ai-collab/logs/task-001.pid"
cd "$TEST_DIR"
result=$(bash "$PROJECT_DIR/skill/scripts/detect_stall.sh" 001 $DEAD_PID 2>&1)
if echo "$result" | grep -qE "SUCCESS|FAILED"; then
    pass
else
    fail "应返回 SUCCESS 或 FAILED，实际: $result"
fi
teardown_test_env

setup_test_env
it "detect_stall.sh 缺少参数应报错"
result=$(bash "$PROJECT_DIR/skill/scripts/detect_stall.sh" 2>&1)
exit_code=$?
if [ $exit_code -ne 0 ]; then
    pass
else
    fail "缺少参数应返回非零退出码"
fi
teardown_test_env

# 打印总结
print_summary
