# Web UI 使用指南

仓库根目录的 `web_server.py` 是 foreman 的本地监控页面：查看任务板、进度、团队配置和执行记录，也能改少数状态。它不启动子 Agent，不调用模型。它随技能一起安装，用 `foreman web start` 启动。旧版 dual-ai-collab（`skill/`）的数据它不读取。

## 启动

```bash
python3 -m pip install --user Flask   # 只有 Web UI 需要 Flask，技能本身只用标准库
cd /path/to/project
foreman web start                     # 后台启动，打印地址；日志在 .task-management/web.log
foreman web                           # 是否在运行和地址；加 --json 输出结构化结果
foreman web stop                      # 关闭本项目启动的看板
```

`foreman web start` 做的事：

- 没有看板在运行时，从 5001 起找一个空闲端口，在后台启动，默认项目就是当前项目。`--port` 指定端口；环境变量 `FOREMAN_WEB_PORT` 改变默认端口。
- 默认端口上已经有看板时，不再起第二个，把当前项目登记进去并打印它的地址。
- 当前项目已经在某个看板里时，只打印地址。

`foreman web stop` 只关闭本项目启动的看板；别的项目启动的要在那个项目里关闭。`foreman doctor` 和第一次 `checkpoint save --phase developing` 也会报告看板的地址。

看板的文件随技能安装在技能目录的 `web/` 下。在本仓库里开发时也可以直接运行，前台启动：

```bash
python3 web_server.py 5001 --project /path/to/project   # 端口默认 5001；不加 --project 时默认项目是本仓库
```

服务只监听 `127.0.0.1`，其他机器访问不到。修改代码或升级后要重启服务再刷新页面。

和 foreman 一样只支持 macOS 和 Linux；在 Windows 上要在 WSL 里运行。

## 项目

页面顶部选择当前项目。

- **默认项目**是启动看板的那个项目：`foreman web start` 所在的项目，或 `--project` 指定的目录；直接运行 `web_server.py` 又不加 `--project` 时是它所在的目录，也就是本仓库。
- **其他项目**在自己的目录里运行 `foreman web start` 就会登记进来，也可以在页面上用“登记项目”添加：填项目名称和项目根目录的绝对路径（`init` 时所在的目录）。登记不会创建、移动或初始化任何文件；没有任务板的目录显示为空列表。同一个目录不能登记两次。
- 登记记录保存在默认项目的 `.task-management/projects.json`。要换位置，启动前设置环境变量 `TASK_MANAGEMENT_PROJECTS_FILE=/absolute/path/projects.json`。
- 旧版用过的 `.dual-ai-collab/projects.json` 和 `DUAL_AI_PROJECTS_FILE` 不再读取，以前登记的项目要重新登记。
- 登记过的目录被删除或移走后，选择器里显示“路径不可用”，这个项目的接口返回 409。

每个项目的数据都从它自己的目录读取：

| 内容 | 文件 |
| --- | --- |
| 任务板 | `planning/tasks.json`（没有时读旧的 `planning/codex-tasks.json`） |
| 角色和并发配置 | `.task-management/config.json`，角色的 droid 在 `.factory/droids/tm-<角色>.md` |
| 执行记录 | `.task-management/history/*.json` |
| 当前阶段 | `.task-management/checkpoint.json` |
| 规划文档 | `planning/specs/*.md`（不含子目录和符号链接） |

打开页面和其他 GET 请求不会在项目里创建文件。

## 页面

每个页面的地址都有两种写法：默认项目用 `/overview`，其他项目用 `/project/<项目ID>/overview`，其余页面同理。页面每 5 秒刷新一次，标签页切到后台时暂停。

- **概览**（`/overview`）：只读。完成比例和各状态数量，checkpoint 里的当前阶段，下一批可以开始的任务和跳过原因，依赖图，最近的执行记录，规划文档（按 Markdown 显示）。当前阶段只显示阶段、时间、当前任务和规格文件名，不显示备注。
- **任务**（`/`）：任务列表和统计，可按状态筛选。“已完成”只计入有集成记录的 `DONE` 任务。
- **任务详情**（`/task/<任务ID>`）：描述和各节正文、优先级、预估小时、角色、固定模型和 droid、依赖、失败次数、相关文件和集成记录。描述和各节正文按 Markdown 显示，内容先转义再加标签。没写角色的任务显示为“当前会话直接执行”。任务的结构化验收条件（`acceptance` 字段）页面上不显示，用 `acceptance <任务ID>` 查看。
- **团队**（`/team`）：只读。角色和模型、手动运行的连接检查、最近子 Agent 的实际模型核对、下一批预览。连接检查只验证 droid 配置、BYOK 模型登记和模型服务的 TCP 连接，不代表鉴权或模型请求能成功。

