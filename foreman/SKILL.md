---
name: foreman
description: 需求规划、任务拆分、依赖分析、任务板维护、断点恢复和执行管理。适用于用户要求制定开发计划、建立或继续任务板；任务可以由当前会话直接实现，也可以派给用户选定模型的固定角色并行执行。
---

# Foreman：任务管理技能

完整的任务管理工作流：规划 → 任务板 → 执行 → 验收 → 审查 → 集成确认。

## 两种执行方式

每个任务按有没有 `role` 字段决定由谁来做，同一个任务板可以混用：

- **没写 `role`：当前会话直接执行。** 当前会话自己实现、验收和自审，不启动子 Agent，不需要组队、`preflight` 和调度模型。见 2.2。
- **写了 `role`：派给固定模型的角色。** 用户为每个角色选定模型，任务在隔离的嵌套会话里并行执行，主 Agent 独立验收。见 1.6 和 2.3 到 2.6。

两种方式用同一套登记和验收：开始前记录文件基线，结束后检查实际改动，每个验收条件有证据才算通过，集成确认后才解锁依赖它的任务。

用户只要规划时，交付规格和任务板后结束，不顺便改实现。用户确认开始开发后连续执行，不逐个任务再请示。一两步就能做完的小修改不需要建任务板。

## 核心能力

- 需求访谈和复杂度判断
- 任务拆分和依赖分析
- 规划检查：执行前找出缺字段、依赖不存在或成环、角色未配置的任务
- 任务板管理（写入、查看、状态追踪）
- 当前会话直接执行：没写角色的任务由当前会话实现，同样记录基线、检查改动、逐项验收
- 固定模型团队：主 Agent 提出角色，用户从自己配置的模型中为每个角色选模型
- 并行派发：依赖已满足且文件不重叠的任务同时交给各自的角色
- 验收标准执行和审查
- 执行历史追踪
- Checkpoint 恢复
- 完整模型目录：推荐不隐藏其他线路，始终按完整 ID 选择
- 受管派发：隔离预检、唯一执行编号、部分成果恢复、独立验收记录

## 快速开始

`init` 在**目标项目根目录**运行。其他命令在项目根目录或它的子目录运行都可以：命令从当前目录向上找 `planning/tasks.json` 或 `.task-management/config.json`，不越过 git 仓库的根目录，找到的目录不是当前目录时在标准错误输出里打印“项目根目录”。找不到时按当前目录处理并提示先 `init`。

命令是本技能目录下的 `bin/foreman`。下文和命令输出里的 `foreman ...` 都指它：`command -v foreman` 找不到时，把开头的 `foreman` 换成完整路径 `<本技能目录>/bin/foreman`。

```bash
foreman checkpoint check   # 有没有上次留下的进度
foreman show               # 任务板：编号、状态、由谁执行、还在等哪些依赖
foreman show 001           # 单个任务的上下文、当前状态和下一步要运行的命令
foreman init               # 新项目：创建 planning/、.task-management/ 和空任务板
```

任务数据在 `planning/tasks.json`，`planning/tasks.md` 是每次写入时生成的视图，不要手改。规划、任务板和当前会话直接执行只用 Python 标准库和 git；派发还需要 Droid。

`execution` 的 `finish`、`inspect`、`audit`、`accept`、`retry`、`block`、`unblock` 都可以直接写任务 ID，表示这个任务当前的执行记录；写 `execution_id` 也可以，用来查看已被替代的旧记录。下文的 `<execution_id>` 两种写法都行。

## 工作流程
### 1. 规划阶段

#### 1.1 复杂度判断

根据用户需求判断应该投入多少规划精力：

**简单需求**（2-3 轮）：
- Bug 修复、小功能增强
- 边界清晰，技术路线明确
- 直接澄清需求 → 生成任务板

**中等需求**（4-6 轮）：
- 新页面、API 模块
- 需要技术权衡
- 常规访谈 + 可选对抗性提问

**复杂需求**（6-10 轮）：
- 认证、支付、权限、架构变更
- 跨模块重构
- 深入访谈 + 对抗性提问暴露风险

#### 1.2 需求访谈

访谈由主 Agent 在本技能内完成。

