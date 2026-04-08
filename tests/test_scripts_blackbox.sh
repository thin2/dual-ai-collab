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

setup_test_env
it "update_task_status.sh 遇到缺少状态字段的任务应报错"
mkdir -p "$TEST_DIR/planning"
cat > "$TEST_DIR/planning/codex-tasks.md" << 'EOF'
## 任务 #001: 缺少状态

**优先级**: P1

---
EOF
result=$(cd "$TEST_DIR" && bash "$PROJECT_DIR/skill/scripts/update_task_status.sh" 001 DONE "$TEST_DIR/planning/codex-tasks.md" 2>&1)
exit_code=$?
if [ $exit_code -eq 0 ]; then
    fail "缺少状态字段时应返回非零退出码"
else
    pass
fi
assert_contains "$result" "缺少"
file_content=$(cat "$TEST_DIR/planning/codex-tasks.md")
assert_not_contains "$file_content" "DONE"
teardown_test_env

setup_test_env
it "update_task_status.sh 并发更新两个任务时不应互相覆盖"
mkdir -p "$TEST_DIR/planning"
cat > "$TEST_DIR/planning/codex-tasks.md" << 'EOF'
## 任务 #001: 任务 A

**状态**: OPEN

---

## 任务 #002: 任务 B

**状态**: OPEN

---
EOF
(
    cd "$TEST_DIR" && bash "$PROJECT_DIR/skill/scripts/update_task_status.sh" 001 DONE "$TEST_DIR/planning/codex-tasks.md" >/dev/null
) &
pid1=$!
(
    cd "$TEST_DIR" && bash "$PROJECT_DIR/skill/scripts/update_task_status.sh" 002 DONE "$TEST_DIR/planning/codex-tasks.md" >/dev/null
) &
pid2=$!
wait $pid1 $pid2
done_count=$(grep -c '\*\*状态\*\*: DONE' "$TEST_DIR/planning/codex-tasks.md")
assert_equals "2" "$done_count"
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

setup_test_env
it "select_next_task.sh 遇到缺少状态字段的任务应报错"
mkdir -p "$TEST_DIR/planning"
cat > "$TEST_DIR/planning/codex-tasks.md" << 'EOF'
## 任务 #001: 半成品任务

**优先级**: P1

---
EOF
result=$(bash "$PROJECT_DIR/skill/scripts/select_next_task.sh" "$TEST_DIR/planning/codex-tasks.md" 2>&1)
exit_code=$?
if [ $exit_code -eq 0 ]; then
    fail "任务缺少状态字段时应返回非零退出码"
else
    pass
fi
assert_contains "$result" "缺少"
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

setup_test_env
it "check_checkpoint.sh 遇到损坏 checkpoint 应返回 CHECKPOINT_CORRUPTED"
cd "$TEST_DIR"
printf '{broken json' > "$TEST_DIR/.dual-ai-collab/checkpoints/state.json"
result=$(bash "$PROJECT_DIR/skill/scripts/check_checkpoint.sh" 2>&1)
assert_contains "$result" "CHECKPOINT_CORRUPTED"
assert_contains "$result" "state.json.corrupted"
assert_file_exists "$TEST_DIR/.dual-ai-collab/checkpoints/state.json.corrupted"
teardown_test_env

setup_test_env
it "write_checkpoint.sh 更新多行 JSON 时应保持有效"
cd "$TEST_DIR"
cat > "$TEST_DIR/.dual-ai-collab/checkpoints/state.json" << 'EOF'
{
  "phase": "developing",
  "updated_at": "2026-03-17T00:00:00Z",
  "current_task": "001"
}
EOF
bash "$PROJECT_DIR/skill/scripts/write_checkpoint.sh" fixing fix_round=2 > /dev/null 2>&1
python3 -c 'import json, sys; json.load(open(sys.argv[1], encoding="utf-8"))' "$TEST_DIR/.dual-ai-collab/checkpoints/state.json"
assert_exit_code 0 $?
teardown_test_env

setup_test_env
it "write_checkpoint.sh 应正确转义带引号的值"
cd "$TEST_DIR"
bash "$PROJECT_DIR/skill/scripts/write_checkpoint.sh" developing spec_file='specs/"demo".md' > /dev/null 2>&1
python3 - "$TEST_DIR/.dual-ai-collab/checkpoints/state.json" << 'EOF'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    data = json.load(fh)

