---
name: foreman
description: 需求规划、任务拆分、依赖分析、任务板维护、断点恢复和执行管理。适用于用户要求制定开发计划、建立或继续任务板；任务可以由当前会话直接实现，也可以派给用户选定模型的固定角色并行执行。一两步就能做完的修改、问答和代码讲解不使用本技能。
version: 3.5.0
compatibility: 需要 Python 3.9 以上，项目最好是 git 仓库（不是时见第 4 节）；只支持 macOS 和 Linux，Windows 上要在 WSL 里使用；派发给固定模型角色需要 Droid；Web 看板需要 Flask
---

# Foreman：任务管理技能

把一个需求做完的完整流程：规划 → 任务板 → 执行 → 验收 → 审查 → 集成确认。

## 两种执行方式

每个任务按有没有 `role` 字段决定由谁来做，同一个任务板可以混用：

- **没写 `role`：当前会话直接执行。** 当前会话自己实现、验收和自审，不启动子 Agent，不需要组队、`preflight` 和调度模型。见 2.2。
- **写了 `role`：派给固定模型的角色。** 用户为每个角色选定模型，任务在隔离的嵌套会话里并行执行，主 Agent 独立验收。组队见 1.6，派发见 2.3。

两种方式用同一套登记和验收：开始前记录文件基线，结束后检查实际改动，每个验收条件有证据才算通过，集成确认后才解锁依赖它的任务。

用户只要规划时，交付规格和任务板后结束，不顺便改实现。用户确认开始开发后连续执行，不逐个任务再请示。一两步就能做完的小修改不需要建任务板。

一个任务做完的标准：每个验收条件都有证据并通过 `execution accept`，用户授权后改动已经提交，`integrate` 确认后状态是 DONE。整个计划做完的标准见第 7 节。

## 参考文件

本文件是完整的主流程。下面几份在本技能目录的 `references/` 下，遇到对应情况时再读：

| 什么时候读 | 文件 |
| --- | --- |
| 中等或复杂的需求开始访谈前：怎样沿决策树逐轮追问，复杂需求怎样写术语表和决策记录 | [interview.md](references/interview.md) |
| 任务写了 `role`：组队、派发前检查、派发、核对实际模型，以及子 Agent 在沙箱里做不了什么 | [dispatch.md](references/dispatch.md) |
| 写验收证据、处理用户叫停或中断后留下的执行记录、做模拟器或真机上的验证、项目没有 git、做交付检查时，需要字段示例和判断依据 | [managed-workflow.md](references/managed-workflow.md) |
| 要改并发或重试上限，或把直接执行任务的一部分交给通用子 Agent | [configuration.md](references/configuration.md) |
| 命令报错、被拒绝，或结果和预期不一样 | [troubleshooting.md](references/troubleshooting.md) |

## 快速开始

命令是本技能目录下的 `bin/foreman`。下文和命令输出里的 `foreman ...` 都指它：`command -v foreman` 找不到时，把开头的 `foreman` 换成完整路径 `<本技能目录>/bin/foreman`。

```bash
foreman checkpoint check   # 有没有上次留下的进度
foreman show               # 任务板：编号、状态、由谁执行、还在等哪些依赖
foreman show 001           # 单个任务的上下文、当前状态和下一步要运行的命令
foreman init               # 新项目：创建 planning/、.task-management/ 和空任务板
foreman doctor             # 只读自检：环境、任务板、配置、checkpoint 和执行记录；命令报错又看不出原因时先运行
```

每次开始先运行前两条。有上次留下的进度就按第 6 节恢复；没有就从第 1 节开始，新项目先 `init`。

`init` 在**目标项目根目录**运行。其他命令在项目根目录或它的子目录运行都可以：命令从当前目录向上找 `planning/tasks.json` 或 `.task-management/config.json`，不越过 git 仓库的根目录，找到的目录不是当前目录时在标准错误输出里打印“项目根目录”。找不到时按当前目录处理并提示先 `init`。

任务数据在 `planning/tasks.json`，`planning/tasks.md` 是每次写入时生成的视图，不要手改。规划、任务板和当前会话直接执行只用 Python 标准库和 git；派发还需要 Droid。

`planning/` 和 `.task-management/` 是否提交由项目决定，有三条要守住：