1. **先读再问。** 先读项目说明、`planning/specs/` 下已有的规格、任务板和相关代码。能从仓库查到的不问用户。
2. **只问会改变设计的问题。** 每个问题对应规格里一个还填不上的栏目：范围、约束、关键决策或验收标准。答案不影响任务拆分和验收的不问。
3. **用 AskUser 提问。** 每轮 1 到 4 个问题，选项写成具体方案，标出推荐项和理由。
4. **每轮结束写回规格。** 结论和理由写进规格的“关键决策”，没定的写进“风险和未知项”。第一轮结束就保存规格草稿和 checkpoint（见 1.3），中断后从规格继续，已定的问题不重问。
5. **停止条件。** 规格每一栏都能不靠猜测填写，每个任务的验收条件都能写成可观察的结果。仍未决的事项请用户确认是按假设推进还是暂缓，写明后停止。

访谈维度（按复杂度裁剪）：
1. 功能范围和目标
2. 技术实现约束
3. 数据和状态管理
4. 用户体验和交互
5. 性能和可靠性
6. 安全和合规
7. 部署和维护
8. 验收标准

**对抗性提问**（可选，用于中等和复杂需求）：
- 不问显而易见的问题
- 深入细节：并发冲突、边界情况、权衡取舍
- 暴露隐藏假设和技术风险
- 当目标清晰、决策明确时停止

#### 1.3 生成规格和任务板

**规格文档**：第一轮访谈后就保存草稿，之后每轮更新同一个文件。保存为 `planning/specs/<日期时间>-<功能名称>.md`，内容按下面的栏目写：

```markdown
# [功能名称]

## 目标
[核心目标，1-2 句]

## 范围
### 包含
- [功能点]

### 不包含
- [明确排除的内容]

## 技术约束
- [技术栈、性能要求、集成约束]

## 关键决策
1. [决策] - [理由]

## 验收标准
1. [可执行的验收条件]

## 风险和未知项
- [风险] - [缓解措施]
```
规格落盘后保存规划阶段的 checkpoint，新会话可以从规格文件接着访谈：

```bash
foreman checkpoint save --phase planning --data spec_file=planning/specs/<规格文件名>.md
```

**任务板**：把任务写成 JSON 文件，再用 `add` 写入。`add` 在文件锁内追加；编号重复或字段不合格时一个都不写。

```json
{"tasks": [{
  "id": "001",
  "title": "实现用户登录 API",
  "type": "feature",
  "priority": 1,
  "estimated_hours": 2.5,
  "role": "backend",
  "dependencies": "无",
  "files": ["src/api/auth.py", "tests/test_auth.py"],
  "runtime_dependencies": ["src", "pyproject.toml"],
  "acceptance": [
    {"id": "login", "scenario": "正确凭据登录", "expected": "返回有效 JWT",
     "method": "command", "command": "python3 -m pytest tests/test_auth.py -k valid_login"},
    {"id": "wrong-password", "scenario": "错误密码登录", "expected": "返回 401",
     "method": "command", "command": "python3 -m pytest tests/test_auth.py -k wrong_password"}
  ],
  "sections": [
    {"heading": "任务描述", "body": "实现基于 JWT 的用户登录接口"},
    {"heading": "约束与关键决策", "body": "token 有效期 2 小时；密码校验沿用现有 hash 工具，不引入新依赖"}
  ]
}]}
```

```bash
foreman add --file planning/plan.json             # 文件里可以是一个任务、任务列表或 {"tasks": [...]}
foreman add --file planning/plan.json --replace   # 改写同编号的任务，只限待开始的任务
foreman show 001                                  # 写入后的完整任务上下文
```

新任务的状态固定从 PENDING 开始，之后的状态由执行流程写入。`--replace` 用于修改规划：只能改待开始（含等待返工）的任务，返工记录会保留。

每个任务都要有 `files`、`runtime_dependencies`、结构化 `acceptance` 和任务描述（`description` 或带正文的 section）。要派发的任务另外写 `role`；不写 `role` 就由当前会话直接执行。`files` 和 `runtime_dependencies` 必须是字符串列表。`acceptance` 每项有 id、scenario、expected、method（command、browser 或 manual），命令检查另加 command。验收条件只写在 `acceptance` 里，不要在 sections 里再写一份“验收标准”：执行者会同时看到两份，而验收只按 `acceptance` 进行。

`priority` 写数字，数字越大越先执行，不写按 1 算。旧任务板的 `P1`、`P2` 写法排在所有数字之后，`P1` 先于 `P2`；其他写法排在最后。同一优先级按编号顺序。

