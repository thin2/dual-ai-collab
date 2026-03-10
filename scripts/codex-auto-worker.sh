#!/bin/bash

################################################################################
# Codex 自动化工作脚本
# 功能：自动读取任务板，领取 OPEN 任务，完成开发，更新状态
################################################################################

set -euo pipefail

# 配置
TASK_BOARD="${TASK_BOARD:-planning/codex-tasks.md}"
PROJECT_ROOT="${PROJECT_ROOT:-$(pwd)}"
LOG_FILE="${LOG_FILE:-.dual-ai-collab/logs/worker.log}"
MAX_ITERATIONS="${MAX_ITERATIONS:-10}"
SLEEP_BETWEEN_TASKS="${SLEEP_BETWEEN_TASKS:-5}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$LOG_FILE"
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARN:${NC} $1" | tee -a "$LOG_FILE"
}

info() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')] INFO:${NC} $1" | tee -a "$LOG_FILE"
}

# 初始化
init() {
    # 创建日志目录（必须在任何日志输出前）
    mkdir -p "$(dirname "$LOG_FILE")"

    log "🤖 Codex Auto Worker 启动..."

    # 检查任务板是否存在
    if [ ! -f "$TASK_BOARD" ]; then
        error "任务板不存在: $TASK_BOARD"
        exit 1
    fi

    # 检查 codex 命令是否可用
    if ! command -v codex &> /dev/null; then
        error "codex 命令不可用，请先安装"
        exit 1
    fi

    log "✅ 初始化完成"
    log "📋 任务板: $TASK_BOARD"
    log "📁 项目根目录: $PROJECT_ROOT"
    log "📝 日志文件: $LOG_FILE"
}

# 查找下一个 OPEN 任务（按优先级）
find_next_task() {
    local task_file="$1"

    # 在 awk 内完成优先级选择，直接输出单个完整任务块
    awk '
        BEGIN { task_count = 0 }
        /## 任务 #[0-9]+:/ {
            if (in_task && task_content ~ /状态.*: OPEN/) {
                # 保存当前任务
                tasks[task_count] = task_header "\n" task_content
                priorities[task_count] = priority
                task_count++
            }
            in_task = 1
            task_header = $0
            task_content = ""
            priority = 9  # 默认最低优先级
            next
        }
        in_task && /^---$/ {
            if (task_content ~ /状态.*: OPEN/) {
                # 保存最后一个任务
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
            # 提取优先级
            if ($0 ~ /优先级.*: P1/) {
                priority = 1
            } else if ($0 ~ /优先级.*: P2/) {
                priority = 2
            } else if ($0 ~ /优先级.*: P3/) {
                priority = 3
            }
        }
        END {
            # 找出最高优先级（数字最小）的任务
            if (task_count > 0) {
                min_priority = 9
                min_index = -1
                for (i = 0; i < task_count; i++) {
                    if (priorities[i] < min_priority) {
                        min_priority = priorities[i]
                        min_index = i
                    }
                }
                if (min_index >= 0) {
                    print tasks[min_index]
                }
            }
        }
    ' "$task_file"
}

# 提取任务 ID
extract_task_id() {
    local task_header="$1"
    echo "$task_header" | grep -oP '任务 #\K\d+'
}

# 更新任务状态
update_task_status() {
    local task_id="$1"
    local old_status="$2"
    local new_status="$3"
    local task_file="$4"

    # 使用 sed 更新状态
    sed -i "/## 任务 #${task_id}:/,/^---$/ s/\*\*状态\*\*: ${old_status}/\*\*状态\*\*: ${new_status}/" "$task_file"

    log "📝 任务 #${task_id} 状态更新: ${old_status} → ${new_status}"
}

