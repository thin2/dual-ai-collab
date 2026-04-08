---
name: dual-ai-collab
description: 双 AI 协作开发模式 - Claude 深入访谈 + 规范生成 + Codex 全自动开发，支持 checkpoint 恢复、异步执行、双重审计和自动修复
---

# Dual AI Collaboration Skill v2.3（自包含版）

> **目标运行环境**：本 Skill 专为 **Claude Code** 设计，依赖 Claude Code 的内置工具（Bash、Read、Write、Edit、AskUserQuestion）。Codex CLI 作为外部开发执行器被调用，但 Skill 本身的流程控制由 Claude 驱动。

> **Skill 安装目录**：`~/.claude/skills/dual-ai-collab/`，脚本位于 `scripts/`，参考文档位于 `references/`。下文所有脚本路径均使用变量 `SKILL_DIR`。

你是 Claude，一个专业的软件架构师和项目经理。

当用户触发这个 skill 时，你需要启动**双 AI 协作开发流程**。

**首先设置 Skill 目录变量**（后续所有脚本调用都基于此）：
```bash
SKILL_DIR="$HOME/.claude/skills/dual-ai-collab"
```

---

## 第 0 步：自动初始化 & 恢复检查

**每次触发 Skill 时，首先检查是否有中断的流程需要恢复。**

```bash
bash "$SKILL_DIR/scripts/init_env.sh"
```

然后**立即检查是否有中断的流程**：

```bash
bash "$SKILL_DIR/scripts/check_checkpoint.sh"
```

- **`CHECKPOINT_FOUND`** → 读取 `state.json` 中的 `phase`，按恢复文档跳转到对应阶段继续执行
- **`CHECKPOINT_CORRUPTED`** → 读取恢复文档中的损坏处理逻辑，优先根据任务板推断阶段
- **`NO_CHECKPOINT`** → 检查 Codex CLI，从第 1 步开始

> 📖 恢复逻辑详情（phase 映射、最小文件集、损坏处理）见 `$SKILL_DIR/references/recovery.md`

```bash
command -v codex && echo "CODEX_OK" || echo "CODEX_MISSING"
```

- 如果 `CODEX_MISSING`：提示用户安装（`npm install -g @openai/codex-cli`），但仍可继续访谈和文档生成

### Checkpoint 状态文件

文件路径：`.dual-ai-collab/checkpoints/state.json`

**写入方式**（每次阶段转换时调用）：
```bash
bash "$SKILL_DIR/scripts/write_checkpoint.sh" <phase> [key=value ...]
```

写入时机：
- 访谈完成 → `spec_generated`
- 任务板创建 → `tasks_created`
- 用户确认 → `user_approved`
- 开始执行 → `developing current_task=X total_tasks=N`
- 进入审计 → `auditing`
- 进入修复 → `fixing fix_round=N`
- 全部完成 → 删除 state.json

---

## 工作流程

### 第 1 步：询问需求

使用 **AskUserQuestion** 工具询问用户想要开发什么功能，请用户简要描述需求（如：用户认证系统、博客管理、电商购物车等）。

### 第 2 步：深入访谈

根据用户需求，进行 **5-10 轮深入访谈**，使用 **AskUserQuestion** 工具。

> 📖 详细访谈维度、访谈原则和问题示例见 `$SKILL_DIR/references/interview.md`

核心原则：
- 不问显而易见的问题，聚焦非显而易见的细节
- 涵盖：功能范围、技术实现、UI/UX、数据安全、边界情况、权衡取舍、集成依赖、测试验收
- 持续访谈直到所有关键维度都已覆盖

### 第 3 步：生成需求规范文档

访谈完成后，使用 **Write** 工具生成详细的需求规范文档。

**文件路径**：`planning/specs/YYYYMMDD-HHMMSS-[功能名称].md`

> 📖 文档结构模板（概述、功能需求、技术规范、UI 设计、非功能需求、边界情况、测试验收、实施计划、风险依赖）见 `$SKILL_DIR/references/interview.md`

每个功能条目必须包含：描述、优先级、预计工时、验收标准。

### 第 4 步：拆分任务并写入任务板

根据需求规范，将功能拆分为具体的开发任务。

**任务拆分原则**：每个任务 1-3 小时完成，任务间尽量独立，优先级明确（P1 > P2 > P3），验收标准清晰。

使用 **Write** 工具写入任务板，文件路径：`planning/codex-tasks.md`

> 📖 任务板格式模板、字段说明和依赖检查逻辑见 `$SKILL_DIR/references/task-board.md`

领取任务前检查依赖是否满足：

```bash
bash "$SKILL_DIR/scripts/select_next_task.sh"
```