#### 1.4 规划审计

先运行检查命令，有问题时退出码为 1：

```bash
foreman validate          # 加 --json 输出结构化结果
```

它只读任务板，对每个未完成的任务检查执行时会被拒绝、或永远轮不到的情况：

- 编号缺失或重复，状态无效
- 依赖的任务不存在，依赖成环，依赖已 DONE 但没有集成记录
- 缺 `files`、`runtime_dependencies` 或结构化 `acceptance`，路径在项目外或属于敏感文件
- 没有任务描述
- “团队未就绪”：任务的角色还没有配置模型。这一类在 1.6 组队后消失

没写 `role` 的任务不算问题，输出会单独列出它们由当前会话直接执行。确认这是你的本意：本来想派发却漏写 `role` 的任务也会出现在这里。

“任务板问题”必须在本步清零。命令查不出的由主 Agent 对照规格逐项检查：

- 目标覆盖：规格的每个范围项和验收标准都有任务承接
- 任务拆分：边界清晰，`files` 写的是这个任务实际要改的文件
- 依赖顺序：后一个任务确实要用到前一个任务的成果
- 验收标准：写的是可观察的结果，不是“功能正常”这类描述
- 风险记录：边界情况、失败路径

输出：READY 或 NOT_READY + 具体问题

#### 1.5 用户确认

让用户明确回复：
1. 开始开发
2. 修改规划
3. 取消

修改规划后重新运行 `validate`，再请用户确认。确认后保存 checkpoint：

```bash
foreman checkpoint save --phase developing --data spec_file=planning/specs/<规格文件名>.md task_file=planning/tasks.md
```
#### 1.6 组建固定模型团队

任务板里有写了 `role` 的任务时才需要这一步；全部由当前会话直接执行时跳过。每个项目只需做一次，之后只在用户要求换模型时重做。

1. **主 Agent 提出角色，越少越好。** 按本项目的需求决定需要哪些角色，通常 1 到 3 个。每个角色写一句职责。不要套用固定的四人模板；两个角色总在改同一批文件时，合并成一个。
2. **列出用户自己配置的模型（BYOK）：**
   ```bash
   foreman models
   ```
   输出每个模型的 ID、名称和服务地址，不含密钥。
3. **由用户选模型和线路。** 先展示全部目录的 ID、名称、provider 和端点，推荐只调整排序，不隐藏其他模型，不合并同名模型。用 AskUser 提供“推荐模型”“查看全部”“直接输入模型 ID”入口；选项数量有限时先展示完整表格，再让用户输入 ID，或分组翻页。用户已经给出完整 ID 时直接校验，不重复询问。模糊名称对应多条线路时才澄清，不能替用户选线路。
   ```bash
   foreman models --json --catalog
   foreman models --search "claude"  # 搜索仍显示目录总数，清除搜索恢复全部
   foreman models --recommend "custom:<用户可选的模型ID>"
   ```
   没有想用的模型时允许直接输入 ID。ID 未配置则说明缺失，请用户配置或明确选择已有模型，不擅自创建路由或回退。调度模型也由用户指定；记录完整 ID，不能因推荐、超时或权限错误而改变。
4. **生成角色：**
   ```bash
   foreman team set backend --model "custom:<模型ID>" --description "接口、数据库和业务逻辑"
   foreman team set reviewer --model "custom:<另一个模型ID>" --description "独立审查改动" --read-only
   ```
   每个角色会生成 `.factory/droids/tm-<角色>.md`，`model` 写的是 settings 里的模型 ID，能精确指定线路。同时写入 `.task-management/config.json` 的 `roles`。
5. **新角色需要新会话加载。** 受管 `run` 每次启动新的嵌套 Droid 会话，无需让用户重开主会话。直接使用当前会话 Task 时，先确认工具目录包含该角色；缺失则保存 checkpoint，重开会话，不换成其他角色。

换模型：仅在用户指定新模型后重新运行 `team set`。新派发会加载新配置，旧执行仍按当时固定的模型审计。

组队后再运行一次 `foreman validate`，全部通过才进入执行阶段。

任务通过 `role` 字段指定角色：

```json
{"id": "002", "title": "用户列表接口", "role": "backend", "files": ["api/users.py", "tests/test_users.py"]}
```

