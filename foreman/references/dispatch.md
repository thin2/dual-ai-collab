# 派给固定模型的角色

任务写了 `role` 时读这份文件。它按操作顺序写：组建团队（每个项目一次）、派发前检查、派发、核对实际模型，然后回到 SKILL.md 的 2.4 验收。没写 `role` 的任务不需要这里的任何一步。

## 目录

1. 组建团队
2. 派发前检查
3. 派发
4. 核对实际模型
5. 在当前会话里手工派发
6. 隔离边界
7. 限制

## 组建团队

每个项目只需做一次，之后只在用户要求换模型时重做。

1. **主 Agent 提出角色，越少越好。** 按本项目的需求决定需要哪些角色，通常 1 到 3 个。每个角色写一句职责。不要套用固定的四人模板；两个角色总在改同一批文件时，合并成一个。
2. **列出用户自己配置的模型（BYOK）：**
   ```bash
   foreman models
   ```
   输出每个模型的 ID、名称和服务地址，不含密钥。
3. **由用户选模型和线路。** 每个角色和调度器都由用户选模型。先展示全部目录的 ID、名称、provider 和端点，推荐只调整排序，不隐藏其他模型，不合并同名模型（同名不同代理是不同的线路）。用 AskUser 提供“推荐模型”“查看全部”“直接输入模型 ID”入口；AskUser 的选项上限不能成为隐藏模型的理由，选项数量有限时先展示完整表格，再让用户输入 ID，或分组翻页。用户已经给出完整 ID 时直接校验，不重复询问。模糊名称对应多条线路时才澄清，不能替用户选线路。
   ```bash
   foreman models --json --catalog   # 返回总数、搜索命中数和全部匹配项
   foreman models --search "claude"  # 搜索仍显示目录总数，清除搜索恢复全部
   foreman models --recommend "custom:<用户可选的模型ID>"
   ```
   没有想用的模型时允许直接输入 ID。ID 未配置则说明缺失，请用户配置或明确选择已有模型，不擅自创建路由或回退，不代填凭据。调度模型也由用户指定；记录完整 ID，不能因推荐、超时或权限错误而改变。
4. **生成角色：**
   ```bash
   foreman team set backend --model "custom:<模型ID>" --description "接口、数据库和业务逻辑"
   foreman team set reviewer --model "custom:<另一个模型ID>" --description "独立审查改动" --read-only
   ```
   每个角色会生成 `.factory/droids/tm-<角色>.md`，`model` 写的是 settings 里的模型 ID，能精确指定线路。同时写入 `.task-management/config.json` 的 `roles`。
5. **新角色需要新会话加载。** 受管 `run` 每次启动新的嵌套 Droid 会话，无需让用户重开主会话。直接使用当前会话 Task 时，先确认工具目录包含该角色；缺失则保存 checkpoint，重开会话，不换成其他角色。

换模型：仅在用户指定新模型后重新运行 `team set`。新派发会加载新配置，旧执行仍按当时固定的模型审计。`team show` 列出已配置的角色和模型，`team remove <角色>` 删除角色和它的 droid 文件。

任务通过 `role` 字段指定角色：

```json
{"id": "002", "title": "用户列表接口", "role": "backend", "files": ["api/users.py", "tests/test_users.py"]}
```

组队后再运行一次 `foreman validate`，“团队未就绪”一类的问题应当消失，全部通过才进入执行阶段。

## 派发前检查

```bash
foreman team check
foreman preflight --dispatcher "custom:<用户选定的调度模型ID>"
```

`team check` 仅检查配置和 TCP，不证明鉴权或实际模型调用成功。角色不可用时不要派发这个角色，不换模型。报告问题，确实需要用户处理服务或选新模型时用 AskUser。

`preflight` 使用用户选定调度模型和一次固定的无敏感数据 Execute 调用，检查当前 CLI 参数、hook 生效、普通文件可读以及受保护假文件不能读写。探针用和真实派发相同的权限级别运行，所以它同时证明这个级别的命令不会被拒绝。技能升级、Droid 升级或保护策略变化后，旧的通过记录失效，`run` 会要求重新运行 `preflight`。失败退出 2，不运行真实任务，也不关闭沙箱重试。不读取真实凭据作探针，不写用户级设置。它验证了什么、没验证什么，见“隔离边界”。