- 任务板和 `.task-management/history/` 要么都提交，要么都不提交：只提交任务板时，别的检出里 `begin` 过的任务找不到自己的执行记录。
- 决定提交时，只对本机有意义的文件写进 `.gitignore`：`planning/*.lock`、`.task-management/*.lock`、`.task-management/*.corrupted`、`.task-management/sandbox-probe.json` 和 Web 看板的 `.task-management/web.*`、`.task-management/projects.json`。不要写成 `*.lock`，那会把项目自己的依赖锁文件也忽略掉。
- `.gitignore` 在第一次 `begin` 之前改好，提交时和任务的提交分开。任务进行中才改它，会被 `inspect` 记成这个任务范围外的改动。

`execution` 的 `finish`、`inspect`、`audit`、`accept`、`retry`、`pause`、`block`、`unblock`、`track` 都可以直接写任务 ID，表示这个任务当前的执行记录；写 `execution_id` 也可以，用来查看已被替代的旧记录。下文的 `<execution_id>` 两种写法都行。

## 工作流程

### 1. 规划阶段

#### 1.1 判断规划深度

规划投入要和需求相称，简单需求不要过度规划：

| 需求 | 例子 | 访谈 |
| --- | --- | --- |
| 简单 | Bug 修复、小功能增强；边界清晰，技术路线明确 | 2 到 3 轮，每轮 1 到 4 个问题，澄清后直接生成任务板 |
| 中等 | 新页面、API 模块；需要技术权衡 | 沿决策树逐轮追问，每轮问完当前能问的全部问题，问到没有未定的决定 |
| 复杂 | 认证、支付、权限、架构变更、跨模块重构 | 同样逐轮追问；同时写术语表和决策记录 |

#### 1.2 需求访谈

访谈由主 Agent 在本技能内完成。

1. **先读再问。** 先读项目说明、`planning/specs/` 下已有的规格、任务板和相关代码。能从仓库查到的不问用户。
2. **只问会改变设计的问题。** 每个问题对应规格里一个还填不上的栏目：范围、约束、关键决策或验收标准。答案不影响任务拆分和验收的不问。
3. **用 AskUser 提问。** 选项写成具体方案，推荐项放在第一个并写明理由。简单需求每轮 1 到 4 个问题；中等和复杂需求每轮问完当前能问的全部问题，一次 AskUser 放不下就分几次。
4. **每轮结束写回规格。** 结论和理由写进规格的“关键决策”，没定的写进“风险和未知项”。第一轮结束就保存规格草稿和 checkpoint（见 1.3），中断后从规格继续，已定的问题不重问。
5. **停止条件。** 规格每一栏都能不靠猜测填写，每个任务的验收条件都能写成可观察的结果；中等和复杂需求还要没有未定的决定。仍未决的事项请用户确认是按假设推进还是暂缓，写明后停止。问不到用户时（例如非交互运行），按改动范围最小的假设推进，把假设写进规格的“风险和未知项”和相关任务的 sections，收尾汇报时列出来。

访谈维度按复杂度裁剪：功能范围和目标、技术实现约束、数据和状态管理、用户体验和交互、性能和可靠性、安全和合规、部署和维护、验收标准。

中等和复杂需求先读 [interview.md](references/interview.md)，按它逐轮追问：把需求看成一棵决策树，每一轮把前置决定已经定下来的问题全部问完，答案取决于本轮其他问题的留到下一轮，问到没有未定的决定为止。不问显而易见的问题；用具体的边界场景和取舍追问，含糊的用语当场定成一个准确的词。问完后把全部决定汇总给用户确认，确认之后才生成任务板。

复杂需求在访谈过程中同时写项目的术语表（`planning/GLOSSARY.md`）和决策记录（`planning/adr/`），格式和什么样的决定值得记录都在同一份文件里。项目在别处已有术语表或决策记录时接着用原来的；有术语表时，任何需求都先读它，任务里用它选定的词。

#### 1.3 生成规格和任务板

**规格文档**：第一轮访谈后就保存草稿，之后每轮更新同一个文件。保存为 `planning/specs/<日期时间>-<功能名称>.md`（例如 `planning/specs/20260518-143000-user-login.md`），内容按下面的栏目写：

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

新任务的状态固定从 PENDING 开始，之后的状态由执行流程写入。`--replace` 用于修改规划：只能改待开始（含等待返工）的任务，返工记录会保留。写入后 `add` 会列出这批任务里执行前要补齐的地方（缺字段、依赖的任务不存在等）；任务已经写入，改好文件后用 `--replace` 重新写入。