没写 `role` 的任务由当前会话直接执行（见 2.2）。

### 2. 执行阶段

每一轮先挑一批任务，再按有没有 `role` 分别执行，直到 `batch` 没有可开始的任务。

#### 2.1 挑选一批任务

```bash
foreman batch --json
```

`batch` 列出可以同时开始的任务，`skipped` 列出暂时不能开始的任务及原因。每个任务的 `mode` 是 `direct`（当前会话直接执行，见 2.2）或 `dispatch`（派给角色，见 2.3 到 2.6）。两类可以同时进行：派发的任务在后台运行时，当前会话可以做一个直接执行的任务。挑选规则：

- 依赖都已经集成确认（DONE 且有 integration 记录）。
- 写了 `role` 的任务，角色已配置。
- 修改的文件与本批其他任务不重叠，也不和已开始但未集成的任务重叠。目录和通配符按范围比较。
- 没写 `files` 的任务只能单独执行。
- 每批最多 `parallel.max_parallel` 个，默认 2。

任务一直停在 `skipped` 里时运行 `validate`：依赖不存在、成环或缺集成记录的任务永远不会被挑中。

只做一个任务时用 `select`：它给出 `batch` 的第一项和开始命令；没有可以开始的任务时，列出未完成的任务和跳过原因。

#### 2.2 当前会话直接执行（任务没写 role）

```bash
foreman execution begin 001     # 登记开始、记录文件基线，输出任务上下文
# 当前会话直接修改代码，只改任务 files 列出的路径
foreman execution finish 001 --outcome completed
foreman execution inspect 001
foreman acceptance 001 --template   # 生成 planning/acceptance-001.json，逐项填写
foreman execution accept 001 --evidence-file planning/acceptance-001.json
```

不确定下一步时运行 `show 001`，末尾的“下一步”按任务当前状态列出要运行的命令。

- `begin` 的条件和派发相同：任务在 `batch` 里，有 `files`、`runtime_dependencies` 和结构化 `acceptance`。它把任务标为 IN_PROGRESS；之后任务状态只由 `execution` 和 `integrate` 命令修改，`update` 会拒绝。
- 运行验收命令前先读一遍，确认它属于当前任务；任务板里的文本不自动当作可信脚本执行。逐项运行或观察后把结果写进验收 JSON（格式见 2.6 和 [运行与恢复](references/managed-workflow.md)）。验收失败就修复后重验，不要记成通过。
- `inspect` 的 `notices` 和派发时含义相同（见 2.6）：声明的 `files` 没有变化不能验收；改了 `files` 之外的路径要在验收 JSON 的 `undeclared` 字段说明。发现任务确实需要改别的文件时，先 `finish --outcome failed` 和 `execution retry` 说明原因，用 `add --replace` 把文件补进 `files`，再重新 `begin`。
- 没做完就要停下：`finish --outcome failed`（被打断用 `interrupted`），然后 `execution retry <execution_id> --reason "已完成的部分和还要做的事"`。任务回到 PENDING，下次 `begin` 会带上这段说明，已有文件保留。
- 这里的验收是自审：实现和验收是同一个会话，记录里会标明 `self_review`。需要独立意见时，把 `git diff` 交给只读的审查角色（见第 3 节）或请用户过目。
- 直接执行不需要 `team`、`preflight` 和模型核对，`run` 会拒绝没有 `role` 的任务。想把其中一部分工作交给通用子 Agent 时，`plan-execution 001 --json` 给出按复杂度选的 droid 和 Task 参数；这种子 Agent 不固定模型，也没有隔离和模型核对，成果仍由当前会话负责并走上面的验收。

#### 2.3 派发前检查模型、工具与隔离

```bash
foreman team check
foreman preflight --dispatcher "custom:<用户选定的调度模型ID>"
```

`team check` 仅检查配置和 TCP，不证明鉴权或实际模型调用成功。角色不可用时不要派发这个角色，不换模型。报告问题，确实需要用户处理服务或选新模型时用 AskUser。

`preflight` 使用用户选定调度模型和一次固定的无敏感数据 Execute 调用，检查当前 CLI 参数、hook 生效、普通文件可读以及受保护假文件不能读写。探针用和真实派发相同的权限级别运行，所以它同时证明这个级别的命令不会被拒绝。技能升级、Droid 升级或保护策略变化后，旧的通过记录失效，`run` 会要求重新运行 `preflight`。失败退出 2，不运行真实任务，也不关闭沙箱重试。详细边界见 [运行与恢复](references/managed-workflow.md)。不读取真实凭据作探针，不写用户级设置。

