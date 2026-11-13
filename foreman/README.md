# Foreman

Droid 原生任务管理技能 - 规划、拆分、执行和验收完整工作流。原名 `task-management`；原来的 `dual-ai-planning`（当前会话自己规划并实现）也已经并入，现在只有这一个技能。

每个任务按有没有 `role` 字段决定由谁来做：没写的由当前会话直接执行，写了的派给用户选定模型的固定角色。两种方式用同一套登记、验收和集成确认，可以在同一个任务板里混用。

## 特性

- 🎯 **需求访谈和复杂度判断**：根据需求规模调整规划深度
- 📋 **任务板管理**：`add` 写入、`show` 查看、状态追踪、依赖分析
- ✍️ **当前会话直接执行**：不派发子 Agent，同样记录文件基线、检查改动、逐项验收
- 🤖 **原生 Droid 集成**：受管进程通过 Task 派发固定模型子 Agent
- ⚙️ **灵活配置**：用户自定义 complexity→droid 映射
- 🧩 **固定模型团队**：按角色分配用户选定的模型，主 Agent 不能更改
- ⚡ **并行派发**：依赖已满足且文件不重叠的任务同时执行
- ✅ **独立验收**：结构化条件、实际文件审查、逐项证据与变更失效检查
- 📊 **执行历史**：追踪任务执行记录和性能数据
- 🔄 **Checkpoint 恢复**：长期项目的进度保存和恢复
- **完整模型选择**：推荐只排序，同名模型保留全部线路，支持搜索和直接输入完整 ID
- **中断恢复**：派发结果与验收分开保存，失败后保留部分文件，不盲目重跑
- **隔离预检**：临时原生沙箱、最小环境、固定假数据探针，失败不派发

## 快速开始

### 安装

```bash
# 安装到 Factory/Droid，并在 ~/.local/bin 里创建 foreman 命令的链接
python3 install.py --profile foreman --bin-dir ~/.local/bin

# 技能默认安装到 ~/.factory/skills/foreman
# 可通过 FACTORY_SKILLS 环境变量或 --target 自定义
```

需要 Python 3.9 以上和 git，只支持 macOS 和 Linux。在 Windows 上命令和安装脚本会说明不支持后退出；要用的话在 WSL 里安装和运行。

命令是技能目录下的 `bin/foreman`，下文都写作 `foreman`。

- `--bin-dir` 指定的目录要在 `PATH` 里。安装脚本只创建一个链接，不修改 shell 配置；那里已经有别的 `foreman` 程序时会拒绝覆盖。
- 不加 `--bin-dir` 时，用完整路径 `~/.factory/skills/foreman/bin/foreman` 运行。
- 在本仓库里开发时，直接运行 `foreman/bin/foreman`。

### 初始化项目

```bash
cd /path/to/your/project
foreman init                          # 创建 planning/、.task-management/ 和空任务板
foreman add --file planning/plan.json # 写入任务（一个任务、任务列表或 {"tasks": [...]}）
foreman validate                      # 检查字段、依赖和角色
foreman show                          # 任务板：编号、状态、由谁执行、等待的依赖
```

`init` 之外的命令也可以在项目的子目录里运行：它们会向上找到有任务板或配置的目录（不越过 git 仓库根目录）。

## 核心工作流

### 1. 规划阶段

根据需求复杂度选择合适的规划深度：

- **简单**（2-3 轮）：Bug 修复、小功能
- **中等**（4-6 轮）：新页面、API 模块
- **复杂**（6-10 轮）：认证、支付、架构变更

访谈由本技能自己完成：先读仓库，只问会改变设计的问题，每轮结论写回规格文件。生成规格文档和任务板后运行 `validate`，在派发前列出缺字段、依赖不存在或成环、角色未配置的任务。

### 2. 执行阶段

`batch --json` 列出下一批可以开始的任务，每个任务的 `mode` 是 `direct` 或 `dispatch`。

