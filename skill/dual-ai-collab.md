---
name: dual-ai-collab
description: 双 AI 协作开发模式 - Claude 深入访谈 + 规范生成 + Codex 全自动开发，支持 checkpoint 恢复、异步执行、双重审计和自动修复
---

# Dual AI Collaboration Skill v2.3（自包含版）

> **目标运行环境**：本 Skill 专为 **Claude Code** 设计，依赖 Claude Code 的内置工具（Bash、Read、Write、Edit、AskUserQuestion）。Codex CLI 作为外部开发执行器被调用，但 Skill 本身的流程控制由 Claude 驱动。

你是 Claude，一个专业的软件架构师和项目经理。

当用户触发这个 skill 时，你需要启动**双 AI 协作开发流程**。

---

## 第 0 步：自动初始化 & 恢复检查

**每次触发 Skill 时，首先检查是否有中断的流程需要恢复。**

```bash
bash skill/scripts/init_env.sh
```

然后**立即检查是否有中断的流程**：

```bash
bash skill/scripts/check_checkpoint.sh
```

**如果发现 checkpoint（`CHECKPOINT_FOUND`）**：
- 读取 `state.json` 中的 `phase` 字段，确定中断在哪个阶段
- **直接跳转到对应阶段继续执行**，不要重新访谈或重新生成文档
- 恢复逻辑见下方「恢复执行规则」

**如果没有 checkpoint（`NO_CHECKPOINT`）**：
- 检查 Codex CLI 是否可用，然后从第 1 步开始

```bash
command -v codex && echo "CODEX_OK" || echo "CODEX_MISSING"
```

- 如果 `CODEX_MISSING`：提示用户安装（`npm install -g @openai/codex-cli`），但仍可继续访谈和文档生成

### 恢复执行规则

根据 `state.json` 中的 `phase` 值跳转：

| phase 值 | 恢复动作 |
|-----------|----------|
| `interview` | 读取已收集信息，继续未完成的访谈 |
| `spec_generated` | 跳到第 4 步（拆分任务） |
| `tasks_created` | 跳到第 5 步（等待用户审查） |
| `user_approved` | 跳到第 6 步（启动开发） |
| `developing` | 读取任务板，找到 OPEN/IN_PROGRESS 任务继续执行 |
| `auditing` | 读取任务板，对 DONE 任务继续审计 |
| `fixing` | 读取任务板，对 REJECTED 任务继续修复 |

**恢复时必须向用户报告**：
```
🔄 检测到中断的流程，正在恢复...
📍 中断阶段：[phase]
📋 任务板：planning/codex-tasks.md
⏩ 继续执行...
```

### Checkpoint 状态文件

文件路径：`.dual-ai-collab/checkpoints/state.json`，字段：`phase`、`spec_file`、`task_file`、`current_task`、`total_tasks`、`completed_tasks`、`fix_round`、`updated_at`。

**写入时机**（每次阶段转换时必须更新）：
- 访谈完成 → `phase: "spec_generated"`
- 任务板创建完成 → `phase: "tasks_created"`
- 用户确认开始开发 → `phase: "user_approved"`
- 开始执行任务 → `phase: "developing"`，更新 `current_task`
- 进入审计 → `phase: "auditing"`
- 进入修复 → `phase: "fixing"`，更新 `fix_round`
- 全部完成 → 删除 state.json

---

## 工作流程

### 第 1 步：询问需求

使用 **AskUserQuestion** 工具询问用户想要开发什么功能，请用户简要描述需求（如：用户认证系统、博客管理、电商购物车等）。

### 第 2 步：深入访谈

根据用户需求，进行 **5-10 轮深入访谈**，使用 **AskUserQuestion** 工具。

> 📖 详细访谈维度、访谈原则和问题示例见 `references/interview.md`

核心原则：
- 不问显而易见的问题，聚焦非显而易见的细节
- 涵盖：功能范围、技术实现、UI/UX、数据安全、边界情况、权衡取舍、集成依赖、测试验收
- 持续访谈直到所有关键维度都已覆盖

### 第 3 步：生成需求规范文档

访谈完成后，使用 **Write** 工具生成详细的需求规范文档。

**文件路径**：`planning/specs/YYYYMMDD-HHMMSS-[功能名称].md`

> 📖 文档结构模板（概述、功能需求、技术规范、UI 设计、非功能需求、边界情况、测试验收、实施计划、风险依赖）见 `references/interview.md`

每个功能条目必须包含：描述、优先级、预计工时、验收标准。

### 第 4 步：拆分任务并写入任务板

根据需求规范，将功能拆分为具体的开发任务。

**任务拆分原则**：每个任务 1-3 小时完成，任务间尽量独立，优先级明确（P1 > P2 > P3），验收标准清晰。

使用 **Write** 工具写入任务板，文件路径：`planning/codex-tasks.md`

> 📖 任务板格式模板、字段说明和依赖检查逻辑见 `references/task-board.md`

领取任务前检查依赖是否满足：

```bash
bash skill/scripts/select_next_task.sh
```

**执行原则**：依赖未完成则跳过该任务，继续寻找下一个可执行的 OPEN 任务。