### 在页面上改状态

任务详情页可以把任务改成待处理、待办、进行中、待审查、待确认集成、已拒绝、阻塞或失败。有两个限制：

- 不能改成已完成。完成要在项目里运行 foreman 的 `integrate <任务ID> --commit <SHA>`，确认提交已集成。
- 用 `execution begin` 或 `run` 开始过的任务，状态只能用 foreman 的 `execution` 和 `integrate` 命令修改，页面会拒绝（409）。

## 和 CLI 一起用

页面和 foreman CLI 读写同一个任务板。在项目里用 CLI 写入或推进任务，页面下一次刷新就能看到。`foreman` 是技能目录下的 `bin/foreman`（安装时加 `--bin-dir` 可以链接到 `PATH`；在本仓库里是 `foreman/bin/foreman`）：

```bash
cd /path/to/project
foreman add --file planning/plan.json
foreman show
```

## 接口

所有接口返回 JSON，带 `success` 字段，出错时另有 `error`。默认项目用 `/api/<资源>`，其他项目用 `/api/projects/<项目ID>/<资源>`。

```text
GET  /api/projects                          项目列表
POST /api/projects                          登记项目 {"name": "项目名称", "path": "/absolute/path"}
GET  /api/tasks                             任务列表
GET  /api/tasks/<任务ID>                    单个任务
PUT  /api/tasks/<任务ID>                    改状态 {"status": "BLOCKED"}，可加 "reset_retries": true
GET  /api/board                             各状态数量和完成比例
GET  /api/history                           执行记录（只含任务、时间、状态、droid 和模型）
GET  /api/team                              角色、模型和并发设置
GET  /api/team/check                        连接检查
GET  /api/team/audit                        子 Agent 实际模型核对
GET  /api/batch                             下一批任务和跳过原因
GET  /api/checkpoint                        当前阶段
GET  /api/graph                             依赖图的节点和边
GET  /api/specs                             规划文档列表
GET  /api/specs/<文件名>                    规划文档内容（超过 1 MiB 时截断）
```

带 `Origin` 的修改请求必须来自同一个地址，跨站请求返回 403。数据路径经符号链接指到项目之外时拒绝读取。

## 故障排查

### 端口被占用
`foreman web start` 会从 5001 起自己找空闲端口；要指定就用 `foreman web start --port 8080`。macOS 的隔空播放接收器占用 5000，所以默认用 5001。

### foreman web start 说需要 Flask 或没有看板文件
按提示里的命令安装 Flask。提示这份安装里没有 Web 看板的文件时，用本仓库的 `install.py` 加 `--force` 重新安装技能。启动失败的日志在项目的 `.task-management/web.log`。

### 任务列表为空
先确认顶部选的是哪个项目：默认项目是启动看板的那个项目，不一定是你正在开发的项目。其他项目要先登记，登记的路径应是项目根目录（有 `planning/tasks.json` 的那一层）。

### 页面显示 Internal server error
服务不把错误细节发给页面，也不写进终端日志，避免泄露文件内容。通常是项目里某个数据文件不是合法的 JSON。在项目目录运行：

```bash
foreman doctor
```

它只读不写，会列出读不出来的任务板、配置、checkpoint 和执行记录，以及各自的出错位置和处理办法。checkpoint 损坏时运行 `foreman execution sync`：原文件另存为 `checkpoint.json.corrupted`，进度按任务板重建。

### 项目未登记（404）或项目目录不存在（409）
404 表示地址里的项目 ID 不在注册表里，回到首页重新选择。409 表示登记的目录不存在或已变成符号链接；恢复目录，或者用新路径重新登记。

### 状态改不了
改成已完成会被拒绝，要用 `integrate`。已经 `begin` 过的任务返回 409，用 `show <任务ID>` 查看下一步该运行的命令。