**当前会话直接执行（任务没写 `role`）**：

```bash
foreman execution begin 001     # 登记开始、记录文件基线，输出任务上下文
# 当前会话直接修改代码，只改任务 files 列出的路径
foreman execution finish 001 --outcome completed
```

`execution` 的子命令可以直接写任务 ID，表示该任务当前的执行记录；`show 001` 末尾会按任务状态列出下一步命令。

不需要组队、`preflight` 和调度模型。之后的验收和集成与派发的任务相同（见第 3、4 步），只是不做模型核对，验收记录会标明是自审。没做完时用 `finish --outcome failed` 加 `execution retry` 记下续做范围。

**派给固定模型的角色（任务写了 `role`）**：

```bash
foreman models --json --catalog
# 角色和调度器都使用用户选择的完整模型 ID
foreman team check
foreman preflight --dispatcher "custom:<调度模型ID>"
foreman batch --json
foreman run 001 --dispatcher "custom:<调度模型ID>"
```

`run` 自动创建唯一编号、记录文件基线、更新状态，通过嵌套 `droid exec` 派发（工具列表为 Task 加子 Agent 需要的读写工具，临时守卫只允许调度会话调用一次 Task），结束后记录进程结果、核对本次实际模型并同步 checkpoint。两种方式的任务都要声明 `files`、结构化 `acceptance` 和 `runtime_dependencies`；`run` 只接受写了 `role` 的任务。独立任务可按 batch 并行运行。嵌套进程以 `--auto medium` 在沙箱内运行，子 Agent 可以跑测试和构建，但不能联网、提交或写任务板；派发结果以子 Agent 自己的结束方式为准。

### 3. 验收和审查

```bash
foreman execution inspect 001
foreman acceptance 001 --template   # 生成 planning/acceptance-001.json，结论和证据待填写
# 主 Agent 检查实际文件、运行验收并把观察证据填进文件后
foreman execution accept 001 --evidence-file planning/acceptance-001.json
# 不完整时保留文件，记录续做范围再派发
foreman execution retry 001 --reason "文件检查结论与还需完成的事项"
```

`inspect` 的 `notices` 会指出声明的文件完全没有变化，或派发期间有声明范围外的改动；后者必须在验收证据的 `undeclared` 字段说明。权限拒绝不代表没有写入文件，派发返回也不代表验收通过。`accept` 逐项检查证据和本次模型审计，保存独立时间戳；不会把失败派发改写成成功。证据格式、恢复和隔离边界见 [运行与恢复](references/managed-workflow.md)。

### 4. 集成确认

用户授权提交后，检查提交包含全部运行依赖，并在干净检出中启动和验收：

```bash
foreman delivery --commit <SHA> --paths <运行依赖路径...>
foreman integrate 001 --commit <SHA>
```

受管任务缺少验收、模型审计、运行依赖，或验收后文件变化时不能集成。依赖被要求保留未提交时明确报告限制，不擅自提交。

## 配置系统

### 固定模型团队（按角色分配模型）

主 Agent 按项目需求提出尽量少的角色，用户从自己配置的模型（`~/.factory/settings.json` 里的 BYOK 模型）中为每个角色选一个。每个角色对应一个项目级 droid，模型固定在 droid 文件里，主 Agent 不能更改。

```bash
foreman models                       # 列出可选模型（不含密钥）
foreman models --search "claude"      # 搜索，仍显示全量目录总数
foreman models --recommend "custom:<模型ID>"  # 只排序，不隐藏其他线路
foreman team set backend \
  --model "custom:<模型ID>" \
  --description "接口、数据库和业务逻辑"   # 生成 .factory/droids/tm-backend.md
foreman team show                    # 查看角色和模型
foreman team check                   # 派发前检查模型服务能否连通
foreman team audit                   # 核对子 Agent 实际用的模型
foreman team remove backend          # 删除角色
```

任务写上 `role` 和 `files`：