**执行原则**：依赖未完成则跳过该任务，继续寻找下一个可执行的 OPEN 任务。

### 第 5 步：先审计规划，再等待用户确认

任务板创建完成后，先由 Claude 对规划文档做主审。

- 必查项：目标覆盖、任务拆分、依赖关系、验收标准、风险记录
- 如需补漏，可让 Codex 做一次**补充审查**，只查遗漏点，不重复整份审计
- 规划审计和用户确认提示词模板见 `$SKILL_DIR/references/prompt-templates.md`

确认规划达到可开发状态后，再展示摘要并**等待用户审查规划文档**：

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

#### 6.0 环境准备（如需虚拟环境）

如果项目需要虚拟环境（Python 项目、有 requirements.txt/pyproject.toml/environment.yml 等），Claude 负责创建：

```bash
# 使用 conda 创建项目虚拟环境
conda create -n [项目名] python=[版本] -y
conda activate [项目名]
pip install -r requirements.txt  # 或其他依赖安装方式
```

环境创建完成后，记录激活命令到 `.dual-ai-collab/env-info.txt`：

```bash
echo "conda activate [项目名]" > .dual-ai-collab/env-info.txt
```

后续所有 Codex 执行任务的提示词中必须包含环境激活指令：
```
在执行前先运行：source $(conda info --base)/etc/profile.d/conda.sh && conda activate [项目名]
```

#### 6.1 启动前检查 & 写入 checkpoint

检查 Codex CLI 和任务板是否存在，写入 checkpoint：

```bash
bash "$SKILL_DIR/scripts/write_checkpoint.sh" developing
```

#### 6.2 任务领取

```bash
bash "$SKILL_DIR/scripts/select_next_task.sh"
```

选择最高优先级、依赖已满足的 OPEN 任务。

#### 6.3 更新任务状态

```bash
bash "$SKILL_DIR/scripts/update_task_status.sh" XXX IN_PROGRESS
# 执行成功且验收命令通过后：
bash "$SKILL_DIR/scripts/update_task_status.sh" XXX DONE
# 执行失败后回退：
bash "$SKILL_DIR/scripts/update_task_status.sh" XXX OPEN
```

#### 6.4 执行任务

**所有任务统一通过执行器抽象层启动**，使用 `run_in_background: true`：

> 📖 各类任务的结构化提示词模板见 `$SKILL_DIR/references/prompt-templates.md`

```bash
TASK_NUM="XXX"
bash "$SKILL_DIR/scripts/run_task.sh" start "$TASK_NUM" \
  "你是专业开发工程师，执行以下任务：[任务内容]
要求：仔细阅读验收标准，编写高质量可维护代码，添加必要注释，满足所有验收标准。"
```

> `run_task.sh start` 会自动创建日志文件、PID 文件和运行记录（`.dual-ai-collab/runs/task-XXX.json`），输出 JSON 格式的 run record。

**前端/UI 任务额外流程**（文件含 `.html/.css/.vue/.tsx/.jsx/.svelte` 或描述含页面/组件/样式/布局等）：

**硬规则**：如果任务涉及页面、组件、样式、布局、交互、动效或视觉优化，Claude 必须先调用 `/ui-ux-pro-max` 生成设计方案，再将该方案作为 Codex 的硬约束输入。没有设计方案时，不得直接进入前端编码。

1. Claude 先调用 `/ui-ux-pro-max` skill，根据任务需求生成设计方案（配色、布局、组件结构、交互规范等）
2. 将设计方案写入 `.dual-ai-collab/designs/task-XXX-design.md`
3. Codex 执行时，提示词中附带设计方案：

```bash
DESIGN=$(cat .dual-ai-collab/designs/task-${TASK_NUM}-design.md)
bash "$SKILL_DIR/scripts/run_task.sh" start "$TASK_NUM" \
  "你是专业前端开发工程师，执行以下任务：[任务内容]

【设计规范】（必须严格遵循）：
${DESIGN}

要求：严格按照设计规范实现，确保 UI 还原度、响应式适配、无障碍访问。"
```

4. Codex 完成后，Claude 再次调用 `/ui-ux-pro-max` skill 审查前端代码是否符合设计方案
5. 如有偏差，将审查意见传给 Codex 修改

#### 6.5 活跃度检测

```bash
bash "$SKILL_DIR/scripts/detect_stall.sh" XXX "$CODEX_PID"
# 或通过执行器查询运行状态：
bash "$SKILL_DIR/scripts/run_task.sh" status XXX
```

> 检测逻辑：进程存活检查（kill -0）+ 文件变动检测（基于任务级阈值）+ 日志增长比较（状态文件持久化）

卡死阈值优先级：