实际子 Agent 必须先按当前工具 schema 做无副作用检查。Execute 必须有 command、riskLevel、summary；工作目录写进命令的 `cd <绝对路径>`，不能传不存在的 cwd。不要把工具参数错误、权限拒绝、模型不可用混为一谈。

## 派发

对 `batch` 返回的、`mode` 为 `dispatch` 的任务并行运行，每个任务一条命令：

```bash
foreman run 001 --dispatcher "custom:<用户选定的调度模型ID>"
foreman run 002 --dispatcher "custom:<同一调度模型ID>"
```

使用工具支持的后台执行方式，等待实际完成事件。`run` 自动创建唯一 execution_id、保存已有文件摘要、标记 IN_PROGRESS，通过嵌套 `droid exec` 派发，随后登记进程结束时间、核对本次子 Agent 模型、同步 checkpoint。每次重试或纠正必须创建新记录。不会自动提交、重试或改模型。

写任务和派发前要知道子 Agent 在沙箱里做不了什么（依据见“隔离边界”）：

- 不能联网。额外依赖由主 Agent 事先安装或提供。
- 用不了 git（`.git` 不可读），所以不能提交；也不能写任务板和项目外的目录。
- 读不到装在用户目录下的工具，例如用 `pip install --user` 装的 pytest。它因此跑不了某条验证命令时会如实报告，这不算失败；验收命令由主 Agent 在验收时自己运行。想让子 Agent 自己跑测试，由主 Agent 事先把工具装进项目内（例如 `.venv`），并在任务描述里写明用它运行。
- 它把命令标为 high 风险时，整次派发会被终止。
- 调度进程只能调用一次 Task。它多调用工具会被拒绝，本次派发记为失败，成果仍保留待检查。

不要用 `--skip-permissions-unsafe` 绕过失败。

读结果：`run` 的 `dispatch_outcome` 以子 Agent 自己的会话记录为准，`transport.worker_outcome` 是它最后一轮的结束方式。调度进程正常返回、但子 Agent 被权限拒绝中止时，结果是 `permission_rejected` 而不是 `returned`；子 Agent 最后一轮没有正常结束的其他情况记为 `failed`。会话记录里没有结束方式时不改判。

派发返回不代表代码可用。无论结果是成功、失败还是权限拒绝，都回到 SKILL.md 的 2.4，先检查实际文件再验收。

## 核对实际模型

`run` 自动按唯一编号核对本次派发；手工派发时运行：

```bash
foreman execution audit <execution_id>
```

必须找到唯一对应的子 Agent 记录且实际模型与派发时固定的 ID 一致。空结果、重复派发、缺失模型或不一致都不能当作通过。`team audit` 仍可浏览近期记录，但不能用旧记录替代本次核对。模型不符时保留文件，检查后 `execution block <execution_id> --reason "实际模型不符及文件检查结果"`，报告用户。

## 在当前会话里手工派发

写了 `role` 的任务要在当前会话里直接用 Task 派发时，用 `execution begin <任务ID>` 获取带唯一标记的 task_args；返回后立即 `execution finish <execution_id> --outcome ...`。这是手工桥接，不提供自动结束记录或隔离保证，必须使用已有受验证的受限会话。不要使用过期的 `await`、`run_in_background` 参数；以当前 Task schema 为准。

## 隔离边界

`preflight --dispatcher <用户选定 ID>` 先检查 CLI 支持必要参数，再用一次只允许固定 Execute 命令的探针验证原生沙箱。只读写临时假文件。普通文件应可读，受保护假文件应不能读写，hook 必须实际运行。失败不产生通过凭据，`run` 拒绝启动。Droid 可执行文件或保护策略变化后必须重测。

每次 run 使用新的进程级临时配置：