```json
{"id": "002", "title": "用户列表接口", "role": "backend", "files": ["api/users.py"]}
```

没写 `role` 的任务由当前会话直接执行，`run` 会拒绝它。推荐列表不能限制用户选择，未配置 ID 不自动替换。

### 并行派发

```bash
foreman batch --json      # 下一批可同时开始的任务，含 Task 调用参数 task_args
foreman execution retry <execution_id> --reason "文件检查与续做范围"
foreman integrate 002 --commit <SHA>     # 确认提交已集成，标记 DONE 并解锁后续任务
```

一批任务要满足：依赖已集成、角色已配置、修改的文件互不重叠，也不和未集成的任务重叠。默认每批最多 2 个，可用 `config set parallel.max_parallel=3` 调整。

注意：
- run 启动新进程加载角色；直接 Task 需当前会话已识别该角色。
- 无效模型可能静默回退，所以受管执行按唯一编号核对本次实际模型。空记录或多条记录不能当作成功。

### Complexity → Droid 映射

只在当前会话想把直接执行任务的一部分交给通用子 Agent 时使用：`plan-execution 001 --json` 按任务复杂度给出 droid 和 Task 参数。这种子 Agent 不固定模型，也没有隔离和模型核对。

配置文件：`.task-management/config.json`

```json
{
  "execution": {
    "light": "worker",
    "medium": "code-architect",
    "heavy": "worker"
  },
  "complexity_rules": {
    "by_type": {
      "docs": "light",
      "test": "light",
      "bugfix": "medium",
      "feature": "medium",
      "refactor": "heavy",
      "architecture": "heavy"
    }
  }
}
```

### 使用 CLI 配置

```bash
# 查看配置
foreman config show

# 设置 droid 映射
foreman config set execution.medium=code-architect

# 查看执行计划
foreman plan-execution 001
foreman plan-execution 001 --json
```

## CLI 命令

```bash
# 初始化
foreman init

# 自检和版本
foreman doctor               # 只读：环境、任务板、配置、checkpoint、执行记录；有问题时退出码 1
foreman --version

# 写入和查看任务
foreman add --file planning/plan.json           # 加 --replace 改写待开始的同号任务
foreman show                 # 任务板
foreman show 001             # 单个任务的完整上下文、当前状态和下一步命令
foreman show --mermaid       # 依赖图

# 下一个可以开始的任务（batch 的第一项）
foreman select

# 任务统计
foreman status

# 规划检查（缺字段、依赖不存在或成环、角色未配置；有问题时退出码 1）
foreman validate

# 规划执行
foreman plan-execution 001

# 更新状态（只用于从未 begin 过的旧任务）
foreman update 001 IN_PROGRESS

# 当前会话直接执行（任务没写 role）
foreman execution begin 001
foreman execution finish 001 --outcome completed   # 任务 ID 或 execution_id 都可以

# Checkpoint 管理
foreman checkpoint check
foreman checkpoint save --phase developing --data current_task=001
foreman checkpoint clear

# 查看历史
foreman history
foreman history --task-id 001

# 列出验收条件；--template 生成验收证据框架 planning/acceptance-001.json
foreman acceptance 001
foreman acceptance 001 --template

# 固定模型团队和并行派发
foreman models
foreman team show            # 另有 set、remove、check、audit
foreman batch --json
foreman fail 001 --reason "..."
foreman integrate 001 --commit <SHA>

# 受管执行与恢复
foreman preflight --dispatcher "custom:<用户选定ID>"
foreman run 001 --dispatcher "custom:<用户选定ID>"
foreman execution recover
foreman execution inspect <execution_id>
foreman execution finish <execution_id> --outcome interrupted
foreman execution audit <execution_id>
foreman execution accept <execution_id> --evidence-file planning/acceptance-001.json
foreman execution retry <execution_id> --reason "保留部分成果，继续剩余工作"
foreman execution block <execution_id> --reason "实际模型不符，等用户处理"
foreman execution unblock <execution_id> --reason "用户已处理阻塞原因"
foreman execution sync
foreman delivery --commit HEAD --paths <运行依赖路径...>
```