### 第 5 步：展示摘要并等待用户审查

任务板创建完成后，展示摘要并**等待用户审查规划文档**：

```
✅ 需求规范和任务板已创建完成！
📄 需求规范文档：planning/specs/[文件名].md
📋 任务板：planning/codex-tasks.md
📊 总任务数：X 个 | ⏱️ 预计总工时：X 小时
```

使用 **AskUserQuestion** 工具询问用户：
1. 是否开始自动开发（开始开发 / 修改规划 / 取消）
2. 是否授予项目目录最高权限（自动创建 `.claude/settings.local.json`）

- 选择"开始开发" → 继续第 6 步
- 选择"修改规划" → 等待用户修改后再次询问
- 选择"取消" → 结束流程
- 选择"授权" → 写入项目级权限配置后继续

### 第 6 步：启动开发（异步 Codex 执行）

**核心原则：Codex 在后台执行，Claude 不阻塞等待。**

#### 6.1 启动前检查 & 写入 checkpoint

检查 Codex CLI 和任务板是否存在，写入 checkpoint：

```bash
bash skill/scripts/write_checkpoint.sh developing
```

#### 6.2 任务领取

```bash
bash skill/scripts/select_next_task.sh
```

选择最高优先级、依赖已满足的 OPEN 任务。

#### 6.3 更新任务状态

```bash
bash skill/scripts/update_task_status.sh XXX IN_PROGRESS
# 执行成功后：
bash skill/scripts/update_task_status.sh XXX DONE
# 执行失败后回退：
bash skill/scripts/update_task_status.sh XXX OPEN
```

#### 6.4 执行任务

**所有任务统一由 Codex 后台执行**，使用 `run_in_background: true`：

```bash
TASK_NUM="XXX"
LOG_FILE=".dual-ai-collab/logs/task-${TASK_NUM}.log"
codex exec -C "$(pwd)" --full-auto "你是专业开发工程师，执行以下任务：[任务内容]
要求：仔细阅读验收标准，编写高质量可维护代码，添加必要注释，满足所有验收标准。" \
  > "$LOG_FILE" 2>&1 &
echo $! > .dual-ai-collab/logs/task-${TASK_NUM}.pid
```

**前端/UI 任务额外要求**（文件含 `.html/.css/.vue/.tsx/.jsx/.svelte` 或描述含页面/组件/样式/布局等）：
- Codex 执行完成后，Claude 必须调用 `/ui-ux-pro-max` skill 对前端代码进行审查和优化
- Codex 根据 ui-ux-pro-max 的审查意见再次修改代码

#### 6.5 活跃度检测

```bash
bash skill/scripts/detect_stall.sh XXX $CODEX_PID
```

> 检测逻辑：进程存活检查（kill -0）+ 文件变动检测（find -mmin）+ 日志增长比较（状态文件持久化）

判定规则：连续 3 次 STALLED（约 3 分钟）→ kill 进程，回退任务为 OPEN，跳到下一个任务。轮询间隔 60 秒。

#### 6.6 执行循环

对每个 OPEN 任务自动循环：领取任务 → 更新 IN_PROGRESS → 后台启动 Codex → 更新 checkpoint → 轮询活跃度 → 成功更新 DONE / 卡死回退 OPEN → 自动继续下一个任务。

每个任务完成后更新 checkpoint 并报告进度：
```bash
bash skill/scripts/write_checkpoint.sh developing current_task=XXX completed_tasks=N
```
```
✅ 任务 #XXX 完成 (3/8) | ⏱️ 耗时：2m30s | 📋 剩余：5 个 | ⏩ 继续执行 #YYY...
```

全部任务完成后更新 checkpoint 为 `auditing`，自动进入审计流程。

### 第 7 步：多 Worker 并行执行（可选）

对无依赖的 OPEN 任务，可同时启动多个 Codex 实例并行处理。

**前提**：并行任务间无依赖关系（`**依赖任务**: 无`）且无文件写入冲突，建议并行数不超过 3 个。

```bash
# 查找可并行任务
bash skill/scripts/select_next_task.sh --parallel

# 并行启动（每个任务独立后台进程）
codex exec -C "$(pwd)" --full-auto "执行任务 #001：[描述]" > .dual-ai-collab/logs/task-001.log 2>&1 &
codex exec -C "$(pwd)" --full-auto "执行任务 #003：[描述]" > .dual-ai-collab/logs/task-003.log 2>&1 &
wait
```

某个任务失败时用 `update_task_status.sh` 回退为 OPEN，不影响其他 Worker。所有并行任务完成后统一进行审计。

---

## 审计流程（双 AI 审计 + 自动修复）

当所有任务完成（DONE）或识别到审计触发词时，自动启动双重审计。

> 📖 详细审计步骤、提示词模板、报告格式和评分标准见 `references/audit.md`

```bash
bash skill/scripts/write_checkpoint.sh auditing
```

### 审计第一轮：Codex 代码审查

对每个 DONE 任务，后台启动 Codex 进行代码审查：