assert data["spec_file"] == 'specs/"demo".md'
EOF
assert_exit_code 0 $?
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
it "detect_stall.sh 读取 exit 文件后应返回 SUCCESS"
mkdir -p "$TEST_DIR/.dual-ai-collab/logs"
sleep 1 &
PID_TO_EXIT=$!
wait $PID_TO_EXIT 2>/dev/null || true
echo "0" > "$TEST_DIR/.dual-ai-collab/logs/task-001.exit"
echo "$PID_TO_EXIT" > "$TEST_DIR/.dual-ai-collab/logs/task-001.pid"
touch "$TEST_DIR/.dual-ai-collab/logs/task-001.log"
cd "$TEST_DIR"
result=$(bash "$PROJECT_DIR/skill/scripts/detect_stall.sh" 001 $PID_TO_EXIT 2>&1)
assert_contains "$result" "SUCCESS"
teardown_test_env

setup_test_env
it "detect_stall.sh 遇到非法 PID 应返回命令式错误"
cd "$TEST_DIR"
result=$(bash "$PROJECT_DIR/skill/scripts/detect_stall.sh" 001 not-a-pid 2>&1)
exit_code=$?
if [ $exit_code -eq 0 ]; then
    fail "非法 PID 应返回非零退出码"
else
    pass
fi
assert_contains "$result" "ERROR: 非法 PID"
assert_not_contains "$result" "Traceback"
teardown_test_env

setup_test_env
it "detect_stall.sh 不应因不匹配的 pid 文件误信旧 exit 文件"
mkdir -p "$TEST_DIR/.dual-ai-collab/logs"
echo "0" > "$TEST_DIR/.dual-ai-collab/logs/task-001.exit"
echo "12345" > "$TEST_DIR/.dual-ai-collab/logs/task-001.pid"
touch "$TEST_DIR/.dual-ai-collab/logs/task-001.log"
cd "$TEST_DIR"
result=$(bash "$PROJECT_DIR/skill/scripts/detect_stall.sh" 001 999999 2>&1)
assert_contains "$result" "FAILED"
assert_not_contains "$result" "SUCCESS"
teardown_test_env

setup_test_env
it "detect_stall.sh 应支持任务级卡死阈值"
mkdir -p "$TEST_DIR/.dual-ai-collab/logs" "$TEST_DIR/planning"
cat > "$TEST_DIR/planning/codex-tasks.md" << 'EOF'
## 任务 #001: 长任务

**状态**: OPEN
**卡死阈值**: 10m

---
EOF
touch "$TEST_DIR/.dual-ai-collab/logs/task-001.log"
sleep 5 &
LIVE_PID=$!
cd "$TEST_DIR"
bash "$PROJECT_DIR/skill/scripts/detect_stall.sh" 001 $LIVE_PID "$TEST_DIR/planning/codex-tasks.md" > /dev/null 2>&1
assert_file_exists "$TEST_DIR/.dual-ai-collab/logs/task-001.stall-state"
kill "$LIVE_PID" 2>/dev/null || true
teardown_test_env

# ═══════════════════════════════════════════
# run_task.sh 测试
# ═══════════════════════════════════════════

setup_test_env
it "run_task.sh start 应转调执行器并创建运行记录"
mkdir -p "$TEST_DIR/.dual-ai-collab/logs" "$TEST_DIR/.dual-ai-collab/runs" "$TEST_DIR/bin"
cat > "$TEST_DIR/bin/codex" << 'EOF'
#!/bin/bash
sleep 5
echo "stub codex"
EOF
chmod +x "$TEST_DIR/bin/codex"
cd "$TEST_DIR"
result=$(PATH="$TEST_DIR/bin:$PATH" bash "$PROJECT_DIR/skill/scripts/run_task.sh" start 001 "测试提示词" 2>&1)
assert_contains "$result" '"backend": "direct"'
assert_contains "$result" '"task_num": "001"'
assert_file_exists "$TEST_DIR/.dual-ai-collab/runs/task-001.json"
assert_file_exists "$TEST_DIR/.dual-ai-collab/logs/task-001.pid"
pid=$(cat "$TEST_DIR/.dual-ai-collab/logs/task-001.pid")
kill "$pid" 2>/dev/null || true
teardown_test_env

# ═══════════════════════════════════════════
# verify_task.sh 测试
# ═══════════════════════════════════════════

setup_test_env
it "verify_task.sh extract 应提取带反引号的验收命令"
mkdir -p "$TEST_DIR/planning"
cat > "$TEST_DIR/planning/codex-tasks.md" << 'EOF'
## 任务 #001: 带命令的验收

**状态**: OPEN

### 验收标准
- [ ] `bash tests/run_all_tests.sh` 全部通过
- [ ] `python3 -c "print('ok')"` 不报错
- [ ] 页面符合预期