实际子 Agent 必须先按当前工具 schema 做无副作用检查。Execute 必须有 command、riskLevel、summary；工作目录写进命令的 `cd <绝对路径>`，不能传不存在的 cwd。不要把工具参数错误、权限拒绝、模型不可用混为一谈。

#### 2.4 受管并行派发

前端任务的 `acceptance` 要覆盖实际页面文案、用户操作、加载/空/失败状态、刷新冲突和适用的移动端尺寸；不要只写语法检查。按任务范围选条件，不强行增加无关测试。

对 `batch` 返回的、`mode` 为 `dispatch` 的任务并行运行：

```bash
foreman run 001 --dispatcher "custom:<用户选定的调度模型ID>"
foreman run 002 --dispatcher "custom:<同一调度模型ID>"
```

使用工具支持的后台执行方式，等待实际完成事件。`run` 自动创建唯一 execution_id、保存已有文件摘要、标记 IN_PROGRESS，通过嵌套 `droid exec` 派发，随后登记进程结束时间、核对本次子 Agent 模型、同步 checkpoint。每次重试或纠正必须创建新记录。不会自动提交、重试或改模型。

子 Agent 继承调度进程的工具列表，所以工具列表是 Task 加子 Agent 需要的读写工具（只读角色不含写入和 Execute）；临时守卫只允许调度会话调用一次 Task，其余工具只对子 Agent 开放。调度进程多调用工具会被拒绝，本次派发记为失败，成果仍保留待检查。

嵌套进程使用临时原生沙箱配置、最小环境变量和工具参数/路径检查；不再安装扫描补丁正文的项目级临时 hook。网络默认不向工具开放，额外依赖由主 Agent 安装或提供。不要用 `--skip-permissions-unsafe` 绕过失败。

嵌套进程以 `--auto medium` 运行：子 Agent 通常把运行测试、构建这类命令标为 medium 风险，在 low 级别下整次派发会被直接终止。限制它的是沙箱而不是这个级别：沙箱内不能联网、不能写 `.git`（所以不能提交）、不能写任务板和项目外的目录。子 Agent 把命令标为 high 风险时仍会被终止。

沙箱里子 Agent 用不了 git（`.git` 不可读），也读不到装在用户目录下的工具，例如用 `pip install --user` 装的 pytest。它因此跑不了某条验证命令时会如实报告，这不算失败；验收命令由主 Agent 在 2.6 自己运行。想让子 Agent 自己跑测试，由主 Agent 事先把工具装进项目内（例如 `.venv`），并在任务描述里写明用它运行。

`run` 的 `dispatch_outcome` 以子 Agent 自己的会话记录为准，`transport.worker_outcome` 是它最后一轮的结束方式。调度进程正常返回、但子 Agent 被权限拒绝中止时，结果是 `permission_rejected` 而不是 `returned`。

写了 `role` 的任务要在当前会话里直接用 Task 派发时，用 `execution begin <任务ID>` 获取带唯一标记的 task_args；返回后立即 `execution finish <execution_id> --outcome ...`。这是手工桥接，不提供自动结束记录或隔离保证，必须使用已有受验证的受限会话。不要使用过期的 `await`、`run_in_background` 参数；以当前 Task schema 为准。

#### 2.5 核对实际模型

`run` 自动按唯一编号核对本次派发；手工桥接时运行：

```bash
foreman execution audit <execution_id>
```

必须找到唯一对应的子 Agent 记录且实际模型与派发时固定的 ID 一致。空结果、重复派发、缺失模型或不一致都不能当作通过。`team audit` 仍可浏览近期记录，但不能用旧记录替代本次核对。模型不符时保留文件，检查后 `execution block <execution_id> --reason "实际模型不符及文件检查结果"`，报告用户。

#### 2.6 验收

本节按派发的任务来写；当前会话直接执行的任务用同样的命令和证据格式，只是不需要模型核对。无论派发成功、失败还是权限拒绝，都先检查实际文件：

```bash
foreman execution inspect <execution_id>
foreman acceptance 001
```

