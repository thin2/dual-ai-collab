#!/bin/bash

################################################################################
# Claude 需求访谈和任务规划脚本
# 功能：通过深入访谈收集需求，生成规范文档，然后创建任务板
################################################################################

set -e

PROJECT_ROOT="${PROJECT_ROOT:-$(pwd)}"
SPECS_DIR="${SPECS_DIR:-planning/specs}"
TASKS_FILE="${TASKS_FILE:-planning/codex-tasks.md}"

# 颜色
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $1"
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

show_usage() {
    echo -e "${BLUE}Claude 需求访谈和任务规划脚本${NC}"
    echo ""
    echo "用法:"
    echo "  $0 [需求名称]"
    echo ""
    echo "示例:"
    echo "  $0 \"用户认证系统\""
    echo "  $0 \"博客管理功能\""
    echo ""
    echo "工作流程:"
    echo "  1. Claude 对你进行深入访谈"
    echo "  2. 生成详细的需求规范文档"
    echo "  3. 根据规范拆分任务"
    echo "  4. 写入任务板"
}

# 主程序
main() {
    if [ -z "$1" ]; then
        show_usage
        exit 1
    fi

    local requirement_name="$1"
    local timestamp=$(date '+%Y%m%d-%H%M%S')
    local spec_file="$SPECS_DIR/${timestamp}-${requirement_name// /-}.md"

    log "🎯 开始需求访谈流程"
    log "需求名称: $requirement_name"
    log ""

    # 创建目录
    mkdir -p "$SPECS_DIR"

    info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    info "第 1 步：深入访谈"
    info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Claude 将通过 AskUserQuestion 工具对你进行深入访谈。"
    echo "访谈内容涉及："
    echo "  - 技术实现细节"
    echo "  - 用户界面与用户体验"
    echo "  - 关注点和优先级"
    echo "  - 权衡取舍"
    echo "  - 边界情况和异常处理"
    echo ""
    echo "请准备好回答问题..."
    echo ""
    read -p "按 Enter 继续..."

    echo ""
    info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    info "访谈完成后，Claude 会："
    info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  1. 生成需求规范文档: $spec_file"
    echo "  2. 根据规范拆分任务"
    echo "  3. 写入任务板: $TASKS_FILE"
    echo ""

    log "✅ 准备就绪，请在 Claude 中继续访谈流程"
}

main "$@"