```bash
codex exec -C "$(pwd)" --full-auto "你是资深代码审查员，审查任务 #XXX 的实现：
任务描述：[描述]
相关文件：[文件列表]
验收标准：[验收标准]

请检查：功能符合性、代码质量、安全性、性能、边界情况。
输出格式：评分(1-10)、PASS/FAIL、问题列表、改进建议。" \
  > ".dual-ai-collab/logs/audit-${TASK_NUM}-codex.log" 2>&1
```

Codex 审查完成后：
- 将审查结果保存到 `planning/audit-reports/task-XXX-codex-review.md`
- 更新任务板，添加 **Codex 审查状态**字段（PASS / FAIL）

### 审计第二轮：Claude 综合审计

Claude 读取以下内容进行综合判定：
1. Codex 的审查报告
2. 需求规范文档
3. 实际代码实现

综合判定后：
- 更新任务板 **Claude 审查状态**字段（VERIFIED / REJECTED）
- 写入综合审计报告到 `planning/audit-reports/task-XXX-final-review.md`
- 报告中包含 Codex 审查结果 + Claude 补充意见

### 审计第三轮：自动修复循环

REJECTED 的任务进入自动修复：

```bash
bash skill/scripts/write_checkpoint.sh fixing fix_round=N
```

1. Claude 将审计报告（含 Codex + Claude 双方意见）整理为修复指令
2. Codex 后台执行修复，读取审计报告中的具体问题和建议
3. 修复完成后重置审查状态，重新进入审计第一轮
4. 修复上限 3 次，超过则标记 FAILED 通知用户人工介入

### 任务板审计字段

每个任务在审计阶段需维护以下字段：

```markdown
**Codex 审查**: PASS/FAIL/待审查
**Claude 审查**: VERIFIED/REJECTED/待审查
**修复轮次**: 0/3
```

---

## 恢复开发流程

识别触发词："开始开发"、"启动 Codex"、"继续开发"、"现在可以开发了"

1. 检查 `planning/codex-tasks.md` 是否存在
2. 有 OPEN 任务 → 执行第 6 步；有 IN_PROGRESS 任务 → 回退为 OPEN 后继续；全部 DONE/VERIFIED → 提示可进行审计
3. 不存在 → 询问是否重新访谈

---

## 监控命令

```bash
# 查看任务进度统计
bash skill/scripts/summarize_progress.sh

# 查看 checkpoint 状态
cat .dual-ai-collab/checkpoints/state.json 2>/dev/null || echo "无活跃流程"

# 查看 Codex 进程
pgrep -f "codex exec" && echo "Codex 运行中" || echo "无 Codex 进程"

# 查看任务日志
tail -n 20 .dual-ai-collab/logs/task-*.log 2>/dev/null
```

---

## 进度报告

触发词："生成报告"、"查看进度"、"项目进度"

```bash
bash skill/scripts/summarize_progress.sh
```

统计各状态任务数、完成率、审计通过率、预估剩余时间，写入 `planning/progress-reports/YYYYMMDD-HHMMSS-progress.md`。

---

## 重要提示

1. **本 Skill 完全自包含**：只需 `cp dual-ai-collab.md ~/.claude/skills/` 即可使用
2. **访谈必须深入**：不要问显而易见的问题，持续 5-10 轮直到需求明确
3. **任务拆分合理**：每个任务 1-3 小时，独立可测
4. **规划后等待用户审查**：任务板生成后必须等用户确认才能启动开发
5. **Checkpoint 持久化**：每次阶段转换必须更新 checkpoint
6. **Codex 后台执行**：后台启动 Codex，避免阻塞主流程
7. **对话压缩后自动恢复**：触发 Skill 时先检查 checkpoint，有则恢复
8. **安全第一**：不要在文档中记录敏感信息
9. **审计严格**：按评分标准客观评价，REJECTED 需说明具体原因

---

## 故障排查

> 📖 详细故障排查步骤见 `references/troubleshooting.md`

常见问题快速处理：
- **Codex 未安装**：`npm install -g @openai/codex-cli`
- **任务卡在 IN_PROGRESS**：`sed -i 's/\*\*状态\*\*: IN_PROGRESS/\*\*状态\*\*: OPEN/g' planning/codex-tasks.md`
- **流程中断恢复**：重新触发 Skill，自动检测 checkpoint 恢复
- **清理状态**：`rm -f .dual-ai-collab/checkpoints/state.json`

---

## 安装方法

```bash
# 方法一：从仓库安装
git clone https://github.com/thin2/dual-ai-collab.git
cp dual-ai-collab/skill/dual-ai-collab.md ~/.claude/skills/

# 方法二：直接下载
curl -o ~/.claude/skills/dual-ai-collab.md \
  https://raw.githubusercontent.com/thin2/dual-ai-collab/master/skill/dual-ai-collab.md

# 方法三：手动安装
mkdir -p ~/.claude/skills
# 将本文件内容保存到 ~/.claude/skills/dual-ai-collab.md
```

安装完成后，在 Claude Code 中输入以下任意魔法词即可使用：
- 🤖 启动双 AI  |  🚀 开始协作  |  💬 深入访谈  |  🔍 审计代码

**无需任何其他配置，开箱即用。**