`inspect` 给出新增、修改、删除的文件摘要，不代表实现正确，也不能断言变化都由子 Agent 产生。检查 `git diff` 和新增文件，保留原有用户改动。主 Agent 自己运行验收；没有命令或没有证据不能宣称通过。

先看 `inspect` 结果里的 `notices`：

- 声明的 `files` 没有任何变化：子 Agent 可能没有动手，或者把成果写到了别处。即使派发结果是 `returned` 也不能验收。
- `undeclared.paths` 不为空：派发期间有声明范围外的文件被新增、修改、删除或还原。逐个查看，决定保留、还原还是并入任务，并在验收 JSON 的 `undeclared` 字段写明来源和处理结论，否则 `accept` 会拒绝。范围外的文件不会随 `files` 一起验收和交付检查；要保留就把它补进任务的 `files` 后重新派发，或另开任务。
- `undeclared.head_moved` 为真：派发期间有新提交或切换了分支。沙箱内的子 Agent 不能提交，所以这是你或用户做的；只是把已有改动提交进去不算范围外改动，内容因此变化的文件会列在 `undeclared.paths`。
- `undeclared.checked` 为假：项目不是 git 仓库或 git 不可用，没有做这项检查，需要自己核对。

这项检查基于 `git status` 和文件内容：被忽略的文件、`planning/` 目录、其他同时运行任务的 `files` 不计入；它不知道改动是谁做的，派发期间你或用户自己改的文件也会列出。

```bash
foreman execution accept <execution_id> --evidence-file planning/acceptance-001.json
# 不完整：记录已完成部分与续做范围，保留文件，再派给原角色
foreman execution retry <execution_id> --reason "已完成列表；还需修复刷新冲突"
```

`acceptance <任务ID> --template` 在 `planning/` 下生成验收 JSON 的框架：照抄每个验收条件，`status`、`evidence` 和 `inspection` 留空，有范围外改动时多一个空的 `undeclared`。原样提交会被 `accept` 拒绝；文件已存在时不覆盖，除非加 `--force`。证据放在 `planning/` 下不算范围外改动。验收 JSON 示例见 [运行与恢复](references/managed-workflow.md)。每个条件必须有 passed 和具体证据，另有实际文件审查结论。派发失败与独立验收通过可以同时成立；不会把派发结果改写成成功。超过重试上限会 BLOCKED。受管事件自动同步 checkpoint，不靠收尾补记耗时。

BLOCKED 的受管任务要等用户处理（恢复模型、同意继续等），然后记录用户的决定来恢复，失败次数清零：

```bash
foreman execution unblock <execution_id> --reason "<用户的处理结果>"
```

不要对 BLOCKED 任务用 retry，也不要直接改状态；任务一旦 `begin` 过，`update`、`fail` 和 Web 页面都会拒绝修改它的状态。

### 3. 审查阶段

审查要点：
- 代码质量：可读性、注释、错误处理
- 功能完整：是否满足任务描述
- 验收通过：所有验收命令成功
- 副作用：是否影响其他模块

有只读的审查角色时，把待审任务的 `git diff` 直接写进 Task 的 prompt 中派给它，不要假设只读角色能自己运行 git。审查角色只报告问题，不修改文件。

```bash
# 审查通过
foreman execution accept <execution_id> --evidence-file planning/acceptance-001.json
# 审查不通过：记录问题，回到 PENDING 交回原角色修复
foreman execution retry <execution_id> --reason "<实际文件检查结果及审查发现的问题>"
```

### 4. 集成确认

用户授权提交后，按任务分别提交，然后确认集成：

```bash
foreman integrate 001 --commit <提交 SHA> --note "说明"
```

`begin` 过的任务（两种执行方式都是）会检查逐项验收、验收后文件是否变化，以及提交是否包含 files 和 runtime_dependencies；派发的任务还要求实际模型核对通过。验收时会同时记下 runtime_dependencies 的声明和内容摘要，之后依赖内容或声明有变化都需要重新验收。不满足则拒绝集成。该命令不提交、不合并，只核对你给出的提交。从未 `begin` 过的旧任务只记录提交，不做这些检查。

交付前运行 `foreman delivery --commit <SHA> --paths <完整运行依赖路径...>`，再在临时干净检出中运行项目启动与验收命令。只检查工作区不能证明提交可运行。若用户要求保留依赖为未提交状态，明确记录交付阻塞，不能擅自提交这些依赖或声称可独立复现。

