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
5. 访谈、审计都按复杂度分级。
6. 用户可读反馈由 Claude 负责翻译，脚本输出保持程序化。
7. 流程依赖 grill-me 和 ui-ux-pro-max 都是**可选的**。无这些 skill 时，Claude 用手工方式替代（见各步说明）。

## 第 1 步：复杂度判断与访谈

先判断复杂度，再决定访谈深度：
- 简单：2-3 轮。例：修 bug、小按钮、小工具函数。无需对抗性提问。
- 中等：4-6 轮。例：新页面、一组接口、一个中等模块。后期可加对抗性提问（grill-me 或 Claude 手工）。
- 复杂：6-10 轮。例：认证、支付、权限、数据迁移、跨模块重构。中期进入对抗性提问（grill-me 或 Claude 手工）。

**降级方案**：
- 若有 grill-me：调用对抗性提问 Prompt（见 [grill-me-integration.md](./references/grill-me-integration.md) 第 1 节）
- 若无 grill-me：Claude 手工执行同等思路的对抗性提问（见 [prompt-templates.md](./references/prompt-templates.md) 1.5）

复杂度判断模板见 [prompt-templates.md](./references/prompt-templates.md) 1.0  
访谈规则和规格模板见 [interview.md](./references/interview.md)

## 第 2 步：规格与任务板

输出：
- `planning/specs/YYYYMMDD-HHMMSS-[功能名称].md`
- `planning/tasks.json`
- `planning/codex-tasks.md`

要求：
- 每个任务 1-3 小时
- 验收标准尽量可执行
- 依赖关系明确；前后端可按接口契约 Mock 先行时用 `**接口依赖**` + 独立集成任务，见 [execution-optimization.md](./references/execution-optimization.md) 第 3 节

常用命令：

```bash
python "<skill-dir>/scripts/cli.py" select
python "<skill-dir>/scripts/cli.py" summary
```

规范见 [task-board.md](./references/task-board.md)

## 第 3 步：规划审计与确认

分两个子阶段：

### 3.1 规范符合性审计（Claude 主审）

检查重点：
- 用户目标覆盖
- 任务拆分可执行性
- 依赖顺序
- 验收标准可验证性
- 风险与边界记录

必要时让 Codex 只做补漏，不重复整份审计。

### 3.2 设计质疑（按需深化）

根据复杂度和风险决定是否进入对抗性设计质疑：
- **简单需求**：跳过，直接用户确认
- **中等需求**：可选，按需启用
- **复杂/高风险需求**：推荐启用

**有 grill-me 时**：
- 调用 grill-me 设计质疑 Prompt（见 [grill-me-integration.md](./references/grill-me-integration.md) 第 2 节）
- grill-me 输出 5-10 个深度疑虑

**无 grill-me 时**：
- Claude 手工执行同等思路的设计质疑（见 [prompt-templates.md](./references/prompt-templates.md) 1.3）
- 输出格式相同，流程相同

设计质疑目的：暴露任务拆分风险、验收标准定性问题、边界情况缺口、依赖关系疑虑。

### 3.3 用户确认

让用户明确回复：
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
3. **Kickoff Check**：确保任务描述清晰，无歧义
4. 按当前模式实现
5. **可选 Midpoint Check**：任务中期检查（高风险任务推荐）
6. 运行验收命令
7. 通过后更新 `DONE`
8. 写 checkpoint

```bash
python "<skill-dir>/scripts/cli.py" update XXX IN_PROGRESS
# 执行前先做 kickoff check（见下方）
python "<skill-dir>/scripts/cli.py" verify run XXX
python "<skill-dir>/scripts/cli.py" update XXX DONE
python "<skill-dir>/scripts/cli.py" checkpoint-write developing current_task=XXX completed_tasks=N
```

### 5.1 Kickoff Check（任务启动检查）

在实现前立即做，确保任务理解无误。

**检查清单**（Claude 执行）：
- 任务目标能一句话说清吗？
- 相关文件都列了吗？
- 验收标准是否可验证？有没有定性标准需要改量化？
- 依赖任务都完成了吗？
- 技术方案有指导吗？

**发现问题时**：立即询问用户或补充说明，不要硬做。

详见 [execution-optimization.md](./references/execution-optimization.md) 第 1.1 节

### 5.2 Midpoint Check（任务中期检查）

**时机**：可选，当任务预计工时过半或遇到困难时。

**目的**：快速判断是否卡住、卡在哪、怎么处理。

**决策树**：
- 能 15 分钟解决？→ 给建议，继续
- 需求歧义？→ 澄清或返工规划
- 技术困难？→ 提供方案，让用户选
- 规划有问题？→ 升级为规划审计

详见 [execution-optimization.md](./references/execution-optimization.md) 第 1.2 节

## 第 6 步：前端设计分级

按任务复杂度灵活判断是否需要专门设计阶段，不强制所有前端任务都走完整流程。

### 简单前端任务：直接实现

以下情况可跳过设计阶段，直接进任务板实现：
- CSS bug 修复
- 间距、颜色、对齐微调
- 现有组件的小范围修复
- 不改变产品视觉方向的改动
- 表单验证、文案调整、权限控制

### 中等前端任务：按需设计

新页面、新组件、新交互。判断流程：

1. Claude 读任务描述，判断产品逻辑是否清晰
2. **有 ui-ux-pro-max 且任务复杂**：调用设计 Prompt（见 ui-ux-pro-max 文档）→ 生成完整设计方案 → 任务板中补充设计文件路径
3. **无 ui-ux-pro-max 或任务相对简单**：Claude 在任务描述中补充轻量设计说明（文字 + 简图/ASCII 草图 + 样式参考） → 直接实现

### 复杂前端任务：必做设计

以下情况必须做设计（有工具就用工具，没工具就用手工）：
- 新视觉方向或全新页面组系
- 复杂交互 / 多级嵌套 / 动效 / 实时反馈
- 用户研究有重大调整
- 跨平台适配有特殊要求

**流程**：
- **有 ui-ux-pro-max**：调用完整设计 Prompt → 生成设计方案 → 任务板中引用
- **无 ui-ux-pro-max**：Claude 手工设计（文字描述 + 组件草图 + 交互流程 + 样式指南） → 写成 `planning/design/[任务编号]-design.md` → 任务板中引用

### 核心原则

**灵活性优先**：设计决策由产品目标和规划清晰度决定，不是页面数量或 skill 可用性决定。

模板见 [prompt-templates.md](./references/prompt-templates.md) 2.2

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
  - 可选对抗性代码挑战（grill-me 或 Claude 手工）
  - Claude 快速核验
  - 必要时升级为标准审计

REJECTED 后先做根因分类（理解偏差 / 设计缺陷 / 环境 / 技术困难 / 无法修复），按修复决策表处理，最多 3 次。
任务数 ≥ 5 的项目，审计时同步维护 `planning/defect-patterns.md`，高频模式会提升后续任务的检查和审计强度。

规则见 [audit.md](./references/audit.md)，修复与模式库见 [execution-optimization.md](./references/execution-optimization.md)

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