---
EOF
result=$(cd "$TEST_DIR" && bash "$PROJECT_DIR/skill/scripts/verify_task.sh" extract 001 "$TEST_DIR/planning/codex-tasks.md" 2>&1)
assert_contains "$result" "bash tests/run_all_tests.sh"
assert_contains "$result" "python3 -c \"print('ok')\""
assert_not_contains "$result" "页面符合预期"
teardown_test_env

setup_test_env
it "verify_task.sh run 应顺序执行验收命令并返回通过"
mkdir -p "$TEST_DIR/planning"
cat > "$TEST_DIR/planning/codex-tasks.md" << 'EOF'
## 任务 #001: 运行验收

**状态**: OPEN

### 验收标准
- [ ] `python3 -c "from pathlib import Path; Path('verified.txt').write_text('ok', encoding='utf-8')"` 生成文件
- [ ] `test -f verified.txt` 文件存在

---
EOF
result=$(cd "$TEST_DIR" && bash "$PROJECT_DIR/skill/scripts/verify_task.sh" run 001 "$TEST_DIR/planning/codex-tasks.md" 2>&1)
assert_contains "$result" "VERIFY_PASSED"
assert_file_exists "$TEST_DIR/verified.txt"
teardown_test_env

setup_test_env
it "verify_task.sh run 遇到失败命令应返回非零退出码"
mkdir -p "$TEST_DIR/planning"
cat > "$TEST_DIR/planning/codex-tasks.md" << 'EOF'
## 任务 #001: 失败验收

**状态**: OPEN

### 验收标准
- [ ] `python3 -c "raise SystemExit(3)"` 明确失败

---
EOF
result=$(cd "$TEST_DIR" && bash "$PROJECT_DIR/skill/scripts/verify_task.sh" run 001 "$TEST_DIR/planning/codex-tasks.md" 2>&1)
exit_code=$?
if [ $exit_code -eq 0 ]; then
    fail "失败验收命令应返回非零退出码"
else
    pass
fi
assert_contains "$result" "VERIFY_FAILED"
teardown_test_env

setup_test_env
it "verify_task.sh run 没有可执行验收命令时应拒绝通过"
mkdir -p "$TEST_DIR/planning"
cat > "$TEST_DIR/planning/codex-tasks.md" << 'EOF'
## 任务 #001: 纯文字验收

**状态**: OPEN

### 验收标准
- [ ] 页面符合产品要求
- [ ] 交互手感自然

---
EOF
result=$(cd "$TEST_DIR" && bash "$PROJECT_DIR/skill/scripts/verify_task.sh" run 001 "$TEST_DIR/planning/codex-tasks.md" 2>&1)
exit_code=$?
if [ $exit_code -eq 0 ]; then
    fail "没有可执行验收命令时不应返回成功"
else
    pass
fi
assert_contains "$result" "NO_VERIFICATION_COMMANDS"
teardown_test_env

setup_test_env
it "run_task.sh status 应报告 running"
mkdir -p "$TEST_DIR/.dual-ai-collab/logs"
sleep 10 &
LIVE_PID=$!
echo "$LIVE_PID" > "$TEST_DIR/.dual-ai-collab/logs/task-001.pid"
cd "$TEST_DIR"
result=$(bash "$PROJECT_DIR/skill/scripts/run_task.sh" status 001 2>&1)
assert_contains "$result" "running"
kill "$LIVE_PID" 2>/dev/null || true
teardown_test_env

setup_test_env
it "run_task.sh stop 应终止任务并清理 pid 文件"
mkdir -p "$TEST_DIR/.dual-ai-collab/logs"
sleep 10 &
LIVE_PID=$!
echo "$LIVE_PID" > "$TEST_DIR/.dual-ai-collab/logs/task-001.pid"
cd "$TEST_DIR"
result=$(bash "$PROJECT_DIR/skill/scripts/run_task.sh" stop 001 2>&1)
assert_contains "$result" "stopped"
if kill -0 "$LIVE_PID" 2>/dev/null; then
    fail "任务进程仍在运行"
    kill "$LIVE_PID" 2>/dev/null || true
else
    pass
fi
if [ -f "$TEST_DIR/.dual-ai-collab/logs/task-001.pid" ]; then
    fail "pid 文件未清理"
else
    pass
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

# ═══════════════════════════════════════════
# detect_stall.sh .pid 缺失场景
# ═══════════════════════════════════════════