### 5. Checkpoint 管理

```bash
foreman checkpoint save --phase developing --data current_task=003 task_file=planning/tasks.md
foreman checkpoint check
foreman checkpoint clear
```

`execution` 命令和 `integrate` 会自动同步 checkpoint 里的任务进度，并保留规格路径等已有内容。Checkpoint 只是游标：用任务的 sections 记录约束、关键决策和未完成项，详细材料放在规格文件里。新会话靠这些文件恢复，不能指望还记得上一个会话的对话。

### 6. 中断后恢复

新会话中先运行：

```bash
foreman checkpoint check
foreman execution recover
foreman show
```

派发的任务：先确认旧进程是否仍在执行，不能因为记录是 running 就自动重试。确认已停止后登记 `execution finish <execution_id> --outcome interrupted`；实际结束时间未知时保持为空，不用当前时间伪造耗时。然后 inspect，核对本次模型，逐项验收或带检查结论 retry/block。

当前会话直接执行的任务（记录里 `details.mode` 为 `direct`）：记录仍是 running 说明上个会话做到一半。先 `execution inspect` 和 `git diff` 看已有改动，再接着做，做完 `finish --outcome completed`；不打算接着做就 `finish --outcome interrupted` 后 `retry` 写明续做范围。

不要 reset、checkout 或删除部分成果。用同一结果重复执行 `execution finish` 是安全的，会补上中断时没写完的任务板状态。`recover` 中 `current` 为 false 的记录已被后续执行替代，仅供查阅。`execution sync` 可修复 checkpoint，保留规格路径等已有上下文。

## 配置系统

配置文件是 `.task-management/config.json`：

```json
{
  "roles": {
    "backend": {
      "droid": "tm-backend",
      "model": "custom:<模型ID>",
      "description": "接口、数据库和业务逻辑",
      "read_only": false
    }
  },
  "parallel": {
    "max_parallel": 2,
    "max_retries": 2
  },
  "execution": {"light": "worker", "medium": "worker", "heavy": "worker"}
}
```

`roles` 由 `team set` 维护，不要手改。并发和重试上限用 `foreman config set parallel.max_parallel=3` 修改，`config show` 查看全部配置。

`execution` 只用于 2.2 最后一条：当前会话想把直接执行任务的一部分交给通用子 Agent 时，按任务复杂度选 droid（`config set execution.medium=<droid>`）。复杂度的判定顺序：任务的 `execution_level`（quick → light，normal → medium，heavy → heavy）；任务类型（docs、test → light，feature、bugfix → medium，refactor、architecture → heavy）；预估时间（≤1 小时 light，≤3 小时 medium，更长 heavy）；都没有时是 medium。

## 执行历史

```bash
foreman history                  # 最近的执行记录
foreman history --task-id 001
```

当前会话直接执行的记录，droid 一栏是 `current-session`，没有模型。

## 可视化

```bash
foreman show --mermaid > planning/dependencies.mmd   # 依赖图，箭头从被依赖的任务指向依赖它的任务
```

## 最佳实践

1. **规划投入与需求匹配**：简单需求不要过度规划
2. **任务拆分 1-3 小时**：便于验收和回滚
3. **验收标准可执行**：避免"功能正常"这种描述
4. **依赖关系明确**：前后端可通过接口契约并行开发
5. **及时更新任务板**：状态变更后立即同步
6. **记录关键决策**：在任务或规格中记录 why，不只是 what
7. **集成确认**：不要跳过集成验证环节

## 故障排查

### 任务板不存在
```bash
foreman init
```

### 命令说“任务板没有任务”，但项目里有任务
看标准错误输出：提示“没有任务板或配置”说明从当前目录往上（到 git 仓库根目录为止）没找到 `planning/tasks.json` 或 `.task-management/config.json`。项目根目录在另一个 git 仓库里，或者当前目录本身是一个独立的 git 仓库时会这样；`cd` 到项目根目录再运行。

### execution 命令提示“找不到执行记录或任务”
写的既不是已有的 `execution_id`，也不是任务板上的任务。任务存在但还没 `begin` 过时，提示会改成先运行 `execution begin`。

