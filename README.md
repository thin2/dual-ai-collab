# Dual AI Collaboration

任务规划与协同开发技能。现在只维护一个技能：**foreman**。

## Foreman（当前版本）

**适用场景**：Factory Droid。规划、任务板和“当前会话直接执行”只用 Python 标准库和 git；派发给固定模型角色需要 Droid。其他 CLI 的适配还没有做。

这个技能原名 `task-management`；原来的 `dual-ai-planning`（当前会话自己规划并实现的轻量技能）也已经并入，不再单独安装。

**特性**：
- 需求访谈、规格文档、任务拆分和依赖分析
- 任务板：`add` 写入、`show` 查看、`validate` 检查
- 两种执行方式，可在同一个任务板里混用：
  - 任务没写 `role`：当前会话直接实现，不启动子 Agent
  - 任务写了 `role`：派给用户选定模型的固定角色，隔离、并行执行
- 两种方式用同一套登记和验收：文件基线、范围外改动检查、逐项验收证据、集成确认后才解锁依赖
- Checkpoint 和中断恢复

**安装**：
```bash
python3 install.py --profile foreman
# 默认安装到 ~/.factory/skills/foreman
```

安装的是完整副本，不依赖本仓库的位置。

**详细文档**：[foreman/README.md](./foreman/README.md)

以前装过旧名字的技能的话，安装脚本不会动它们。装好 foreman 后自己删除，否则 Droid 里会同时出现两个内容相同的技能：

```bash
rm -rf ~/.factory/skills/task-management    # 改名前的安装
rm -rf ~/.codex/skills/dual-ai-planning     # Codex 里的旧技能
rm ~/.factory/skills/dual-ai-planning       # Droid 里指向它的链接（如果有）
```

改的只是技能名。项目里的 `.task-management/` 目录、角色前缀 `tm-` 和执行标记 `[tm:编号]` 都没有变，已有项目不需要迁移。

---

## Dual AI Collab（旧版，不再更新）

原始的 Claude+Codex 协作系统，支持多种执行后端和模型路由。代码在 `skill/`，Web UI 已不支持它。

```bash
python3 install.py --profile full
# 默认安装到 ~/.claude/skills/dual-ai-collab
```

**详细文档**：[README-legacy.md](./README-legacy.md)

旧版脚本也读写 `planning/tasks.json`，但格式和文件锁与 foreman 不兼容，同一个任务板不要两边混用。

## Web UI（Foreman）

可选的任务监控界面：

```bash
python3 web_server.py 5001
open http://localhost:5001
```

界面只支持新版 `foreman/lib`，提供多项目任务监控、概览页（`/overview`）和团队页（`/team`）。
概览页只读：完成比例、当前阶段和各状态数量，下一批可开始的任务和跳过原因，任务依赖图，最近的执行记录，以及 `planning/specs/` 下的规格文档（按 Markdown 显示）。
当前阶段来自 checkpoint，只显示阶段、时间、当前任务和规格文件名，不显示备注等自由文本。
任务详情里的任务描述和各节正文按 Markdown 显示（标题、列表、代码、表格等），内容先转义再加标签。
任务可查看角色、固定模型、失败次数、依赖和集成确认；没有角色的任务显示为“当前会话直接执行”。`DONE` 只有带有集成记录才计为完成。
Web 可更新待办、进行中、待验收、待集成、拒绝、阻塞和失败状态，完成任务需通过技能的 `integrate`；已经用 `execution begin` 或 `run` 开始过的任务不能在页面上改状态。

团队页只用于监控：查看角色与模型、手动检查连接、核对最近子 Agent 的实际模型，并预览下一批及跳过原因。
连接检查仅验证 droid 配置、BYOK 模型登记和服务 TCP 连接，不代表模型请求或鉴权成功；
没有核对记录表示尚未核对。页面不会启动子 Agent 或编辑模型。

项目登记保存在 `.task-management/projects.json`，可用环境变量 `TASK_MANAGEMENT_PROJECTS_FILE` 指定独立注册表。
默认项目 API 为 `/api/<resource>`，其他项目为 `/api/projects/<project_id>/<resource>`；
任务读取 `planning/tasks.json`（库内兼容 `codex-tasks.json`），配置和历史分别读取
`.task-management/config.json`、`.task-management/history/*.json`；
概览页另外读取 `.task-management/checkpoint.json` 和 `planning/specs/*.md`（不含子目录和符号链接）。
GET 请求不会初始化项目文件；旧注册表、旧运行记录和旧 run API 不再使用。
服务只监听 `127.0.0.1`，拒绝跨站修改请求，并检查数据路径不会经符号链接越出项目。

## 迁移指南

从 `dual-ai-planning` 或 `dual-ai-collab` 迁移的命令对照和注意事项见
[foreman/README.md](./foreman/README.md) 的“迁移指南”。

## 测试

```bash
# 运行所有测试
python3 -m pytest tests/ -v

# 只测试 foreman
python3 -m pytest tests/test_foreman.py tests/test_foreman_team.py tests/test_foreman_workflow.py -v

# 只测试安装逻辑
python3 -m pytest tests/test_install_pytest.py -v
```

## 开发

```bash
# 代码检查
ruff check .

# 修复可自动修复的问题
ruff check --fix .
```

## 项目结构

```
dual-ai-collab/
├── foreman/                  # 当前版本：规划、任务板和执行管理
│   ├── SKILL.md
│   ├── README.md
│   ├── lib/                  # 核心库
│   ├── tools/                # CLI 工具
│   └── references/
├── skill/                    # 旧版 dual-ai-collab（不再更新）
│   ├── dual-ai-collab.md
│   ├── scripts/
│   └── references/
├── tests/                    # 测试
├── docs/                     # 文档
├── web_server.py            # Web UI（可选）
└── install.py               # 安装脚本
```

## 贡献

欢迎提交 Issue 和 Pull Request！

贡献指南：[CONTRIBUTING.md](./CONTRIBUTING.md)

## 许可证

MIT License

## 版本历史

- **v3.2** (2026-11) - task-management 改名为 foreman；项目里的 `.task-management/` 和 `tm-` 前缀不变
- **v3.1** (2026-11) - dual-ai-planning 并入 task-management：没写角色的任务由当前会话直接执行
- **v3.0** (2026-10) - 添加 task-management 技能（Droid 原生）
- **v2.0** (2026-10) - 添加 dual-ai-planning 轻量技能
- **v1.0** - 完整 dual-ai-collab 系统
