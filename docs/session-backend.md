# 可恢复的 Codex 会话后端

当前新增 `app-server` 后端，保留 `direct` 与 `adapter` 的调用方式。默认后端仍是 `direct`，可以通过基础配置或命令行选择。Claude Agent SDK 尚未接入。

## 使用

从保存任务板的项目目录运行以下命令。`<cli>` 指仓库或已安装 Skill 的 `scripts/cli.py` 的绝对路径。

```bash
python3 <cli> run capabilities
python3 <cli> run start 001 "实现任务" --backend app-server --isolate
python3 <cli> run status 001
python3 <cli> run events 001 --after 0 --limit 100
```

`--isolate` 从代码仓库当前 HEAD 创建独立、detached worktree。要求 `--workdir` 指向 Git 根目录且工作区干净；运行目录 `.dual-ai-collab/` 和生成的任务板通常应加入 `.gitignore`。未提交修改不会被复制，也不会自动 stash、提交、合并或删除。默认代码目录是当前目录；可以显式传入 `--workdir /path/to/code`。

不使用 `--isolate` 时在给定工作目录执行，适用于非 Git 项目。worktree 用于分开文件修改，实际访问权限仍由 Codex 沙箱控制。

```bash
# 执行结束后，沿用原 thread_id 发起下一轮
python3 <cli> run continue 001 "补充处理空输入，保留现有接口"

# 执行过程中追加指导
python3 <cli> run steer 001 "先运行失败的测试，缩小问题范围"

# 请求中断当前 turn
python3 <cli> run stop 001
```

`steer` / `stop` 返回 `queued` 只代表本地请求已入队。请查看事件中的 `control/result`，区分服务器确认、拒绝或无法确认；任务终态通过 `status` 确认。请求绑定当前 run / turn，不会自动重放到后续任务。直接终止 worker 时会尽量请求中断并关闭服务器。

每轮运行拥有独立 `run_id`。`events` 返回 `next_after` 用于分页，游标仅在同一个 `run_id` 内有效；新一轮需从 0 开始。事件包含服务器通知、控制请求结果和 worker 错误。

## 验收与同会话修复

在原项目的 `planning/tasks.json` / Markdown 任务板中定义可执行验收命令，命令使用代码工作目录作为当前目录。模板里的自然语言验收条目不等于可执行检查。

```bash
# 等 status 为 success，再执行验收
python3 <cli> run complete 001

# 验收失败时自动沿用原线程修复一次
python3 <cli> run complete 001 --repair
```

行为约定：

- 进程成功、结构化回复为 DONE，都不会直接更新任务板。
- `complete` 执行全部验收命令，通过才更新任务板为 AWAITING_REVIEW；报告保存命令、退出码、输出尾部、耗时和所属 run / thread / turn。
- 没有验收命令、执行超时、会话失败或被阻塞，都不能完成任务。
- `--repair` 将失败报告作为诊断材料发到原会话，启动一个修复轮次；原验收失败仍返回退出码 1。它不循环重试，也不会在修复结束后自动重新验收，请再次调用 `complete`。
- 验收期间若任务定义被修改，拒绝更新任务阶段。代码仍需审查；通过测试不意味着可以自动合并 worktree。
- AWAITING_REVIEW 表示执行目录验收通过；隔离 worktree 尚未合并。审查和原仓库集成确认后才成为 DONE 并解锁依赖，详见 [任务面板](task-board.md)。

## 状态与落盘

项目目录和代码工作目录分离。所有运行记录保存在发起命令的项目目录下：

```text
.dual-ai-collab/
  runs/task-001.json                 # 最新一轮状态
  sessions/task-001-<uuid>/
    state.json                      # 本轮状态，包含 thread_id / turn_id / 工作目录
    prompt.md
    events.jsonl
    result.json
    server.log
    worker.log
    verification-<uuid>.json
    commands/                       # 绑定本轮的控制请求与响应
  worktrees/task-001-<uuid>/         # 显式 --isolate 才创建
  history/                          # 执行历史
```

同一任务的编号别名（如 1 / 001）会统一，同一任务不能重复启动。已有线程使用 `continue`；新任务使用新编号。线程恢复失败会报错，绝不悄悄新建一个丢失上下文的线程。

Worker 意外死亡后，查询状态会将未确认完成的运行标记为 `interrupted`。已有 thread_id 可显式恢复；系统不会因断线自动重跑。每轮启动一个 app-server 进程，完成后关闭，下一轮从持久线程恢复；当前版本不运行常驻服务。

权限采用所选 Codex 沙箱和 `approvalPolicy=never`。额外权限或人工输入请求会被拒绝/记录，运行标记为 blocked；当前不提供交互式审批界面，不会自动批准请求。

## 配置

`.dual-ai-collab/config.json` 示例：

```json
{
  "default_backend": "app-server",
  "default_sandbox": "workspace-write",
  "app_server_request_timeout": 30,
  "app_server_turn_timeout": 600,
  "verification_timeout": 120
}
```

`CODEX_BIN` 可指定可执行文件。`--timeout` 覆盖单轮执行超时。后续 `continue` 沿用已有线程的执行目录、模型、沙箱和超时参数，不在恢复时隐式改变权限。

协议依据 [Codex App Server 官方文档](https://learn.chatgpt.com/docs/app-server) 和本机 `codex app-server generate-json-schema` 导出的稳定接口。验证版本为 **codex-cli 0.160.1**；该 CLI 仍将 app-server 标注为 experimental，部署时建议固定已验证版本，升级后重新做协议测试。

## 本轮验证

自动化回归：81 项 Python 测试、97 项 Shell 检查通过，编译与 diff 检查通过。

- 自动化协议对端覆盖：消息交错、线程恢复、追加指导、中断、连接断开、超时、权限请求、重复启动、隔离目录与验收修复。
- 真实 Codex 0.160.1 在临时干净 Git 仓库中创建独立 worktree。
- 首轮写入 `answer.txt=draft`；验收要求 `ready`，因此失败。
- `complete --repair` 使用相同 thread_id、不同 turn_id 修复；第二次验收通过；当前任务板进入 AWAITING_REVIEW。
- 最终内容为 `ready`，验收脚本未改变，原仓库未生成 `answer.txt`，未合并任何分支。

这验证了会话后端的最小真实链路，不是大型项目质量或性能基准。Windows 的新增会话后端尚未做真实环境验证。
