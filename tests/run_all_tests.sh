#!/bin/bash
################################################################################
# 一键运行所有测试
################################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🧪 Dual AI Collaboration - 自动化测试套件${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

TOTAL_PASS=0
TOTAL_FAIL=0
TOTAL_RUN=0
FAILED_SUITES=""

run_test_suite() {
    local test_file="$1"
    local test_name="$2"

    echo -e "${BLUE}▶ 运行: $test_name${NC}"

    # 运行测试并捕获输出
    local output
    local exit_code=0
    output=$(bash "$test_file" 2>&1) || exit_code=$?

    echo "$output"

    # 解析测试结果
    local passed=$(echo "$output" | grep -c "✅" || true)
    local failed=$(echo "$output" | grep -c "❌" || true)

    # 如果脚本异常退出（exit_code != 0），强制记为失败
    if [ $exit_code -ne 0 ]; then
        echo -e "${RED}⚠️  测试套件异常退出（exit code: $exit_code）${NC}"
        failed=$((failed + 1))
        FAILED_SUITES="$FAILED_SUITES\n  - $test_name (异常退出: exit code $exit_code)"
    elif [ $failed -gt 0 ]; then
        FAILED_SUITES="$FAILED_SUITES\n  - $test_name ($failed 个失败)"
    fi

    TOTAL_PASS=$((TOTAL_PASS + passed))
    TOTAL_FAIL=$((TOTAL_FAIL + failed))
    TOTAL_RUN=$((TOTAL_RUN + passed + failed))

    echo ""
}

# 运行所有测试套件
run_test_suite "$SCRIPT_DIR/test_find_task.sh" "任务领取和优先级调度"
run_test_suite "$SCRIPT_DIR/test_update_status.sh" "状态转换"
run_test_suite "$SCRIPT_DIR/test_statistics.sh" "统计报告输出"
run_test_suite "$SCRIPT_DIR/test_start_stop.sh" "启动/停止流程"
run_test_suite "$SCRIPT_DIR/test_dependencies.sh" "任务依赖管理（v2.1.0）"
run_test_suite "$SCRIPT_DIR/test_parallel.sh" "并行任务识别（v2.1.0）"
run_test_suite "$SCRIPT_DIR/test_progress.sh" "进度统计报告（v2.1.0）"

# 总结
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}📊 总测试结果${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  测试套件:  7"
echo -e "  总用例数:  $TOTAL_RUN"
echo -e "  ${GREEN}通过:      $TOTAL_PASS${NC}"
echo -e "  ${RED}失败:      $TOTAL_FAIL${NC}"
echo ""

if [ $TOTAL_FAIL -eq 0 ]; then
    echo -e "${GREEN}🎉 所有 $TOTAL_RUN 个测试全部通过！${NC}"
    echo ""
    exit 0
else
    echo -e "${RED}💥 有 $TOTAL_FAIL 个测试失败：${NC}"
    echo -e "$FAILED_SUITES"
    echo ""
    exit 1
fi