## 测试

在仓库根目录运行：

```bash
python3 -m pytest tests/test_foreman*.py tests/test_install_pytest.py -q
```

## 迁移指南

### 任务板文件

任务数据在 `planning/tasks.json`，`planning/tasks.md` 是每次写入时生成的只读视图。

早期版本把数据存在 `planning/codex-tasks.json`。`planning/tasks.json` 不存在时会自动读取旧文件，下一次写入（包括运行 `init`）会保存到 `planning/tasks.json`。旧的 `codex-tasks.json` 和 `codex-tasks.md` 不会被删除，确认新文件正确后可以自己删掉。

### 从 task-management 改名

技能从 `task-management` 改名为 `foreman`，只换了技能名和安装目录。项目里的 `.task-management/` 目录、角色 droid 的 `tm-` 前缀和文件里的 `managed-by: task-management` 标记、执行标记 `[tm:编号]` 都保持原样，已有任务板、角色和执行记录可以直接继续用。

```bash
python3 install.py --profile foreman
rm -rf ~/.factory/skills/task-management   # 删除改名前的安装，避免出现两个相同的技能
```

### 从 dual-ai-planning 迁移

`dual-ai-planning` 已并入本技能。数据文件同样是 `planning/tasks.json`，已有任务板可以直接读取；视图从 `planning/codex-tasks.md` 换成 `planning/tasks.md`。

| 原来的命令（`planning.py ...`） | 现在（`foreman ...`） |
|---|---|
| `select`、`board show` | `select`、`show` |
| `board context 001` | `show 001` |
| `templates create ... --add` | 把任务写成 JSON，`add --file` |
| `update 001 IN_PROGRESS` | `execution begin 001` |
| `verify extract 001` | `acceptance 001` |
| `verify run 001` | 当前会话读过命令后自己运行，结果写进验收 JSON |
| `update 001 AWAITING_REVIEW`、`board review` | `execution finish <id> --outcome completed`、`execution accept <id>` |
| `board integrate 001 --target --commit` | `integrate 001 --commit` |
| `checkpoint-write`、`checkpoint-check` | `checkpoint save`、`checkpoint check` |
| `visualize` | `show --mermaid` |
| `summary`、`analyze` | `status`、`show`（不再生成分析报告） |

不再提供的：任务模板、自动执行验收命令（`verify run`）、进度和分析报告。旧的 checkpoint 不会被读取，用 `checkpoint save` 重新保存。

旧任务没有 `files` 和结构化 `acceptance`。用 `add --replace` 补齐后就能走 `execution begin`；不补也能继续用 `update` 和 `integrate`，但没有文件基线和验收记录。

同一个任务板不要再用旧脚本写入：旧脚本每次写入都会按自己的格式改写整个任务板，文件锁也和本技能不兼容。

### 从 dual-ai-collab 迁移

1. 安装新技能：
```bash
python3 install.py --profile foreman
```

2. 任务板：
- dual-ai-collab 的数据文件也是 `planning/tasks.json`，可以直接读取。
- 旧字段会自动标准化（`task_num` → `id`，列表形式的依赖转成 `#001, #002`）。
- 旧的 `planning/codex-tasks.md` 不再更新，新的视图是 `planning/tasks.md`。
- 依赖只认 `DONE` 且带集成记录的任务。旧任务的审查和集成记录不会重新校验，有疑问的任务用 `integrate` 重新确认。

3. 配置：
- `.dual-ai-collab/model-routing.json` 不再读取，可以保留也可以删除。
- 任务里的 `execution_level` 会自动换算：quick → light，normal → medium，heavy → heavy。
- 需要固定模型时，用 `team set` 为每个角色指定模型，并在任务里写 `role`。

