---
name: dual-ai-collab
description: 双 AI 协作开发模式 - Claude 负责访谈、规划、门控和审计，Codex/Claude 执行实现，支持恢复、验证和分级流程
---

# Dual AI Collaboration Skill

目标：Claude 负责需求澄清、规划、门控和审计；Codex 优先负责实现；必要时可切换到 adapter backend 或 Claude-only。

## 启动前

将下文中的 `<skill-dir>` 替换为实际安装目录。
- Linux / macOS 常见路径：`~/.claude/skills/dual-ai-collab`
- Windows 常见路径：`%USERPROFILE%\.claude\skills\dual-ai-collab`

```bash
python "<skill-dir>/scripts/cli.py" init
python "<skill-dir>/scripts/cli.py" checkpoint-check
python -c "from shutil import which; print('CODEX_OK' if which('codex') else 'CODEX_MISSING')"
```

解释：
- `CHECKPOINT_FOUND` / `CHECKPOINT_CORRUPTED`：按 [recovery.md](./references/recovery.md) 恢复
- `NO_CHECKPOINT`：根据触发词决定流程
- `CODEX_MISSING`：不要中断，改走 Claude-only

## 入口分支

根据用户触发词决定走哪条流程：

**纯规划模式**（触发词：`规划`、`planning`、`需求分析`、`任务规划`）：
- 只走第 1-3 步：复杂度判断 → 访谈 → 规格与任务板 → 规划审计 → 用户确认
- 不进入执行、验收、代码审计阶段
- 产出物：`planning/specs/*.md` + `planning/tasks.json` + `planning/codex-tasks.md`
- 用户确认后流程结束，可随时用"协作"或"继续开发"触发词衔接执行

**完整协作模式**（触发词：`双 AI 协作`、`dual ai`、`启动协作`、`继续开发`、`审计代码`）：
- 走完整流程：规划 → 执行 → 验收 → 审计 → 修复

## 核心原则

1. 先判断复杂度，再决定流程重量；简单需求走轻流程，复杂需求走重流程。
2. 先规划，后开发；规划先审计，再让用户确认。
3. 任务真相源是 `planning/tasks.json`；`planning/codex-tasks.md` 是渲染视图。
4. 验收命令必须执行，通过后才可标记 `DONE`（仅完整协作模式）。
5. 访谈、前端设计、审计都按复杂度分级。
6. 用户可读反馈由 Claude 负责翻译，脚本输出保持程序化。

## 第 1 步：复杂度判断与访谈

先判断复杂度，再决定访谈深度：
- 简单：2-3 轮。例：修 bug、小按钮、小工具函数。
- 中等：4-6 轮。例：新页面、一组接口、一个中等模块。
- 复杂：6-10 轮。例：认证、支付、权限、数据迁移、跨模块重构。

复杂度判断模板见 [prompt-templates.md](./references/prompt-templates.md) 1.0
规则和规格模板见 [interview.md](./references/interview.md)

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
python "<skill-dir>/scripts/cli.py" select
python "<skill-dir>/scripts/cli.py" summary
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

**纯规划模式到此结束。** 用户选择"开始开发"后写入 checkpoint，流程完成。后续可用"协作"或"继续开发"触发词衔接执行阶段。

```bash
python "<skill-dir>/scripts/cli.py" checkpoint-write user_approved spec_file=[路径] task_file=planning/codex-tasks.md total_tasks=[数量]
```

以下步骤仅在完整协作模式下执行。

## 第 4 步：执行模式

### Codex 模式

适用：`codex` 可用，且任务适合后台执行。

```bash
python "<skill-dir>/scripts/cli.py" run start XXX "任务提示词"
python "<skill-dir>/scripts/cli.py" run status XXX
python "<skill-dir>/scripts/cli.py" run stop XXX
```

### Adapter 模式

适用：希望保留后台 worker / run record / 卡死检测，但不直接依赖 `codex`。

默认内置：
- `claude-cli`：设置 `DUAL_AI_ADAPTER=claude-cli`
- `custom-json`：设置 `DUAL_AI_ADAPTER=custom-json` 和 `DUAL_AI_CUSTOM_CMD_JSON`

```bash
python "<skill-dir>/scripts/cli.py" run start XXX "任务提示词" --backend adapter
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
python "<skill-dir>/scripts/cli.py" update XXX IN_PROGRESS
python "<skill-dir>/scripts/cli.py" verify run XXX
python "<skill-dir>/scripts/cli.py" update XXX DONE
python "<skill-dir>/scripts/cli.py" checkpoint-write developing current_task=XXX completed_tasks=N
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
python "<skill-dir>/scripts/cli.py" detect XXX "$CODEX_PID"
python "<skill-dir>/scripts/cli.py" run status XXX
python "<skill-dir>/scripts/cli.py" run stop XXX
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
python "<skill-dir>/scripts/cli.py" summary
python "<skill-dir>/scripts/cli.py" summary --report
python -c "from pathlib import Path; p = Path('.dual-ai-collab/checkpoints/state.json'); print(p.read_text(encoding='utf-8') if p.exists() else '无活跃流程')"
```

恢复见 [recovery.md](./references/recovery.md)

## Claude 的执行要求

1. 根据触发词判断走纯规划还是完整协作，不要混淆两条路径。
2. 简单需求走轻流程，复杂需求走重流程。
3. Codex 缺失时直接切到 Claude-only，不要停在规划阶段（仅完整协作模式）。
4. 如果需要后台执行但没有 Codex，可优先尝试 adapter backend。
5. 小型前端改动不要强制完整设计流程。
6. 小任务不要默认完整三轮审计。
7. 只按需读取 reference，不要每次全量加载。

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

触发词（完整协作模式）：
- 双 AI 协作
- dual ai
- 启动协作
- 继续开发
- 审计代码

触发词（纯规划模式）：
- 规划
- planning
- 需求分析
- 任务规划