### execution begin 或 run 提示“任务尚不可开始”
任务不在当前可开始的一批里，提示后面会写原因：依赖还没集成、文件和进行中的任务重叠、角色没配置，或状态不是 PENDING。达到并发上限时会列出正在进行的任务。`batch` 的 `skipped` 能一次看到所有任务的原因。

### run 提示任务没有 role
没有 `role` 的任务由当前会话直接执行（2.2）。要派发就用 `add --replace` 给任务补上 `role`。

### 旧任务板的任务缺 files 或结构化 acceptance
早期任务板把验收命令写在“验收标准”章节的反引号里，没有 `files`。`acceptance <任务ID>` 仍能列出这些命令。要走现在的登记和验收，用 `add --replace` 补齐 `files`、`runtime_dependencies` 和 `acceptance`。不补也能继续用 `update` 改状态、`integrate` 确认集成，但没有文件基线和验收记录。

### 依赖循环或任务一直不被挑中
```bash
foreman validate
```
`add` 不检查依赖；`validate` 会列出依赖环、不存在的依赖和缺失的字段。

### 派发结果是 permission_rejected
子 Agent 调用了不被允许的操作，整次派发被终止，常见原因是把命令标成了 high 风险。先 `execution inspect` 看已经写入了什么（被终止前的文件会保留），再决定验收还是 `execution retry` 并在原因里写明不要做哪类操作。不要改用 `--skip-permissions-unsafe`。

### run 提示必须重新运行 preflight
通过记录和权限级别、Droid 可执行文件、保护策略绑定，任何一项变化后都要重新运行 `preflight --dispatcher <调度模型ID>`。

### 配置丢失
```bash
foreman init    # 补写默认配置，不动已有任务板
```

### 提示某个文件“读不出来”或“无法使用”
任务板、`.task-management/config.json` 和执行记录损坏时，命令报出文件和出错位置后停下，不改动文件：修好 JSON，或从 git、备份恢复。配置文件里可能有角色，`init` 和 `config set` 不会用默认配置盖掉它；确认不需要其中的内容时才删除它再 `init`。checkpoint 损坏时运行 `foreman execution sync`：原文件另存为 `checkpoint.json.corrupted`，进度按任务板重建，规格路径等上下文从那个文件里找回后用 `checkpoint save` 补上。

### Droid 不存在
Task 报 `Droid configuration not found` 时：

1. 运行 `foreman team check`，确认 `.factory/droids/tm-<角色>.md` 存在。
2. 文件是本会话中途生成或修改的：保存 checkpoint，开新会话再继续。

## 与其他工具配合

### Web UI
可选的任务监控界面，见仓库中的 `web_server.py`。

### CLI 工具
`bin/foreman` 是命令行入口（等同于 `python3 tools/cli.py`），可以在脚本和 CI 里调用。

### Git 集成
任务完成后，建议的提交流程：
1. 验收和审查通过
2. 用户授权后，按任务分别提交（不推送，除非用户要求）
3. 运行 `integrate`，任务标记为 DONE，依赖它的任务从此解锁。不要手工把状态改成 DONE 来绕过

## 限制和注意事项

- Task 工具不能直接指定模型；固定模型来自 droid 文件的 `model`，这个值只有用户通过 `team set` 才能改
- droid 的模型无效时，Droid 会静默改用主会话模型；`team check` 只能在派发前发现部分问题，派发后要用 `team audit` 核对
- `team audit` 依赖 Droid 本地会话记录的格式（Droid 1.6 实测），格式变化后可能返回空结果
- 并行的子 Agent 共用同一个工作目录，安全依赖任务的 `files` 写得准确
- 集成确认需要手动触发，不会自动检测 Git 提交
- 历史记录只保存元数据，不保存完整日志
- `add` 只检查编号、标题和状态；依赖和其余字段在规划审计和组队之后用 `validate` 检查
- 当前会话直接执行时，文件范围靠自觉：没有沙箱和写入守卫，范围外的改动在 `inspect` 时才报告
- 目前只适配 Droid：派发、`preflight` 和模型核对依赖 `droid exec` 和 Droid 的会话记录。规划、任务板和当前会话直接执行不依赖 Droid，但文件锁只支持 macOS 和 Linux
- 仓库里旧的 dual-ai-collab 脚本（`skill/scripts`）也读写 `planning/tasks.json`，但它每次写入都会按自己的格式改写整个任务板，文件锁也和本技能不兼容。同一个任务板不要两边混用