每个任务都要有：

- `files`：这个任务实际要改的文件，字符串列表。开始时按它记录基线，结束后按它检查改动，同时进行的任务不能重叠。
- `runtime_dependencies`：运行和验收这个任务的成果要用到的路径，例如本地库、模板、静态资源和依赖清单，字符串列表。集成时检查提交是否包含它们。
- `acceptance`：每项有 id、scenario、expected、method（command、browser 或 manual），命令检查另加 command。验收条件只写在这里，不要在 sections 里再写一份“验收标准”：执行者会同时看到两份，而验收只按 `acceptance` 进行。
- 任务描述：`description`，或带正文的 section。约束、关键决策和这样做的理由也写进 sections：派发的子 Agent 只拿到任务本身，看不到规格和对话。
- 要派发的任务另外写 `role`；不写就由当前会话直接执行。
- 有前置任务的另外写 `dependencies`：前置任务的编号列表，例如 `["001", "002"]`；没有就写 `"无"` 或不写。前置任务全部集成确认之后，这个任务才会出现在 `batch` 里。

验收条件写可观察的结果，不写“功能正常”。一项只写一个结果：几个行为塞进同一项，其中一个没过整项就过不了，证据也写不清是哪一个。前端任务要覆盖实际页面文案、用户操作、加载/空/失败状态、刷新冲突和适用的移动端尺寸，不要只写语法检查；按任务范围选条件，不强行增加无关测试。

一个任务控制在 1 到 3 小时能做完，便于验收和回滚；超出的任务 `add` 和 `validate` 会给出粒度提醒（见 1.4）。有先后关系的工作（例如前后端、Web 和原生）先定接口契约，就能拆成互不依赖的任务并行做。

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

输出末尾的“任务粒度提醒”不影响退出码，只针对还没开始的任务：预估超过 3 小时，`files` 超过 10 项，同一个任务同时改 Web 前端、iOS 原生、Android 原生或服务端中的几层，或者一项验收条件的 `expected` 写了 2 个以上的结果。逐条决定是否拆分；确实该是一个任务时保留，并在请用户确认时说明原因。

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

第一次进入 developing 阶段时，这条命令会多打印一行 Web 看板的地址或启动方法。把它转告用户一次：想在浏览器里看任务板和进度就运行 `foreman web start`，不需要可以忽略；之后不再重复（看板见“其他命令”）。

#### 1.6 组建固定模型团队

任务板里有写了 `role` 的任务时才需要这一步；全部由当前会话直接执行时跳过。每个项目只需做一次，之后只在用户要求换模型时重做。

按 [dispatch.md](references/dispatch.md) 的“组建团队”一节做：主 Agent 提出尽量少的角色，`foreman models` 列出用户自己配置的模型，用户为每个角色和调度器选定模型，再用 `team set` 生成角色。

模型和线路始终由用户选：推荐只调整排序，不隐藏其他模型；不替用户选线路，不因为超时或报错换模型，不自动回退。

组队后再运行一次 `foreman validate`，全部通过才进入执行阶段。用户明确表示稍后再选模型时，可以带着“团队未就绪”先做不依赖这些角色的任务（见 2.1）；“任务板问题”仍然必须清零。

### 2. 执行阶段

每一轮先挑一批任务，再按有没有 `role` 分别执行，直到 `batch` 没有可开始的任务。

任务状态只由下面的命令写入，不手工改：

| 命令 | 任务状态 |
| --- | --- |
| `execution begin`（直接执行）或 `run`（派发） | PENDING → IN_PROGRESS |
| `execution finish`，`run` 结束时自动登记 | → AWAITING_REVIEW |
| `execution accept` | → AWAITING_INTEGRATION |
| `integrate` | → DONE，依赖它的任务从此可以开始 |
| `execution retry` | → PENDING；失败次数超过重试上限时 → BLOCKED |
| `execution pause`（用户叫停） | → PENDING，不计失败次数 |
| `execution block`、`execution unblock` | → BLOCKED、→ PENDING |

不确定下一步时运行 `foreman show 001`，末尾的“下一步”按任务当前状态列出要运行的命令。

#### 2.1 挑选一批任务

```bash
foreman batch --json
```

