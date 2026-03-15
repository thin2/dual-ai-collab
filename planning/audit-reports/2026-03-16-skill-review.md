# 审查报告：dual-ai-collab Skill 结构与可维护性评估

**审查时间**: 2026-03-16
**审查对象**: `skill/dual-ai-collab.md` 及其配套说明文档
**审查类型**: 静态审查 / Skill 结构审计 / 可维护性评估
**审查基准**:
- 当前仓库内 `skill/dual-ai-collab.md`
- `skill-definition.md`
- `README.md`
- Codex `skill-creator` 指南

---

## 审查结论

当前这份 skill 的核心思路清晰，协作流程也覆盖了访谈、拆解、开发、审计和修复闭环；但从 **Codex skill 规范适配、结构设计、执行可靠性和长期维护成本** 来看，仍存在一轮值得优先处理的结构性问题。

综合判断：当前版本更像一份“面向 Claude 的长篇操作剧本”，而不是一份经过收敛的、便于 Codex 稳定加载和复用的 skill。若继续扩展功能而不先做结构收敛，后续文档漂移、行为分叉和上下文膨胀问题会进一步加剧。

建议将本次整改目标定义为：**先完成 skill 结构重构，再继续叠加新能力。**

---

## 审查范围与方法

本次审查主要关注以下维度：

1. Skill 文件结构是否符合当前 Codex skill 的推荐组织方式。
2. frontmatter、正文和配套文档是否存在语义漂移。
3. 指令是否过度依赖特定代理或专属工具。
4. 是否存在会直接影响恢复、执行或维护的实现级问题。
5. 当前文件组织是否满足 progressive disclosure 原则。

本次未进行端到端实际执行，原因是 skill 中引用了若干特定代理环境工具；因此本报告以静态审查和结构对照为主。

---

## 主要发现

### 发现 1：Skill 入口结构与 Codex 推荐规范不一致

**严重级别**: 高

**证据**

