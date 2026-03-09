#!/bin/bash

################################################################################
# Codex Worker 启动脚本
# 提供多种启动方式：前台、后台、tmux
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER_SCRIPT="$SCRIPT_DIR/codex-auto-worker.sh"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/.dual-ai-collab/logs"

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

show_usage() {
    echo -e "${BLUE}Codex Worker 启动脚本${NC}"
    echo ""
    echo "用法:"
    echo "  $0 [选项]"
    echo ""
    echo "选项:"
    echo "  -f, --foreground    前台运行（默认）"
    echo "  -b, --background    后台运行"
    echo "  -t, --tmux          在 tmux 会话中运行"
    echo "  -s, --stop          停止后台运行的 worker"
    echo "  -l, --logs          查看日志"
    echo "  -h, --help          显示帮助"
    echo ""
    echo "环境变量:"
    echo "  TASK_BOARD          任务板路径（默认: planning/codex-tasks.md）"
    echo "  MAX_ITERATIONS      最大迭代次数（默认: 10）"
    echo "  SLEEP_BETWEEN_TASKS 任务间隔秒数（默认: 5）"
    echo ""
    echo "示例:"
    echo "  $0 -f                    # 前台运行"
    echo "  $0 -b                    # 后台运行"
    echo "  $0 -t                    # 在 tmux 中运行"
    echo "  $0 -l                    # 查看日志"
    echo "  $0 -s                    # 停止 worker"
}

# 前台运行
run_foreground() {
    echo -e "${GREEN}🚀 启动 Codex Worker (前台模式)${NC}"
    cd "$PROJECT_ROOT"
    bash "$WORKER_SCRIPT"
}

# 后台运行
run_background() {
    echo -e "${GREEN}🚀 启动 Codex Worker (后台模式)${NC}"
    cd "$PROJECT_ROOT"

    # 确保日志目录存在
    mkdir -p "$LOG_DIR"

    # 检查是否已经在运行
    if [ -f "$LOG_DIR/codex-worker.pid" ]; then
        local pid=$(cat "$LOG_DIR/codex-worker.pid")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo -e "${YELLOW}⚠️  Codex Worker 已经在运行 (PID: $pid)${NC}"
            echo "使用 '$0 -s' 停止，或 '$0 -l' 查看日志"
            exit 1
        fi
    fi

    # 启动后台进程（先启动，再判定）
    nohup bash "$WORKER_SCRIPT" > "$LOG_DIR/codex-worker-nohup.log" 2>&1 &
    local pid=$!

    # 验证 PID 文件写入
    if ! echo $pid > "$LOG_DIR/codex-worker.pid"; then
        echo -e "${RED}❌ 启动失败：无法写入 PID 文件${NC}"
        kill "$pid" 2>/dev/null || true
        exit 1
    fi

    # 等待一小段时间，确认进程仍在运行
    sleep 1
    if ! ps -p "$pid" > /dev/null 2>&1; then
        echo -e "${RED}❌ 启动失败：进程立即退出${NC}"
        echo "查看日志了解详情: tail -n 50 $LOG_DIR/codex-worker-nohup.log"
        rm -f "$LOG_DIR/codex-worker.pid"
        exit 1
    fi

    echo -e "${GREEN}✅ Codex Worker 已启动 (PID: $pid)${NC}"
    echo "查看日志: $0 -l"
    echo "停止 worker: $0 -s"
}

# 在 tmux 中运行
run_tmux() {
    echo -e "${GREEN}🚀 启动 Codex Worker (tmux 模式)${NC}"

    # 检查 tmux 是否安装
    if ! command -v tmux &> /dev/null; then
        echo -e "${YELLOW}⚠️  tmux 未安装，请先安装 tmux${NC}"
        exit 1
    fi

    # 检查会话是否已存在
    if tmux has-session -t codex-worker 2>/dev/null; then
        echo -e "${YELLOW}⚠️  tmux 会话 'codex-worker' 已存在${NC}"
        echo "连接到会话: tmux attach -t codex-worker"
        echo "或先删除: tmux kill-session -t codex-worker"
        exit 1
    fi

    # 创建新的 tmux 会话
    cd "$PROJECT_ROOT"
    tmux new-session -d -s codex-worker "bash $WORKER_SCRIPT"

    echo -e "${GREEN}✅ Codex Worker 已在 tmux 会话中启动${NC}"
    echo "连接到会话: tmux attach -t codex-worker"
    echo "分离会话: Ctrl+B 然后按 D"
    echo "停止会话: tmux kill-session -t codex-worker"
}

# 停止后台运行的 worker
stop_worker() {
    echo -e "${YELLOW}🛑 停止 Codex Worker...${NC}"

    if [ ! -f "$LOG_DIR/codex-worker.pid" ]; then
        echo "没有找到运行中的 worker"
        exit 0
    fi

    local pid=$(cat "$LOG_DIR/codex-worker.pid")

    if ps -p "$pid" > /dev/null 2>&1; then
        kill "$pid"
        echo -e "${GREEN}✅ Codex Worker 已停止 (PID: $pid)${NC}"
        rm -f "$LOG_DIR/codex-worker.pid"
    else
        echo "Worker 进程不存在 (PID: $pid)"
        rm -f "$LOG_DIR/codex-worker.pid"
    fi
}

# 查看日志
view_logs() {
    local log_file="$LOG_DIR/worker.log"

    if [ ! -f "$log_file" ]; then
        echo "日志文件不存在: $log_file"
        exit 1
    fi

    echo -e "${BLUE}📝 Codex Worker 日志${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # 使用 tail -f 实时查看日志
    tail -f "$log_file"
}

# 主程序
main() {
    case "${1:-}" in
        -f|--foreground)
            run_foreground
            ;;
        -b|--background)
            run_background
            ;;
        -t|--tmux)
            run_tmux
            ;;
        -s|--stop)
            stop_worker
            ;;
        -l|--logs)
            view_logs
            ;;
        -h|--help|*)
            show_usage
            exit 0
            ;;
    esac
}

main "$@"