`batch` 列出可以同时开始的任务，`skipped` 列出暂时不能开始的任务及原因。每个任务的 `mode` 是 `direct`（当前会话直接执行，见 2.2）或 `dispatch`（派给角色，见 2.3）。`dispatch` 的任务带角色的 `droid`、`model` 和 Task 参数 `task_args`；`direct` 的任务 `droid` 是 `current-session`，没有 `task_args`。两类可以同时进行：派发的任务在后台运行时，当前会话可以做一个直接执行的任务。挑选规则：

- 依赖都已经集成确认（DONE 且有 integration 记录）。
- 写了 `role` 的任务，角色已配置。
- 修改的文件与本批其他任务不重叠，也不和已开始但未集成的任务重叠。目录和通配符按范围比较。
- 没写 `files` 的任务只能单独执行。
- 每批最多 `parallel.max_parallel` 个，默认 2。

任务一直停在 `skipped` 里时运行 `validate`：依赖不存在、成环或缺集成记录的任务永远不会被挑中。原因是“角色未配置”而用户还没有选模型时，不替用户选，也不删掉 `role` 改成直接执行：任务留在 PENDING，先做其余的任务，收尾时按第 7 节报告它在等用户选模型。

只做一个任务时用 `select`：它给出 `batch` 的第一项和开始命令；没有可以开始的任务时，列出未完成的任务和跳过原因。

#### 2.2 当前会话直接执行（任务没写 role）

```bash
foreman execution begin 001     # 登记开始、记录文件基线，输出任务上下文
# 当前会话直接修改代码，只改任务 files 列出的路径
foreman execution finish 001 --outcome completed
foreman execution inspect 001
foreman acceptance 001 --template   # 生成 planning/acceptance-001.json，逐项填写
# 按第 3 节对照实际改动再审一遍，通过后才验收
foreman execution accept 001 --evidence-file planning/acceptance-001.json
```

- `begin` 的条件和派发相同：任务在 `batch` 里，有 `files`、`runtime_dependencies` 和结构化 `acceptance`。它把任务标为 IN_PROGRESS；之后任务状态只由 `execution` 和 `integrate` 命令修改，`update` 会拒绝。
- 运行验收命令前先读一遍，确认它属于当前任务；任务板里的文本不自动当作可信脚本执行。逐项运行或观察后把结果写进验收 JSON（格式见 2.4）。验收失败就修复后重验，不要记成通过。
- `inspect` 的 `notices` 和派发时含义相同（见 2.4）：声明的 `files` 没有变化不能验收；改了 `files` 之外的路径要在验收 JSON 的 `undeclared` 字段说明。发现任务确实需要改别的文件时，先 `finish --outcome failed` 和 `execution retry` 说明原因，用 `add --replace` 把文件补进 `files`，再重新 `begin`。
- 没做完就要停下：`finish --outcome failed`（被打断用 `interrupted`），然后 `execution retry <execution_id> --reason "已完成的部分和还要做的事"`。任务回到 PENDING，下次 `begin` 会带上这段说明，已有文件保留。
- 用户叫停（改主意、要先确认别的事）不是失败：`finish --outcome interrupted` 之后运行 `foreman execution pause <execution_id> --reason "用户为什么叫停；已完成的部分"`。任务回到 PENDING，不计失败次数，已有文件保留。之后不要自己重新开始：用户同意继续时再 `begin`，上下文会带上这段说明，在已有改动上接着做。
- 任务时间长时，每做完一个能单独说明的阶段就向用户汇报一句，不要沉默到验收。验证要用模拟器、真机或其他启动慢的环境时，先告诉用户要做哪几步、预计多久，超出预计就停下来说明，不要反复重试。写法见 [managed-workflow.md](references/managed-workflow.md) 的“长时间任务和设备验证”。
- 执行期间启动、命令返回后还在运行的进程（dev server、模拟器、监听程序）要登记：`foreman execution track 001 --pid <PID> --label "dev server，端口 5173"`。`finish`、`retry`、`pause` 和 `integrate` 时还在运行的会在标准错误输出里列出：不再需要的关掉，要留着的告诉用户。
- 这里的验收是自审：实现和验收是同一个会话，记录里会标明 `self_review`。需要独立意见时，把 `git diff` 交给只读的审查角色（见第 3 节）或请用户过目。
- 直接执行不需要 `team`、`preflight` 和模型核对，`run` 会拒绝没有 `role` 的任务。想把其中一部分工作交给通用子 Agent 时，`plan-execution 001 --json` 给出按复杂度选的 droid 和 Task 参数，说明在 [configuration.md](references/configuration.md)；这种子 Agent 不固定模型，也没有隔离和模型核对，成果仍由当前会话负责并走上面的验收。