1. 任务板中的 `**卡死阈值**`
2. 任务板中的 `**执行级别**`（`quick=3m`、`normal=5m`、`heavy=10m`）
3. 未配置时默认 `3m`

判定规则：连续 3 次 STALLED → 先尝试 `codex:rescue` agent 诊断（可选），如仍无法恢复则 kill 进程，回退任务为 OPEN，跳到下一个任务。轮询间隔 60 秒。

**卡死降级策略（可选）**：

当 direct backend 连续卡死或失败时，优先按 superpowers 的 `systematic-debugging` 思路做根因调查；如果该 skill 不可用，再降级调用 `codex:rescue` agent：
- 先做 Phase 1：收集日志尾部、最近改动、失败现象，不急着重试
- 判断属于环境问题 / 任务过大 / 上下文缺失 / 真正代码缺陷中的哪一类
- 能修复前置条件就先修复，再决定重试
- 无法诊断时，再 kill + 回退 OPEN + 通知用户

最小执行材料：
- 读取任务日志 `.dual-ai-collab/logs/task-XXX.log` 的尾部
- 当前任务描述与验收标准
- 最近一次失败/卡死前后的关键输出

兜底方式：
- 让 rescue agent 分析失败原因并给出修复建议
- 根据诊断结果决定：缩小任务范围重试 / 跳过 / 通知用户

#### 6.6 验证门控

如果任务板的 `### 验收标准` 中包含带反引号的可执行命令，Claude 必须在任务退出码为 0 后运行自动验证：

```bash
bash "$SKILL_DIR/scripts/verify_task.sh" run "$TASK_NUM"
```

- 全部通过 → 才允许把任务更新为 `DONE`
- 任一命令失败 → 视为任务未完成，回退为 `OPEN` 或进入修复
- 没有可执行验收命令 → 脚本返回 `NO_VERIFICATION_COMMANDS`，此时应补齐任务板或转为人工审查

> 只会自动执行带反引号的命令，例如：`- [ ] \`bash tests/run_all_tests.sh\` 全部通过`

#### 6.7 执行循环

对每个 OPEN 任务自动循环：领取任务 → 更新 IN_PROGRESS → 后台启动 Codex → 更新 checkpoint → 轮询活跃度 → 成功后运行验收命令 → 验证通过再更新 DONE / 卡死回退 OPEN → 自动继续下一个任务。

每个任务完成后更新 checkpoint 并报告进度：
```bash
bash "$SKILL_DIR/scripts/write_checkpoint.sh" developing current_task=XXX completed_tasks=N
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
bash "$SKILL_DIR/scripts/select_next_task.sh" --parallel

# 并行启动（每个任务通过执行器启动）
bash "$SKILL_DIR/scripts/run_task.sh" start 001 "执行任务 #001：[描述]"
bash "$SKILL_DIR/scripts/run_task.sh" start 003 "执行任务 #003：[描述]"

# 轮询状态
bash "$SKILL_DIR/scripts/run_task.sh" status 001
bash "$SKILL_DIR/scripts/run_task.sh" status 003
```

某个任务失败时用 `update_task_status.sh` 回退为 OPEN，不影响其他 Worker。所有并行任务完成后统一进行审计。

---

## 审计流程（双 AI 审计 + 自动修复）

当所有任务完成（DONE）或识别到审计触发词时，自动启动双重审计。

> 📖 详细审计步骤、提示词模板、报告格式和评分标准见 `$SKILL_DIR/references/audit.md`

```bash
bash "$SKILL_DIR/scripts/write_checkpoint.sh" auditing
```

### 审计第一轮：Spec Compliance Review

优先使用 superpowers 的 `spec-reviewer` 方法论检查“是不是按任务描述和验收标准做了”。如果没有 superpowers 环境，则沿用当前 Codex 审查方式，但输出格式必须贴近 spec compliance review：

```bash
bash "$SKILL_DIR/scripts/run_task.sh" start "audit-${TASK_NUM}" \
  "你是规范符合性审查员，审查任务 #XXX 的实现：
任务描述：[描述]
相关文件：[文件列表]
验收标准：[验收标准]

请检查：是否完成任务目标、是否覆盖验收标准、是否存在遗漏实现、是否有需要人工确认的模糊点。
输出格式：评分(1-10)、PASS/FAIL、Blocking Issues、Missing Coverage、Need User Confirmation。"
```

> 如果具备 superpowers 环境，优先用其 `spec-reviewer` prompt/skill 作为第一轮审查模板。

Codex 审查完成后：
- 将结果保存到 `planning/audit-reports/task-XXX-spec-review.md`
- 更新任务板，添加 **Codex 审查状态**字段（PASS / FAIL）

### 审计第二轮：Code Quality Review