setup_test_env
it "detect_stall.sh 无 .pid 文件时不应误信残留 .exit 文件"
mkdir -p "$TEST_DIR/.dual-ai-collab/logs"
# 只留旧 exit 文件（exit code 0），不给 pid 文件
echo "0" > "$TEST_DIR/.dual-ai-collab/logs/task-001.exit"
touch "$TEST_DIR/.dual-ai-collab/logs/task-001.log"
# 不创建 .pid 文件
cd "$TEST_DIR"
result=$(bash "$PROJECT_DIR/skill/scripts/detect_stall.sh" 001 999999 2>&1)
# 应该返回 FAILED（不信任 exit=0），不应返回 SUCCESS
assert_contains "$result" "FAILED"
assert_not_contains "$result" "SUCCESS"
teardown_test_env

# ═══════════════════════════════════════════
# summarize_progress.sh 测试
# ═══════════════════════════════════════════

setup_test_env
it "summarize_progress.sh 应正确统计各状态"
mkdir -p "$TEST_DIR/planning"
cat > "$TEST_DIR/planning/codex-tasks.md" << 'EOF'
## 任务 #001: 任务A

**状态**: OPEN
**优先级**: P1

---

## 任务 #002: 任务B

**状态**: DONE
**优先级**: P1

---

## 任务 #003: 任务C

**状态**: VERIFIED
**优先级**: P2

---
EOF
result=$(bash "$PROJECT_DIR/skill/scripts/summarize_progress.sh" "$TEST_DIR/planning/codex-tasks.md" 2>&1)
assert_contains "$result" "总任务: 3"
assert_contains "$result" "OPEN: 1"
assert_contains "$result" "DONE: 1"
assert_contains "$result" "VERIFIED: 1"
teardown_test_env

setup_test_env
it "summarize_progress.sh 应统计 FAILED 状态"
mkdir -p "$TEST_DIR/planning"
cat > "$TEST_DIR/planning/codex-tasks.md" << 'EOF'
## 任务 #001: 失败任务

**状态**: FAILED
**优先级**: P1

---

## 任务 #002: 已验收

**状态**: VERIFIED
**优先级**: P2

---
EOF
result=$(bash "$PROJECT_DIR/skill/scripts/summarize_progress.sh" "$TEST_DIR/planning/codex-tasks.md" 2>&1)
assert_contains "$result" "FAILED: 1"
assert_contains "$result" "VERIFIED: 1"
teardown_test_env

setup_test_env
it "summarize_progress.sh 对缺少状态字段的任务应发出警告"
mkdir -p "$TEST_DIR/planning"
cat > "$TEST_DIR/planning/codex-tasks.md" << 'EOF'
## 任务 #001: 正常任务

**状态**: OPEN
**优先级**: P1

---

## 任务 #002: 缺少状态

**优先级**: P1

---
EOF
result=$(bash "$PROJECT_DIR/skill/scripts/summarize_progress.sh" "$TEST_DIR/planning/codex-tasks.md" 2>&1)
assert_contains "$result" "WARNING"
assert_contains "$result" "总任务: 1"
teardown_test_env

setup_test_env
it "summarize_progress.sh --report 应生成报告文件"
mkdir -p "$TEST_DIR/planning"
cat > "$TEST_DIR/planning/codex-tasks.md" << 'EOF'
## 任务 #001: 任务A

**状态**: VERIFIED
**优先级**: P1

---
EOF
cd "$TEST_DIR"
result=$(bash "$PROJECT_DIR/skill/scripts/summarize_progress.sh" --report "$TEST_DIR/planning/codex-tasks.md" 2>&1)
assert_contains "$result" "报告已写入"
# 检查报告文件存在
report_count=$(ls "$TEST_DIR/planning/progress-reports/"*.md 2>/dev/null | wc -l)
if [ "$report_count" -ge 1 ]; then
    pass
else
    fail "未找到报告文件"
fi
teardown_test_env

# ═══════════════════════════════════════════
# init_env.sh 测试
# ═══════════════════════════════════════════

setup_test_env
it "init_env.sh 应创建所有必要目录并输出 ENV_READY"
cd "$TEST_DIR"
result=$(bash "$PROJECT_DIR/skill/scripts/init_env.sh" 2>&1)
assert_contains "$result" "ENV_READY"
if [ -d "$TEST_DIR/planning/specs" ] && [ -d "$TEST_DIR/planning/audit-reports" ] && \
   [ -d "$TEST_DIR/.dual-ai-collab/logs" ] && [ -d "$TEST_DIR/.dual-ai-collab/checkpoints" ]; then
    pass
else
    fail "部分目录未创建"
fi
teardown_test_env

# 打印总结
print_summary