#### 2.3 派给角色（任务写了 role）

先读 [dispatch.md](references/dispatch.md)，再运行下面的命令。先检查，后派发：

```bash
foreman team check                                             # 角色的 droid 文件和模型服务
foreman preflight --dispatcher "custom:<用户选定的调度模型ID>"   # 隔离探针；没通过就不派发
foreman run 001 --dispatcher "custom:<用户选定的调度模型ID>"     # 每个任务一条，用后台方式并行，等实际完成
```

几条不能省的规矩：

- 模型和线路由用户选定。角色不可用、超时或权限被拒时报告用户，不换模型、不回退，也不用 `--skip-permissions-unsafe` 绕过。
- `run` 返回不代表代码可用。结果是 `returned`、`failed` 还是 `permission_rejected`，都按 2.4 先检查实际文件再验收。
- 子 Agent 在沙箱里不能联网、用不了 git、读不到装在用户目录下的工具。它跑不了某条验证命令不算失败，验收命令由主 Agent 自己运行。
- `run` 会自动核对子 Agent 实际使用的模型，核对没通过的不能验收。

#### 2.4 验收

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

逐项运行或观察验收条件，把结论和证据写进验收 JSON，再提交：

```bash
foreman acceptance 001 --template   # 生成 planning/acceptance-001.json 的框架
foreman execution accept <execution_id> --evidence-file planning/acceptance-001.json
# 不完整：记录已完成部分与续做范围，保留文件，再派给原角色
foreman execution retry <execution_id> --reason "已完成列表；还需修复刷新冲突"
```

```json
{
  "inspection": "检查了实际 diff 和新增文件；修改都在 files 内，原有用户改动已保留",
  "checks": [
    {"id": "login", "status": "passed", "evidence": "python3 -m pytest tests/test_auth.py -k valid_login：1 passed，退出码 0"},
    {"id": "wrong-password", "status": "passed", "evidence": "python3 -m pytest tests/test_auth.py -k wrong_password：1 passed，退出码 0"}
  ]
}
```

- `--template` 生成的框架照抄每个验收条件，`status`、`evidence` 和 `inspection` 留空，有范围外改动时多一个空的 `undeclared`。原样提交会被 `accept` 拒绝；文件已存在时不覆盖，除非加 `--force`。证据放在 `planning/` 下不算范围外改动。
- 框架开头的 `execution_id` 是这次执行的编号，不要改。证据要在 `execution finish` 之后取得：`accept` 拒绝为另一次执行写的证据，也拒绝写于这次执行登记结束之前的证据文件。返工之后运行 `foreman acceptance 001 --template --force` 重新生成，再逐项重新取证。
- 每个条件必须是 passed 并有具体证据，`inspection` 写实际文件审查的结论。不要根据子 Agent 的“完成”报告填 passed。浏览器和手工条件的证据写法见 [managed-workflow.md](references/managed-workflow.md)。
- 派发失败与独立验收通过可以同时成立；不会把派发结果改写成成功。
- 超过重试上限会 BLOCKED。受管事件自动同步 checkpoint，不靠收尾补记耗时。

BLOCKED 的受管任务要等用户处理（恢复模型、同意继续等），然后记录用户的决定来恢复，失败次数清零：

```bash
foreman execution unblock <execution_id> --reason "<用户的处理结果>"
```

不要对 BLOCKED 任务用 retry，也不要直接改状态；任务一旦 `begin` 过，`update`、`fail` 和 Web 页面都会拒绝修改它的状态。

### 3. 审查阶段

验收条件逐项通过只说明条件满足。运行 `execution accept` 之前，对照下面几点再看一遍实际改动：

- 代码质量：可读性、注释、错误处理
- 功能完整：是否满足任务描述
- 验收通过：所有验收命令成功
- 副作用：是否影响其他模块

有只读的审查角色时，把待审任务的 `git diff` 直接写进 Task 的 prompt 中派给它，不要假设只读角色能自己运行 git。审查角色只报告问题，不修改文件。

审查通过才运行 `execution accept`（见 2.4）。不通过就记录问题，任务回到 PENDING 交回原来的执行者修复：

```bash
foreman execution retry <execution_id> --reason "<实际文件检查结果及审查发现的问题>"
```