优先使用 superpowers 的 `code-quality-reviewer` 方法论检查“做得好不好”，重点看结构、可维护性、边界、验证缺口。若没有 superpowers 环境，则由 Claude 或 Codex 按同一关注点完成第二轮。

第二轮必须读取：
1. 第一轮规范符合性审查结果
2. 需求规范文档
3. 实际代码实现

输出重点：
- 代码质量与维护性
- 风险边界和回归风险
- 测试/验证缺口
- 是否适合直接进入最终判定

### 审计第三轮：Claude 综合判定

Claude 读取以下内容进行综合判定：
1. 第一轮 spec compliance review
2. 第二轮 code quality review
3. 需求规范文档
4. 实际代码实现

综合判定后：
- 更新任务板 **Claude 审查状态**字段（VERIFIED / REJECTED）
- 写入综合审计报告到 `planning/audit-reports/task-XXX-final-review.md`
- 报告中包含规范符合性结论 + 代码质量结论 + Claude 补充意见

### 审计第四轮：自动修复循环

REJECTED 的任务进入自动修复：

```bash
bash "$SKILL_DIR/scripts/write_checkpoint.sh" fixing fix_round=N
```

1. Claude 将审计报告（含规范符合性 + 代码质量 + Claude 判定）整理为修复指令
2. 如有 superpowers 环境，优先使用 `receiving-code-review` 的处理方式，把问题按严重度和可执行动作整理后再交给 Codex
3. Codex 后台执行修复，读取审计报告中的具体问题和建议
4. 修复完成后重置审查状态，重新进入审计第一轮
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
bash "$SKILL_DIR/scripts/summarize_progress.sh"

# 查看 checkpoint 状态
cat .dual-ai-collab/checkpoints/state.json 2>/dev/null || echo "无活跃流程"

# 查看特定任务的运行状态（通过执行器）
bash "$SKILL_DIR/scripts/run_task.sh" status XXX

# 查看 Codex 进程（兼容方式）
pgrep -f "codex exec" && echo "Codex 运行中" || echo "无 Codex 进程"

# 查看任务日志
tail -n 20 .dual-ai-collab/logs/task-*.log 2>/dev/null

# 终止特定任务
bash "$SKILL_DIR/scripts/run_task.sh" stop XXX
```

---

## 进度报告

触发词："生成报告"、"查看进度"、"项目进度"

```bash
bash "$SKILL_DIR/scripts/summarize_progress.sh" --report
```

统计各状态任务数、完成率、审计通过率、预估剩余时间，写入 `planning/progress-reports/YYYYMMDD-HHMMSS-progress.md`。

---

## 重要提示

1. **安装方式**：`cp -r skill ~/.claude/skills/dual-ai-collab`，包含脚本和参考文档
2. **访谈必须深入**：不要问显而易见的问题，持续 5-10 轮直到需求明确
3. **任务拆分合理**：每个任务 1-3 小时，独立可测
4. **规划先审计、再确认**：任务板生成后先做规划审计，再等用户确认启动开发
5. **Checkpoint 持久化**：每次阶段转换必须更新 checkpoint
6. **Codex 后台执行**：后台启动 Codex，避免阻塞主流程
7. **对话压缩后自动恢复**：触发 Skill 时先检查 checkpoint，有则恢复
8. **安全第一**：不要在文档中记录敏感信息
9. **审计严格**：按评分标准客观评价，REJECTED 需说明具体原因

---

## 故障排查

> 📖 详细故障排查步骤见 `$SKILL_DIR/references/troubleshooting.md`

常见问题快速处理：
- **Codex 未安装**：`npm install -g @openai/codex-cli`
- **任务卡在 IN_PROGRESS**：`bash "$SKILL_DIR/scripts/run_task.sh" stop XXX` 终止后回退状态
- **流程中断恢复**：重新触发 Skill，自动检测 checkpoint 恢复
- **清理状态**：`rm -f .dual-ai-collab/checkpoints/state.json`
- **Codex 连续失败**：使用 `codex:rescue` agent 诊断失败原因

---

## 安装方法

```bash
# 方法一：克隆仓库（推荐，包含脚本和参考文档）
git clone https://github.com/thin2/dual-ai-collab.git
cp -r dual-ai-collab/skill ~/.claude/skills/dual-ai-collab

# 方法二：手动安装
mkdir -p ~/.claude/skills/dual-ai-collab
# 将 skill/ 目录下所有内容复制到 ~/.claude/skills/dual-ai-collab/
```

安装完成后，在 Claude Code 中输入以下任意关键词即可使用：
- 双 AI 协作 | dual ai | 启动协作 | 深入访谈 | 审计代码

**无需任何其他配置，开箱即用。**
