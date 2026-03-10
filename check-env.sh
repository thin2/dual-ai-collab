#!/bin/bash
# check-env.sh - Dual AI Collaboration 环境检查脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 计数器
PASS=0
FAIL=0
WARN=0

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🔍 Dual AI Collaboration 环境检查${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# 1. 检查 Skill 安装
echo -e "${BLUE}[1/10] 检查 Skill 安装...${NC}"
if [ -f ~/.claude/skills/dual-ai-collab.md ]; then
    echo -e "${GREEN}✅ Skill 已安装到 ~/.claude/skills/${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}❌ Skill 未安装${NC}"
    echo -e "${YELLOW}   修复: cp skill/dual-ai-collab.md ~/.claude/skills/${NC}"
    FAIL=$((FAIL + 1))
fi
echo ""

# 2. 检查配置文件
echo -e "${BLUE}[2/10] 检查配置文件...${NC}"
if [ -f .dual-ai-collab.yml ]; then
    echo -e "${GREEN}✅ 配置文件存在${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${YELLOW}⚠️  配置文件不存在（可选）${NC}"
    echo -e "${YELLOW}   修复: cp templates/.dual-ai-collab.yml .${NC}"
    WARN=$((WARN + 1))
fi
echo ""

# 3. 检查 .gitignore
echo -e "${BLUE}[3/10] 检查 .gitignore...${NC}"
if [ -f .gitignore ]; then
    echo -e "${GREEN}✅ .gitignore 存在${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${YELLOW}⚠️  .gitignore 不存在（建议创建）${NC}"
    echo -e "${YELLOW}   修复: 运行 install.sh 自动创建${NC}"
    WARN=$((WARN + 1))
fi
echo ""

# 4. 检查日志目录
echo -e "${BLUE}[4/10] 检查日志目录...${NC}"
if [ -d .dual-ai-collab/logs ]; then
    echo -e "${GREEN}✅ 日志目录存在${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}❌ 日志目录不存在${NC}"
    echo -e "${YELLOW}   修复: mkdir -p .dual-ai-collab/logs${NC}"
    FAIL=$((FAIL + 1))
fi
echo ""

# 5. 检查检查点目录
echo -e "${BLUE}[5/10] 检查检查点目录...${NC}"
if [ -d .dual-ai-collab/checkpoints ]; then
    echo -e "${GREEN}✅ 检查点目录存在${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}❌ 检查点目录不存在${NC}"
    echo -e "${YELLOW}   修复: mkdir -p .dual-ai-collab/checkpoints${NC}"
    FAIL=$((FAIL + 1))
fi
echo ""

# 6. 检查规范文档目录
echo -e "${BLUE}[6/10] 检查规范文档目录...${NC}"
if [ -d planning/specs ]; then
    echo -e "${GREEN}✅ 规范文档目录存在${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}❌ 规范文档目录不存在${NC}"
    echo -e "${YELLOW}   修复: mkdir -p planning/specs${NC}"
    FAIL=$((FAIL + 1))
fi
echo ""

# 7. 检查 Codex CLI
echo -e "${BLUE}[7/10] 检查 Codex CLI...${NC}"
if command -v codex &> /dev/null; then
    CODEX_VERSION=$(codex --version 2>/dev/null || echo "未知版本")
    echo -e "${GREEN}✅ Codex CLI 已安装 ($CODEX_VERSION)${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}❌ Codex CLI 未安装${NC}"
    echo -e "${YELLOW}   修复: npm install -g @openai/codex-cli${NC}"
    echo -e "${YELLOW}   或访问: https://github.com/openai/codex-cli${NC}"
    FAIL=$((FAIL + 1))
fi
echo ""

# 8. 检查 tmux（可选）
echo -e "${BLUE}[8/10] 检查 tmux（可选）...${NC}"
if command -v tmux &> /dev/null; then
    TMUX_VERSION=$(tmux -V 2>/dev/null || echo "未知版本")
    echo -e "${GREEN}✅ tmux 已安装 ($TMUX_VERSION)${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${YELLOW}⚠️  tmux 未安装（可选，但推荐）${NC}"
    echo -e "${YELLOW}   Ubuntu/Debian: sudo apt install tmux${NC}"
    echo -e "${YELLOW}   macOS: brew install tmux${NC}"
    WARN=$((WARN + 1))
fi
echo ""

# 9. 检查脚本权限
echo -e "${BLUE}[9/10] 检查脚本权限...${NC}"
ALL_EXECUTABLE=true
for script in scripts/*.sh; do
    if [ ! -x "$script" ]; then
        echo -e "${RED}❌ $script 不可执行${NC}"
        ALL_EXECUTABLE=false
    fi
done

if [ "$ALL_EXECUTABLE" = true ]; then
    echo -e "${GREEN}✅ 所有脚本都可执行${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}❌ 部分脚本不可执行${NC}"
    echo -e "${YELLOW}   修复: chmod +x scripts/*.sh${NC}"
    FAIL=$((FAIL + 1))
fi
echo ""

# 10. 检查任务板模板
echo -e "${BLUE}[10/11] 检查任务板模板...${NC}"
if [ -f templates/codex-tasks.md ]; then
    echo -e "${GREEN}✅ 任务板模板存在${NC}"
    PASS=$((PASS + 1))
else
    echo -e "${RED}❌ 任务板模板不存在${NC}"
    echo -e "${YELLOW}   这是一个严重问题，请检查项目完整性${NC}"
    FAIL=$((FAIL + 1))
fi
echo ""

# 11. 功能性自检：验证任务领取逻辑
echo -e "${BLUE}[11/11] 功能性自检：验证任务领取逻辑...${NC}"
FUNC_TEST_DIR=$(mktemp -d)
cat > "$FUNC_TEST_DIR/test-tasks.md" <<'TASKEOF'
## 任务 #901: 低优先级测试任务

**优先级**: P3
**状态**: OPEN
**分配给**: Codex

### 任务描述
这是一个 P3 测试任务

---

## 任务 #902: 高优先级测试任务

**优先级**: P1
**状态**: OPEN
**分配给**: Codex

### 任务描述
这是一个 P1 测试任务

---

## 任务 #903: 已完成任务

**优先级**: P1
**状态**: DONE
**分配给**: Codex

### 任务描述
这是一个已完成的任务

---
TASKEOF

# 用 codex-auto-worker.sh 中相同的 awk 逻辑做自检
PICKED_TASK=$(awk '
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
' "$FUNC_TEST_DIR/test-tasks.md")

FUNC_OK=true
# 检查 1：能否领取到任务
if echo "$PICKED_TASK" | grep -q "任务 #"; then
    # 检查 2：是否优先选择了 P1 任务（#902 而非 #901）
    if echo "$PICKED_TASK" | grep -q "#902"; then
        echo -e "${GREEN}✅ 功能自检通过：正确领取 P1 优先任务 #902${NC}"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}❌ 功能自检失败：优先级调度错误（未选择 P1 任务）${NC}"
        FUNC_OK=false
        FAIL=$((FAIL + 1))
    fi
else
    echo -e "${RED}❌ 功能自检失败：无法领取 OPEN 任务${NC}"
    FUNC_OK=false
    FAIL=$((FAIL + 1))
fi
rm -rf "$FUNC_TEST_DIR"
echo ""

# 总结
TOTAL=11
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}📊 检查结果总结${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${GREEN}✅ 通过: $PASS${NC}"
echo -e "${RED}❌ 失败: $FAIL${NC}"
echo -e "${YELLOW}⚠️  警告: $WARN${NC}"
echo ""

# 评分
TOTAL=10
SCORE=$(( (PASS * 100 + TOTAL / 2) / TOTAL ))

echo -e "${BLUE}总体评分: $SCORE/100${NC}"
echo ""

# 建议
if [ $FAIL -eq 0 ] && [ $WARN -eq 0 ]; then
    echo -e "${GREEN}🎉 恭喜！环境完全就绪，可以开始使用了！${NC}"
    echo ""
    echo -e "${BLUE}快速开始：${NC}"
    echo "1. 在 Claude Code 中输入: 🤖 启动双 AI"
    echo "2. 或者输入: 双 AI 协作"
    echo "3. 查看快速开始指南: cat QUICKSTART.md"
elif [ $FAIL -eq 0 ]; then
    echo -e "${YELLOW}⚠️  环境基本就绪，但有一些可选项未配置${NC}"
    echo ""
    echo -e "${BLUE}建议：${NC}"
    echo "- 运行 bash install.sh 完成所有配置"
    echo "- 或者手动修复上述警告项"
elif [ $FAIL -le 3 ]; then
    echo -e "${YELLOW}⚠️  环境需要一些修复才能使用${NC}"
    echo ""
    echo -e "${BLUE}快速修复：${NC}"
    echo "bash install.sh"
else
    echo -e "${RED}❌ 环境存在严重问题，需要完整安装${NC}"
    echo ""
    echo -e "${BLUE}请运行：${NC}"
    echo "bash install.sh"
fi

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# 退出码
if [ $FAIL -eq 0 ]; then
    exit 0
else
    exit 1
fi