### 4. 集成确认

用户授权提交后，按任务分别提交（不推送，除非用户要求），然后确认集成：

```bash
foreman integrate 001 --commit <提交 SHA> --note "说明"
```

任务的提交里是它 `files` 的改动。`runtime_dependencies` 里还有没提交的改动时 `integrate` 会拒绝：属于这个任务的一并提交，属于别的任务的等那个任务提交之后再集成。`planning/` 和 `.task-management/` 不放进任务的提交，因为 `integrate` 之后它们还会变：项目决定提交它们时（见快速开始），在 `integrate` 之后另做只含这两个目录的提交，每个任务一次或每批一次都可以。

`integrate` 把任务标记为 DONE，依赖它的任务从此解锁；不要手工把状态改成 DONE 来绕过。该命令不提交、不合并，只核对你给出的提交。

项目不在 git 仓库里时没有提交可以核对，改用 `--no-git`，并在 `--note` 里写明成果保存在哪里：

```bash
foreman integrate 001 --no-git --note "成果在项目目录，已备份到 <位置>"
```

它照样检查逐项验收和验收后文件是否变化，记下已验收内容的摘要来代替提交；项目在 git 仓库里时会被拒绝。这类项目的 `inspect` 不检查范围外改动（`undeclared.checked` 为假），`delivery` 也用不了，这两项要自己核对。

`begin` 过的任务（两种执行方式都是）会检查逐项验收、验收后文件是否变化，以及提交是否包含 files 和 runtime_dependencies；派发的任务还要求实际模型核对通过。验收时会同时记下 runtime_dependencies 的声明和内容摘要，之后依赖内容或声明有变化都需要重新验收。不满足则拒绝集成。从未 `begin` 过的旧任务只记录提交，不做这些检查。

交付检查在要交付的任务全部集成之后做一次，不必每个任务都做：

```bash
foreman delivery --commit HEAD --paths <各任务 runtime_dependencies 的并集...>
checkout=$(mktemp -d) && git archive HEAD | tar -xf - -C "$checkout"   # 干净检出，放在项目目录之外
# 在 $checkout 里运行项目的启动和验收命令，用完删除这个目录
```

只检查工作区不能证明提交可运行。若用户要求保留依赖为未提交状态，明确记录交付阻塞，不能擅自提交这些依赖或声称可独立复现。

### 5. Checkpoint 管理

```bash
foreman checkpoint save --phase developing --data current_task=003 task_file=planning/tasks.md
foreman checkpoint check
foreman checkpoint clear
```

`execution` 命令和 `integrate` 会自动同步 checkpoint 里的任务进度，并保留规格路径等已有内容。用 `checkpoint save` 手工写的备注（例如 `next_action`）不会跟着更新：写入之后又有任务开始、结束、验收或集成时，`checkpoint check` 会在那一行标出“可能已过期”。这时进度以 `foreman show` 为准，备注还有用就用 `checkpoint save` 重写；`spec_file` 和 `task_file` 不会被标记。Checkpoint 只是游标：用任务的 sections 记录约束、关键决策和未完成项，详细材料放在规格文件里。新会话靠这些文件恢复，不能指望还记得上一个会话的对话。

### 6. 中断后恢复

新会话先运行快速开始的前两条，再列出还没有集成的执行记录：

```bash
foreman checkpoint check
foreman show
foreman execution recover
```

派发的任务：先确认旧进程是否仍在执行，不能因为记录是 running 就自动重试。确认已停止后登记 `execution finish <execution_id> --outcome interrupted`；实际结束时间未知时保持为空，不用当前时间伪造耗时。然后 inspect，核对本次模型，逐项验收或带检查结论 retry/block。

当前会话直接执行的任务（记录里 `details.mode` 为 `direct`）：记录仍是 running 说明上个会话做到一半。先 `execution inspect` 和 `git diff` 看已有改动，再接着做，做完 `finish --outcome completed`；不打算接着做就 `finish --outcome interrupted` 后 `retry` 写明续做范围，是用户叫停的改用 `pause`（见 2.2）。上次登记过进程时，`inspect` 的 `processes` 列出它们是否还在运行。`inspect` 的 `undeclared.paths` 这时已经列出上个会话留在 `files` 之外的文件：不要删除，验收时在证据的 `undeclared` 字段写明来源和去留。