4. 工作流：
- 不再使用 `run start/stop` 命令，也不再调度外部 CLI 进程（codex/claude 命令）、按适配器路由和自动换模型。
- 写了 `role` 的任务用受管 run，通过嵌套进程调用 Task；没写的由当前会话用 `execution begin` 直接执行。
- 验收仍然由主 Agent 运行任务里的验收命令。

## 可选工具

### Web UI
仓库根目录的 `web_server.py` 用于可视化监控（不随技能安装，需要在仓库里运行）：

```bash
python3 web_server.py 5001
open http://localhost:5001
```

默认显示的是该仓库目录；要看自己的项目，在页面顶部“登记项目”。页面内容、接口和故障排查见仓库的 `docs/web-ui.md`。

## 最佳实践

1. **复杂度与需求匹配**：简单需求不要过度规划
2. **任务拆分 1-3 小时**：便于验收和回滚
3. **验收标准可执行**：写具体命令而非描述
4. **配置 droid 映射**：根据项目特点选择合适的 droid
5. **及时更新状态**：保持任务板与实际进度同步
6. **完整集成确认**：不要跳过验证环节

## 故障排查

### 不知道哪里出了问题
```bash
foreman doctor
```
只读自检，逐项列出环境和项目数据的状态；“问题”一项会让命令用不了，退出码为 1。

### 任务板不存在
```bash
foreman init
```

### 在子目录里运行时找不到任务板
命令从当前目录向上找 `planning/tasks.json` 或 `.task-management/config.json`，到 git 仓库根目录为止。没找到时标准错误输出会提示，按当前目录处理。当前目录在另一个 git 仓库里（例如子模块）时，`cd` 到项目根目录再运行。

### 角色的 droid 不存在
角色的 droid 在项目的 `.factory/droids/tm-<角色>.md`，由 `team set` 生成：
```bash
foreman team show     # 已配置的角色和模型
foreman team check    # 检查 droid 文件和模型服务
```
`plan-execution` 用到的通用 droid（如 `worker`）由 Droid 自带，或放在 `~/.factory/droids/`。

### 配置丢失
重新生成默认配置：
```bash
foreman init
```

### 提示文件读不出来或无法使用
任务板、配置和执行记录损坏时，命令报出文件和位置后停下，不改动文件；修好 JSON 或从 git、备份恢复。配置损坏时 `init` 不会覆盖它，因为里面可能有角色。checkpoint 损坏时运行 `foreman execution sync`，原文件会另存为 `checkpoint.json.corrupted`。

### 依赖循环
`add` 写入后只列出这批任务自己的问题，不检查整个任务板。运行 `foreman validate` 列出依赖环、不存在的依赖和缺失的字段；batch 无可执行任务时检查 skipped，不把依赖阻塞当作全部完成。

## 架构

```
foreman/
├── SKILL.md              # 技能主文件（完整工作流）
├── README.md            # 本文件
├── lib/                 # 核心库
│   ├── __init__.py
│   ├── store.py         # 任务存储
│   ├── board.py         # 任务板管理
│   ├── config.py        # 配置系统
│   ├── executor.py      # 执行规划
│   ├── history.py       # 执行历史
│   ├── workflow.py      # 文件基线、恢复、验收、交付检查
│   ├── plan.py          # 规划检查（validate）
│   ├── doctor.py        # 只读自检（doctor）和版本
│   ├── team.py          # 固定模型角色与模型目录
│   ├── runner.py        # 嵌套 Task 派发与自动记录
│   ├── safety.py        # 单次运行的原生沙箱配置
│   ├── probe.py         # 无敏感数据的隔离探针
│   └── checkpoint.py    # Checkpoint 管理
├── bin/
│   └── foreman          # 命令入口，运行 tools/cli.py
├── tools/
│   ├── cli.py           # CLI 实现
│   └── dispatch_guard.py # 工具 schema 和文件路径检查
└── references/
    └── managed-workflow.md # 证据格式、恢复步骤与保护边界
```

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License
