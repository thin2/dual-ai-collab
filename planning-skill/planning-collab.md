---
name: planning-collab
description: 纯规划技能 - 访谈分级、需求规格、任务板生成、规划审计、用户确认，产出物兼容 dual-ai-collab
---

# Planning Collaboration Skill

目标：Claude 负责需求澄清、规划、审计和确认。产出物（规格文档 + 任务板）格式兼容 dual-ai-collab，可直接衔接任何执行方式。

## 启动前

将下文中的 `<skill-dir>` 替换为实际安装目录。
- Linux / macOS 常见路径：`~/.claude/skills/planning-collab`
- Windows 常见路径：`%USERPROFILE%\.claude\skills\planning-collab`

```bash
python "<skill-dir>/scripts/cli.py" init
python "<skill-dir>/scripts/cli.py" checkpoint-check
```

解释：
- `CHECKPOINT_FOUND`：按恢复指引继续
- `CHECKPOINT_CORRUPTED`：检查任务板状态，推断阶段后继续
- `NO_CHECKPOINT`：从复杂度判断开始

## 核心原则

1. 先判断复杂度，再决定访谈深度和流程重量。
2. 任务真相源是 `planning/tasks.json`；`planning/codex-tasks.md` 是渲染视图。
3. 规划文档必须先审计，再让用户确认，确认后才算完成。
4. 缺信息时明确指出"缺什么、影响什么"，不硬猜。

## 第 1 步：复杂度判断

先判断复杂度，再决定访谈深度：
- 简单：2-3 轮。例：修 bug、小按钮、小工具函数。
- 中等：4-6 轮。例：新页面、一组接口、一个中等模块。
- 复杂：6-10 轮。例：认证、支付、权限、数据迁移、跨模块重构。

模板见 [prompt-templates.md](./references/prompt-templates.md) 1.0

## 第 2 步：访谈

按复杂度分级进行访谈，持续到关键维度覆盖、无明显遗漏为止。

规则和规格模板见 [interview.md](./references/interview.md)

## 第 3 步：规格与任务板

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
python "<skill-dir>/scripts/cli.py" select
python "<skill-dir>/scripts/cli.py" summary
```

规范见 [task-board.md](./references/task-board.md)

## 第 4 步：规划审计

Claude 先主审，必要时让其他 AI 只做补漏，不重复整份审计。

检查重点：
- 用户目标覆盖
- 任务拆分可执行性
- 依赖顺序
- 验收标准可验证性
- 风险与边界记录

模板见 [prompt-templates.md](./references/prompt-templates.md) 1.1 / 1.2

## 第 5 步：用户确认

让用户明确回复：
1. 开始开发
2. 修改规划
3. 取消

模板见 [prompt-templates.md](./references/prompt-templates.md) 1.3

确认后写入 checkpoint：

```bash
python "<skill-dir>/scripts/cli.py" checkpoint-write user_approved spec_file=[路径] task_file=planning/codex-tasks.md total_tasks=[数量]
```

## Checkpoint 与恢复

| phase | 含义 | 恢复动作 |
|-------|------|----------|
| `interview` | 访谈进行中 | 读取已收集信息，继续访谈 |
| `spec_generated` | 规格已生成 | 跳到任务板生成 |
| `tasks_created` | 任务板已生成 | 跳到规划审计 |
| `user_approved` | 用户已确认 | 规划完成，可交付执行 |

恢复步骤：
1. 读取 `.planning-collab/checkpoints/state.json`
2. 根据 phase 确定恢复动作
3. 向用户报告恢复状态后继续

## Claude 的执行要求

1. 简单需求走轻流程（2-3 轮访谈 + 快速审计），复杂需求走重流程。
2. 只按需读取 reference，不要每次全量加载。
3. 产出物必须与 dual-ai-collab 任务板格式兼容。

## 安装

```bash
git clone https://github.com/thin2/dual-ai-collab.git
cd dual-ai-collab
python install.py --skill planning
```

触发词：
- 规划
- planning
- 需求分析
- 任务规划
