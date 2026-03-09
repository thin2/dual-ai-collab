#!/bin/bash
# install.sh - Dual AI Collaboration 一键安装脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🚀 Dual AI Collaboration Framework 安装${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# 1. 安装 Skill 到 Claude Code
echo -e "${BLUE}[1/6] 安装 Skill...${NC}"
mkdir -p ~/.claude/skills
if [ -f ~/.claude/skills/dual-ai-collab.md ]; then
    echo -e "${YELLOW}⚠️  Skill 已存在，正在更新...${NC}"
fi
cp skill/dual-ai-collab.md ~/.claude/skills/
echo -e "${GREEN}✅ Skill 已安装到 ~/.claude/skills/${NC}"
echo ""

# 2. 创建配置文件
echo -e "${BLUE}[2/6] 创建配置文件...${NC}"
if [ ! -f .dual-ai-collab.yml ]; then
    cp templates/.dual-ai-collab.yml .dual-ai-collab.yml
    echo -e "${GREEN}✅ 配置文件已创建${NC}"
else
    echo -e "${YELLOW}⚠️  配置文件已存在，跳过${NC}"
fi
echo ""

# 3. 创建 .gitignore
echo -e "${BLUE}[3/6] 检查 .gitignore...${NC}"
if [ ! -f .gitignore ]; then
    cat > .gitignore <<'EOF'
# Dual AI Collab
.dual-ai-collab/logs/
.dual-ai-collab/checkpoints/
.dual-ai-collab/tmp/
*.pid

# OMC
.omc/

# OS
.DS_Store
Thumbs.db

# Editors
.vscode/
.idea/
*.swp
*.swo
*~

# Logs
*.log
logs/

# Temporary files
tmp/
temp/
*.tmp
EOF
    echo -e "${GREEN}✅ .gitignore 已创建${NC}"
else
    echo -e "${YELLOW}⚠️  .gitignore 已存在，跳过${NC}"
fi
echo ""

# 4. 创建必要的目录
echo -e "${BLUE}[4/6] 创建目录结构...${NC}"
mkdir -p .dual-ai-collab/logs
mkdir -p .dual-ai-collab/checkpoints
mkdir -p planning/specs
echo -e "${GREEN}✅ 目录结构已创建${NC}"
echo "   - .dual-ai-collab/logs/"
echo "   - .dual-ai-collab/checkpoints/"
echo "   - planning/specs/"
echo ""

# 5. 检查依赖
echo -e "${BLUE}[5/6] 检查依赖...${NC}"
DEPS_OK=true

if command -v codex &> /dev/null; then
    CODEX_VERSION=$(codex --version 2>/dev/null || echo "未知版本")
    echo -e "${GREEN}✅ Codex CLI 已安装 ($CODEX_VERSION)${NC}"
else
    echo -e "${RED}❌ Codex CLI 未安装${NC}"
    echo -e "${YELLOW}   请运行: npm install -g @openai/codex-cli${NC}"
    echo -e "${YELLOW}   或访问: https://github.com/openai/codex-cli${NC}"
    DEPS_OK=false
fi

if command -v tmux &> /dev/null; then
    TMUX_VERSION=$(tmux -V 2>/dev/null || echo "未知版本")
    echo -e "${GREEN}✅ tmux 已安装 ($TMUX_VERSION)${NC}"
else
    echo -e "${YELLOW}⚠️  tmux 未安装（可选，但推荐安装）${NC}"
    echo -e "${YELLOW}   Ubuntu/Debian: sudo apt install tmux${NC}"
    echo -e "${YELLOW}   macOS: brew install tmux${NC}"
fi
echo ""

# 6. 验证脚本权限
echo -e "${BLUE}[6/6] 设置脚本权限...${NC}"
chmod +x scripts/*.sh
chmod +x check-env.sh
echo -e "${GREEN}✅ 脚本权限已设置${NC}"
echo ""

# 运行环境检查
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🔍 运行环境检查...${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if bash check-env.sh; then
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}🎉 安装完成！环境完全就绪！${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "${BLUE}快速开始：${NC}"
    echo ""
    echo "1️⃣  在 Claude Code 中输入魔法词："
    echo "   🤖 启动双 AI"
    echo "   🚀 开始协作"
    echo "   💬 深入访谈"
    echo ""
    echo "2️⃣  或者使用关键词："
    echo "   双 AI 协作"
    echo "   dual ai"
    echo "   codex 协作"
    echo ""
    echo "3️⃣  查看文档："
    echo "   cat QUICKSTART.md      # 5 分钟快速开始"
    echo "   cat README-USAGE.md    # 日常使用指南"
    echo "   cat INTERVIEW-GUIDE.md # 深入访谈指南"
    echo ""
    echo -e "${BLUE}示例工作流：${NC}"
    echo "   🤖 启动双 AI"
    echo "   → 告诉我你的需求"
    echo "   → 我会进行 5-10 轮深入访谈"
    echo "   → 生成详细的需求规范和任务板"
    echo "   → 你决定是否启动 Codex 自动开发"
    echo ""
    echo -e "${GREEN}祝你使用愉快！${NC}"
else
    echo ""
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}⚠️  安装完成，但环境检查发现一些问题${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "${BLUE}请根据上述提示修复问题，然后重新运行：${NC}"
    echo "   bash check-env.sh"
fi

echo ""