- [skill/dual-ai-collab.md:1](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L1)
- [skill/dual-ai-collab.md:8](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L8)
- [SKILL.md:58](/home/hn/.codex/skills/.system/skill-creator/SKILL.md#L58)
- [SKILL.md:79](/home/hn/.codex/skills/.system/skill-creator/SKILL.md#L79)

**问题描述**

当前仓库的 skill 主文件是 `skill/dual-ai-collab.md`，并采用了自定义 frontmatter 字段：

- `version`
- `author`
- `category`
- `triggers`
- `aliases`

但根据 `skill-creator` 指南，Codex skill 的核心识别入口应为 `SKILL.md`，且真正影响触发判断的关键字段是 `name` 与 `description`。这意味着当前文件中大量自定义 frontmatter 很可能只是“自我描述”，并不会稳定参与技能发现或触发。

**影响**

- Skill 在 Codex 语境下的可发现性和触发行为不稳定
- 文档中宣称的关键词、别名、魔法词未必真正生效
- 后续维护者容易误以为 frontmatter 中所有字段都属于正式契约

**建议**

- 将技能入口重构为标准目录结构：`dual-ai-collab/SKILL.md`
- 将触发语义收敛进 `description`
- 将 `version`、`author`、`aliases` 等非关键元信息移出 frontmatter

---

### 发现 2：Skill 主文件过大，违反 progressive disclosure 原则

**严重级别**: 高

**证据**

- [skill/dual-ai-collab.md](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md)
- [SKILL.md:103](/home/hn/.codex/skills/.system/skill-creator/SKILL.md#L103)
- [SKILL.md:145](/home/hn/.codex/skills/.system/skill-creator/SKILL.md#L145)

**问题描述**

`skill/dual-ai-collab.md` 当前共有 1169 行，已经远超 `skill-creator` 对 SKILL.md “尽量控制在 500 行以内”的建议。该文件同时承载了：

- 初始化与 checkpoint
- 深入访谈策略
- 规范文档模板
- 任务板格式
- 串行执行逻辑
- 并行执行逻辑
- 审计流程
- 自动修复流程
- 故障排查
- 进度报告

这使 skill 在触发后需要一次性加载大量细节，不利于模型稳定抓住真正关键的执行约束。

**影响**

- 上下文成本过高
- 指令优先级容易被稀释
- 细节修改时更容易出现局部更新、整体漂移
- 新增功能会进一步放大维护难度

**建议**

- 将核心流程保留在 `SKILL.md`
- 将任务板规范、审计规则、故障排查、并行策略拆到 `references/`
- 将重复 shell 逻辑抽到 `scripts/`

---

### 发现 3：Skill 过度绑定 Claude 专属语境，难以作为通用 Codex skill 复用

**严重级别**: 高

**证据**

- [skill/dual-ai-collab.md:33](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L33)
- [skill/dual-ai-collab.md:154](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L154)
- [skill/dual-ai-collab.md:171](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L171)
- [skill/dual-ai-collab.md:417](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L417)
- [skill/dual-ai-collab.md:578](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L578)
- [skill/dual-ai-collab.md:786](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L786)

**问题描述**

文件正文一开始就将代理角色写死为 Claude，并在后续大量使用下列工具名和能力假设：

- `AskUserQuestion`
- `Read`
- `Write`
- `Edit`
- `run_in_background`

这使技能本身并不是“描述协作流程”，而是在“描述某一类 Claude 运行时如何操作”。如果你的目标是保留一个 Claude 专用技能，这样可以接受；但如果目标是让 Codex 当前技能体系也稳定消费，这种写法耦合度过高。

**影响**

- Skill 的可移植性较差
- 一旦运行环境工具名变化，正文会大面积失真
- 模型更容易把环境假设误当成任务目标

**建议**

- 将技能正文改写为“意图级指令”，弱化具体工具名
- 把运行时差异拆到单独参考文档，如 `references/claude-runtime.md`、`references/codex-runtime.md`
- 明确说明本 skill 的目标环境，避免“看起来通用，实则专用”

---

### 发现 4：Checkpoint 示例写法存在实现级错误，时间戳不会展开

**严重级别**: 中高

**证据**

- [skill/dual-ai-collab.md:130](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L130)
- [skill/dual-ai-collab.md:141](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L141)

**问题描述**

checkpoint 写入示例使用了单引号 heredoc：

```bash
cat > .dual-ai-collab/checkpoints/state.json << 'CHECKPOINT'
```

在这种写法下，`updated_at` 字段中的 `$(date -u +%Y-%m-%dT%H:%M:%SZ)` 不会被 shell 展开，而会被原样写入文件。

**影响**

- `updated_at` 失去真实时间语义
- 恢复逻辑中的可观测性下降
- 后续若依赖时间戳做调度或诊断，会出现误导

**建议**

- 改为无引号 heredoc，或先生成时间变量再插值
- 为 checkpoint 示例补充“有效 JSON 输出”的明确要求

---

### 发现 5：流程定义内部存在矛盾，用户确认是否必需不够清晰

**严重级别**: 中高

**证据**

- [skill/dual-ai-collab.md:414](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L414)
- [skill/dual-ai-collab.md:445](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L445)
- [skill/dual-ai-collab.md:646](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L646)
- [skill/dual-ai-collab.md:970](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L970)

**问题描述**

正文一处明确要求：

- 任务板生成后先让用户审查
- 用户选择“开始开发”后才进入第 6 步

但在执行循环部分又写明：

- “自动继续下一个任务（无需用户确认）”

在“重要提示”中则再次强调：

- “规划后等待用户审查”

这意味着 skill 对“是否必须经用户确认才能真正开始改代码”没有统一口径。

**影响**

- 不同代理在执行时可能采取不同策略
- 用户预期和实际行为可能不一致
- 这是高风险的行为级歧义，而不仅是文案问题

**建议**

- 明确产品决策
- 若要求安全可控，保留“规划后确认再执行”
- 若追求全自动，需同步删除所有“必须等待确认”的表述

---

### 发现 6：大量高脆弱度 shell 逻辑内联在 skill 正文中，维护和测试成本偏高

**严重级别**: 中

**证据**

- [skill/dual-ai-collab.md:555](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L555)
- [skill/dual-ai-collab.md:584](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L584)
- [skill/dual-ai-collab.md:668](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L668)
- [skill/dual-ai-collab.md:771](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L771)
- [skill/dual-ai-collab.md:843](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L843)

**问题描述**

当前 skill 将大量 awk/sed/bash 逻辑直接嵌在说明文字中，包括：

- 任务挑选
- 后台启动
- 活跃度检测
- 并行分配
- 审计状态更新
- 修复后状态回写

这些操作属于高脆弱度、强格式依赖、重复出现的逻辑，更适合抽到 `scripts/` 中由 skill 调用，而不是长期以内联代码块形式维护。

**影响**

- 一旦任务板格式有细微变化，多个片段都可能同步失效
- 测试和技能说明之间容易出现语义漂移
- 修改一处逻辑后，难以确保所有副本都同步更新

**建议**

- 将解析和状态更新逻辑收敛到脚本层
- Skill 只保留“何时调用什么脚本”的说明
- 为脚本建立单元测试，减少对正文示例的依赖

---

### 发现 7：README 和 skill 文档角色边界不清，仓库中存在额外噪音文档

**严重级别**: 中

**证据**

- [skill/README.md](/home/hn/projects/dual-ai-collab/skill/README.md)
- [skill/CHANGELOG.md](/home/hn/projects/dual-ai-collab/skill/CHANGELOG.md)
- [SKILL.md:123](/home/hn/.codex/skills/.system/skill-creator/SKILL.md#L123)
- [SKILL.md:133](/home/hn/.codex/skills/.system/skill-creator/SKILL.md#L133)

**问题描述**

`skill-creator` 明确建议 skill 目录下避免额外附带 README、安装说明、changelog 等辅助文档，因为这些内容容易形成额外噪音并加剧维护分裂。但当前仓库在 `skill/` 下仍保留了：

- `skill/README.md`
- `skill/CHANGELOG.md`

这些文件从“项目仓库文档”角度可以理解，但从“技能交付物”角度看，边界并不清晰。

**影响**

- 维护者难以分辨哪些文件属于真正的 skill 契约
- 版本说明、安装说明和主 skill 更容易漂移
- Skill 目录可读性变差

**建议**

- 若以仓库方式维护 skill，建议区分“项目文档”和“技能交付目录”
- 交付目录仅保留 `SKILL.md`、`references/`、`scripts/`、`agents/`
- 其余说明统一上移到仓库根目录

---

## 正向观察

以下方面值得保留：

- 双 AI 协作的角色分工很清楚，产品概念易于理解。
- 任务板作为单一协作接口的设计是合理的。
- 访谈、规范、开发、审计、修复的闭环意识较强。
- 对恢复执行、并行任务和审计回路都有明确关注，说明设计目标完整。

这些优点意味着：这份 skill 的问题主要不在“方向错了”，而在“结构还没有收敛到易维护、易复用的形态”。

---

## 风险评估

### 近期风险

- Skill 在不同代理环境中的行为不一致
- 关键触发字段看似丰富，实际未必生效
- checkpoint 时间戳错误影响恢复和诊断
- 用户确认机制不清，可能导致越权式自动执行

### 中期风险

- 单文件继续膨胀，导致上下文成本和漂移风险持续增加
- shell 逻辑碎片化，局部修复无法保证整体一致
- 项目文档与 skill 本体逐渐形成多份“真相来源”

---

## 整改优先级建议

### P0：优先立即处理

1. 修复 checkpoint heredoc 写法，确保 `updated_at` 为真实 UTC 时间。
2. 明确“生成规划后是否必须等待用户确认”这一行为决策，并统一正文表述。
3. 确定 skill 的目标运行环境是“Claude 专用”还是“面向 Codex 规范重构”。

### P1：建议本轮完成

1. 将单文件重构为标准 skill 目录结构：
   - `SKILL.md`
   - `references/`
   - `scripts/`
   - `agents/`
2. 将任务板规范、审计规则、故障排查拆到参考文档中。
3. 将任务解析、状态更新、并行调度等逻辑抽成脚本。

### P2：后续增强

1. 为 `agents/openai.yaml` 增加界面元数据。
2. 为 `scripts/` 补充自动化测试。
3. 将文档中的工具名依赖改写为更抽象的意图级指令，降低环境耦合。

---

## 建议的重构方向

建议将下一版本定义为“**v3 结构收敛版**”，目标不是增加更多功能，而是完成以下收敛：

- `SKILL.md` 只保留：
  - skill 目的
  - 触发场景
  - 核心工作流
  - 何时读取哪个参考文件
  - 何时运行哪个脚本

- `references/` 存放：
  - `workflow.md`
  - `task-board.md`
  - `audit.md`
  - `runtime-claude.md`
  - `runtime-codex.md`

- `scripts/` 存放：
  - `init_state.sh`
  - `select_next_task.sh`
  - `update_task_status.sh`
  - `detect_stall.sh`
  - `summarize_progress.sh`

这样可以在不改变产品目标的前提下，大幅降低上下文负担并提升演进能力。

---

## 最终判断

当前 skill **值得优化，而且建议尽快优化**。

它已经具备不错的流程设计雏形，但在“是否符合当前 skill 最佳实践”和“是否适合继续扩展”这两个问题上，答案都偏向否定。最合理的下一步不是继续加功能，而是先做一次结构重构，把这份 skill 从“长篇操作说明”整理成“轻量入口 + 可验证脚本 + 按需加载参考文档”的形态。