不要 reset、checkout 或删除部分成果。用同一结果重复执行 `execution finish` 是安全的，会补上中断时没写完的任务板状态。`recover` 中 `current` 为 false 的记录已被后续执行替代，仅供查阅。`execution sync` 可修复 checkpoint，保留规格路径等已有上下文。逐步的判断依据见 [managed-workflow.md](references/managed-workflow.md) 的“中断恢复”。

### 7. 收尾

`batch` 没有可开始的任务不等于做完了。向用户汇报前逐项确认：

```bash
foreman show                # 每个任务都是 DONE；不是的要说明停在哪一步、为什么
foreman execution recover   # 没有 current 为 true 的记录，即没有做完却还没集成的执行
foreman doctor              # 没有“问题”；有任务在等用户配置角色时除外，见下
```

- 有任务在等用户为角色选模型时，`doctor` 会把“角色”列为问题并以 1 退出，`validate` 也会报“团队未就绪”。这是没完成的任务该有的状态：如实汇报，不为了让它消失而替用户选模型或删掉 `role`。
- 全部任务集成后，把项目自己的完整测试和构建再跑一遍。每个任务的验收只覆盖它自己的条件，任务之间的相互影响靠这一步发现。失败就开新任务修复，已经 DONE 的任务不能改写。
- 汇报写清四件事：完成了哪些任务和对应的提交；没完成或 BLOCKED 的任务及原因；实际运行过的验证命令和结果，没运行的如实说明；还需要用户做的事，例如推送、合并或处理阻塞。
- 全部任务集成后 checkpoint 的阶段会自动变成 completed，不需要手工清除；还有任务没完成时不要清除它。

## 其他命令

```bash
foreman status                                       # 各状态的任务数
foreman history                                      # 最近的执行记录；加 --task-id 001 只看一个任务
foreman show --mermaid > planning/dependencies.mmd   # 依赖图，箭头从被依赖的任务指向依赖它的任务
foreman --version                                    # 本技能的版本，也就是本文件开头的 version
foreman web                                          # Web 看板是否在运行和它的地址；web start 启动，web stop 关闭
```

- 当前会话直接执行的记录，`history` 的 droid 一栏是 `current-session`，没有模型。
- `update <任务ID> <状态>` 和 `fail <任务ID> --reason "<原因>"` 只用于从未 `begin` 过的旧任务，这类任务没有文件基线和验收记录。`begin` 过的任务用第 2 节的 `execution` 命令。
- Web 看板随技能安装在本技能目录的 `web/` 下，需要 Flask，只监听本机。`foreman web start` 在后台启动它并打印地址，默认端口上已有看板时把本项目登记进去；`foreman web stop` 关闭本项目启动的那一个。用户没有要求时不要自己启动。它只用来看：不启动子 Agent，也不能把任务标为完成。

## 退出码

- 0：成功。
- 1：命令被拒绝或出错，原因在标准错误输出以“错误:”开头的一行；`validate` 和 `doctor` 发现问题时也是 1。
- 2：检查没有通过，结果在标准输出里：`preflight`、`run`、`team check`、`team audit`、`execution audit`、`delivery`。命令行参数写错时也是 2，标准错误输出里有 usage。
- 130：被中断。

## 限制和注意事项

- 集成确认需要手动触发，不会自动检测 Git 提交
- 历史记录只保存元数据，不保存完整日志
- `add` 只检查编号、标题和状态；依赖和其余字段在规划审计和组队之后用 `validate` 检查
- 当前会话直接执行时，文件范围靠自觉：没有沙箱和写入守卫，范围外的改动在 `inspect` 时才报告
- `execution track` 只记你登记的进程，不会自己发现后台进程；证据的时间检查看的是证据文件的修改时间，不能防止虚报
- 目前只适配 Droid：派发、`preflight` 和模型核对依赖 `droid exec` 和 Droid 的会话记录。规划、任务板和当前会话直接执行不依赖 Droid。派发的其他限制见 [dispatch.md](references/dispatch.md)
- 只支持 macOS 和 Linux：文件锁和进程管理用的是 POSIX 接口。在 Windows 上命令会说明不支持后退出，要用的话在 WSL 里安装和运行
- 仓库里旧的 dual-ai-collab 脚本（`skill/scripts`）也读写 `planning/tasks.json`，但它每次写入都会按自己的格式改写整个任务板，文件锁也和本技能不兼容。同一个任务板不要两边混用