- 开启原生 per-command 沙箱。shell 与子进程由操作系统限制，文件工具由 Droid 的路径策略检查；Task 子 Agent 按 Droid 的契约继承沙箱。
- 隐藏用户 Factory、SSH、云凭据等常见目录，以及项目内发现的 `.env*`、密钥文件、敏感目录和符号链接。最小环境不继承 API key/token。以 `.example`、`.sample`、`.template`、`.dist` 结尾的 `.env` 模板不算敏感文件，可以读取并声明为运行依赖；不要把真实密钥写进模板。
- 工具网络默认不开放，Factory 自身域名的例外遵循 Droid 实现。主进程仍需读取模型配置完成鉴权，这部分不交给模型工具。
- 子 Agent 继承调度进程的工具列表，只给 Task 时子 Agent 没有任何工具。因此工具列表是 Task 加子 Agent 需要的读写工具（只读角色不含写入和 Execute），由临时 hook 按会话区分：第一个按给定参数调用 Task 的会话是调度会话，它只能调用这一次 Task；其他会话才能使用读写工具。运行结束后还会核对 hook 记录的调度会话与 Droid 报告的是否一致，不一致则派发记为失败。
- 临时 hook 限制 Task 参数、Execute schema 和文件操作路径。补丁仅解析目标头，不扫描正文；文档提到 settings.json 不会被误拦截。
- 嵌套进程以 `--auto medium` 运行，子 Agent 才能运行测试和构建这类它自己标为 medium 风险的命令；在 low 级别下这类命令会让整次派发被直接终止，标为 high 的命令在 medium 下仍会终止整次派发。这个级别不是隔离手段，隔离靠沙箱：实测在该级别下联网、`git commit`、写任务板、写用户目录都被沙箱拒绝，项目内的普通文件可写。`preflight` 的探针用同一级别运行，通过记录里记着级别，级别不同的旧记录无效。
- 沙箱内 `.git` 不可读写，用户目录除 `.local`、`.cache` 外不可读。子 Agent 因此不能使用 git，也读不到装在用户目录下的工具（例如 `~/Library/Python` 下的 pytest）；装在项目内的工具（例如 `.venv`）可以正常使用。
- 不修改用户级设置，不安装永久项目 hook，不开启 unsafe 权限。临时目录正常结束会清理。

这不是对恶意代码的完全隔离：探针只验证当前 Execute 读写与 hook，不证明所有工具和内核路径无漏洞；沙箱默认可读系统文件，无法自动识别所有自定义命名的秘密，依赖目录不做递归秘密发现。shell 在项目内仍可能修改任务范围外的文件：这类改动不会被拦截（实测：文件工具写范围外的文件被守卫拒绝，同一文件用 shell 写入成功），但派发结束时会按 `git status` 和文件内容的前后差异记入 `inspect` 的 `undeclared`，验收时必须说明；被 git 忽略的文件不在这项检查内。每次 run 的临时守卫目录对子 Agent 可读（hook 在沙箱内运行，必须能读到它），其中只有本次任务参数和允许写入的路径，没有凭据；可写的调度会话记录被改动时，会因与 Droid 报告的会话不一致而把派发记为失败。真正不可信的代码需要无宿主凭据的独立容器或 VM，不能把本探针当作安全认证。通过收据是本地运行记录，不是对恶意篡改的防护。

CLI 使用已有 Factory 登录状态；如果环境仅靠被过滤的 FACTORY_API_KEY 认证，探针会失败，不能为通过检查而重新向工具注入密钥。

## 限制

- Task 工具不能直接指定模型；固定模型来自 droid 文件的 `model`，这个值只有用户通过 `team set` 才能改
- droid 的模型无效时，Droid 会静默改用主会话模型；`team check` 只能在派发前发现部分问题，派发后要按上面的“核对实际模型”核对
- `team audit` 和模型核对依赖 Droid 本地会话记录的格式（Droid 1.6 实测），格式变化后可能返回空结果
- 并行的子 Agent 共用同一个工作目录，安全依赖任务的 `files` 写得准确
