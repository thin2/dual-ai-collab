---
name: dual-ai-collab
description: 双 AI 协作开发模式 - Claude 负责访谈、规划、门控和审计，Codex/Claude 执行实现，支持恢复、验证和分级流程
---

# Dual AI Collaboration Skill

目标：Claude 负责需求澄清、规划、门控和审计；Codex 优先负责实现；Codex 不可用时自动降级为 Claude-only。

## 启动前

```bash
SKILL_DIR="$HOME/.claude/skills/dual-ai-collab"
python3 "$SKILL_DIR/scripts/task_manager.py" init
python3 "$SKILL_DIR/scripts/task_manager.py" checkpoint-check
command -v codex && echo "CODEX_OK" || echo "CODEX_MISSING"
```

解释：
- `CHECKPOINT_FOUND` / `CHECKPOINT_CORRUPTED`：按 [recovery.md](./references/recovery.md) 恢复
- `NO_CHECKPOINT`：从访谈开始
- `CODEX_MISSING`：不要中断，改走 Claude-only

## 核心原则

1. 先规划，后开发；规划先审计，再让用户确认。
2. 任务真相源是 `planning/tasks.json`；`planning/codex-tasks.md` 是渲染视图。
3. 验收命令必须执行，通过后才可标记 `DONE`。
4. 访谈、前端设计、审计都按复杂度分级。
5. 用户可读反馈由 Claude 负责翻译，脚本输出保持程序化。

## 第 1 步：访谈

先判断复杂度，再决定访谈深度：
- 简单：2-3 轮。例：修 bug、小按钮、小工具函数。
- 中等：4-6 轮。例：新页面、一组接口、一个中等模块。
- 复杂：6-10 轮。例：认证、支付、权限、数据迁移、跨模块重构。
- 规则和规格模板见 [interview.md](./references/interview.md)

## 第 2 步：规格与任务板

输出：
- `planning/specs/YYYYMMDD-HHMMSS-[功能名称].md`
- `planning/tasks.json`
- `planning/codex-tasks.md`

要求：
- 每个任务 1-3 小时
- 验收标准尽量可执行
- 依赖关系明确

常用命令：

```bash
python3 "$SKILL_DIR/scripts/task_manager.py" select
python3 "$SKILL_DIR/scripts/task_manager.py" summary
```

规范见 [task-board.md](./references/task-board.md)

## 第 3 步：规划审计与确认

Claude 先主审，必要时让 Codex 只做补漏，不重复整份审计。

检查重点：
- 用户目标覆盖
- 任务拆分可执行性
- 依赖顺序
- 验收标准可验证性
- 风险与边界记录

然后让用户明确回复：
1. 开始开发
2. 修改规划
3. 取消

模板见 [prompt-templates.md](./references/prompt-templates.md)

## 第 4 步：执行模式

### Codex 模式

适用：`codex` 可用，且任务适合后台执行。

```bash
python3 "$SKILL_DIR/scripts/run_task.py" start XXX "任务提示词"
python3 "$SKILL_DIR/scripts/run_task.py" status XXX
python3 "$SKILL_DIR/scripts/run_task.py" stop XXX
```

### Claude-only 模式

适用：Codex CLI 不可用，或任务很小。

规则：
- Claude 直接阅读任务和代码并同步实现
- 仍然执行验收命令和审计
- 不使用后台 worker、并行执行、`codex:rescue`

## 第 5 步：执行循环

统一流程：
1. 领取任务
2. 更新 `IN_PROGRESS`
3. 按当前模式实现
4. 运行验收命令
5. 通过后更新 `DONE`
6. 写 checkpoint

```bash
python3 "$SKILL_DIR/scripts/task_manager.py" update XXX IN_PROGRESS
python3 "$SKILL_DIR/scripts/verify_task.py" run XXX
python3 "$SKILL_DIR/scripts/task_manager.py" update XXX DONE
python3 "$SKILL_DIR/scripts/task_manager.py" checkpoint-write developing current_task=XXX completed_tasks=N
```

## 第 6 步：前端设计分级

以下情况必须先调用 `ui-ux-pro-max`：
- 新页面
- 新组件体系
- 新视觉方向
- 复杂交互 / 动效 / 高信息密度界面

以下情况可直接实现：
- CSS bug
- 间距、颜色、对齐微调
- 现有组件的小范围修复
- 不改变产品视觉方向的改动

模板见 [prompt-templates.md](./references/prompt-templates.md)

## 第 7 步：活跃度检测与失败处理

仅 Codex 模式需要：

```bash
python3 "$SKILL_DIR/scripts/task_manager.py" detect XXX "$CODEX_PID"
python3 "$SKILL_DIR/scripts/run_task.py" status XXX
python3 "$SKILL_DIR/scripts/run_task.py" stop XXX
```

卡住时先诊断根因，再决定回退或重试。排障见 [troubleshooting.md](./references/troubleshooting.md)

## 第 8 步：审计分级

- 重审计：P1、高风险、跨模块、安全/支付/认证/数据迁移、新页面核心路径
  - Spec Compliance Review
  - Code Quality Review
  - Claude 最终判定
- 标准审计：大多数 P2
  - Spec Compliance Review
  - Claude 最终判定
  - 必要时补 Code Quality Review
- 轻审计：小型 P3、局部 bugfix、工具函数、小样式修复
  - Claude 快速核验
  - 必要时升级为标准审计

规则见 [audit.md](./references/audit.md)

## 第 9 步：恢复与进度

```bash
python3 "$SKILL_DIR/scripts/task_manager.py" summary
python3 "$SKILL_DIR/scripts/task_manager.py" summary --report
cat .dual-ai-collab/checkpoints/state.json 2>/dev/null || echo "无活跃流程"
```

恢复见 [recovery.md](./references/recovery.md)

## Claude 的执行要求

1. 简单需求走轻流程，复杂需求走重流程。
2. Codex 缺失时直接切到 Claude-only，不要停在规划阶段。
3. 小型前端改动不要强制完整设计流程。
4. 小任务不要默认完整三轮审计。
5. 只按需读取 reference，不要每次全量加载。

## 安装

推荐：

```bash
git clone https://github.com/thin2/dual-ai-collab.git
cd dual-ai-collab
python install.py
```

Windows：

```bat
install.cmd
```

触发词：
- 双 AI 协作
- dual ai
- 启动协作
- 继续开发
- 审计代码