# 执行任务
execute_task() {
    local task_content="$1"
    local task_id="$2"

    log "🔧 开始执行任务 #${task_id}..."

    # 构建 Codex 提示词
    local prompt="你是一个专业的开发工程师，正在执行以下任务：

${task_content}

工作要求：
1. 仔细阅读任务描述、技术要求和验收标准
2. 在项目根目录 ${PROJECT_ROOT} 中工作
3. 编写高质量、可维护的代码
4. 添加必要的注释和文档
5. 确保代码符合最佳实践
6. 满足所有验收标准

重要提示：
- 只编写代码，不要进行审计或测试（这是 Claude 的工作）
- 完成后直接保存文件即可
- 不需要更新任务板状态（脚本会自动更新）

现在开始工作！"

    # 调用 Codex
    info "调用 Codex CLI..."

    # 将提示词保存到临时文件
    local temp_prompt="/tmp/codex-prompt-${task_id}.txt"
    echo "$prompt" > "$temp_prompt"

    # 执行 Codex（显式捕获退出码）
    local exit_code=0
    codex --cwd "$PROJECT_ROOT" "$(cat "$temp_prompt")" 2>&1 | tee -a "$LOG_FILE" || exit_code=$?

    rm -f "$temp_prompt"

    if [ $exit_code -eq 0 ]; then
        log "✅ 任务 #${task_id} 执行成功"
        return 0
    else
        error "任务 #${task_id} 执行失败（退出码：$exit_code）"
        return 1
    fi
}

# 主循环
main() {
    init

    local iteration=0

    while [ $iteration -lt $MAX_ITERATIONS ]; do
        iteration=$((iteration + 1))

        log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        log "🔄 第 ${iteration} 轮迭代"

        # 查找下一个任务
        local task_info=$(find_next_task "$TASK_BOARD")

        if [ -z "$task_info" ]; then
            log "🎉 所有任务已完成！没有更多 OPEN 状态的任务"
            break
        fi

        # 提取任务 ID
        local task_header=$(echo "$task_info" | head -n 1)
        local task_id=$(extract_task_id "$task_header")

        if [ -z "$task_id" ]; then
            error "无法提取任务 ID"
            continue
        fi

        log "📋 领取任务 #${task_id}"

        # 更新状态为 IN_PROGRESS
        update_task_status "$task_id" "OPEN" "IN_PROGRESS" "$TASK_BOARD"

        # 执行任务
        if execute_task "$task_info" "$task_id"; then
            # 更新状态为 DONE
            update_task_status "$task_id" "IN_PROGRESS" "DONE" "$TASK_BOARD"
            log "✅ 任务 #${task_id} 已完成，等待 Claude 审计"
        else
            # 执行失败，恢复为 OPEN
            update_task_status "$task_id" "IN_PROGRESS" "OPEN" "$TASK_BOARD"
            error "任务 #${task_id} 执行失败，已恢复为 OPEN 状态"
        fi

        # 等待一段时间再处理下一个任务
        if [ $iteration -lt $MAX_ITERATIONS ]; then
            info "⏳ 等待 ${SLEEP_BETWEEN_TASKS} 秒后处理下一个任务..."
            sleep $SLEEP_BETWEEN_TASKS
        fi
    done

    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "🏁 Codex Auto Worker 完成"
    log "📊 总共处理了 ${iteration} 个任务"

    # 生成统计报告
    generate_report
}

# 生成统计报告
generate_report() {
    # 使用 awk 计数，避免 grep -c 的退出码问题
    local total=$(awk '/## 任务 #/ {count++} END {print count+0}' "$TASK_BOARD")
    local open=$(awk '/\*\*状态\*\*: OPEN|状态: OPEN/ {count++} END {print count+0}' "$TASK_BOARD")
    local in_progress=$(awk '/\*\*状态\*\*: IN_PROGRESS|状态: IN_PROGRESS/ {count++} END {print count+0}' "$TASK_BOARD")
    local done=$(awk '/\*\*状态\*\*: DONE|状态: DONE/ {count++} END {print count+0}' "$TASK_BOARD")
    local verified=$(awk '/\*\*状态\*\*: VERIFIED|状态: VERIFIED/ {count++} END {print count+0}' "$TASK_BOARD")
    local rejected=$(awk '/\*\*状态\*\*: REJECTED|状态: REJECTED/ {count++} END {print count+0}' "$TASK_BOARD")

    log ""
    log "📊 任务统计报告"
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "总任务数:     ${total}"
    log "待开始:       ${open}"
    log "进行中:       ${in_progress}"
    log "已完成:       ${done} (等待审计)"
    log "已验收:       ${verified}"
    log "被拒绝:       ${rejected}"
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# 捕获退出信号
trap 'log "⚠️  收到退出信号，正在清理..."; exit 0' SIGINT SIGTERM

# 运行主程序
main
