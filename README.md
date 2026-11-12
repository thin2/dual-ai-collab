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

**详细文档**：[docs/legacy/](./docs/legacy/README.md)。旧版的 README、教程、开发记录和设计文档都在这个目录，不再更新。

旧版脚本也读写 `planning/tasks.json`，但格式和文件锁与 foreman 不兼容，同一个任务板不要两边混用。

## Web UI（Foreman）

可选的本地监控界面，在本仓库里运行，需要 Flask：

```bash
python3 web_server.py 5001
open http://localhost:5001
```

- 默认显示的是本仓库目录。要看自己的项目，点页面顶部的“登记项目”，填项目根目录的绝对路径。
- 有任务列表和详情、概览页（`/overview`）和团队页（`/team`）。概览页和团队页只读。
- 页面能改少数状态，但不能把任务标为完成：完成要通过技能的 `integrate`。已经用 `execution begin` 或 `run` 开始过的任务不能在页面上改状态。
- 页面不会启动子 Agent，也不调用模型。服务只监听 `127.0.0.1`。

页面内容、接口、读取哪些文件和故障排查见 [docs/web-ui.md](./docs/web-ui.md)。

## 文档

| 想做什么 | 看哪里 |
| --- | --- |
| 安装和使用 foreman，查命令 | [foreman/README.md](./foreman/README.md) |
| 完整工作流（Agent 执行技能时读的那份） | [foreman/SKILL.md](./foreman/SKILL.md) |
| 验收证据格式、中断恢复和隔离边界 | [foreman/references/managed-workflow.md](./foreman/references/managed-workflow.md) |
| 用 Web 界面监控任务 | [docs/web-ui.md](./docs/web-ui.md) |
| 从 `dual-ai-planning` 或 `dual-ai-collab` 迁移 | [foreman/README.md](./foreman/README.md) 的“迁移指南” |
| 参与开发 | [CONTRIBUTING.md](./CONTRIBUTING.md) |
| 旧版 dual-ai-collab（不再更新） | [docs/legacy/](./docs/legacy/README.md) |

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
├── docs/
│   ├── web-ui.md             # Web UI 使用指南
│   └── legacy/               # 旧版的文档（不再更新）
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
