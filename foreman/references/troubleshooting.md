# 故障排查

命令报错、被拒绝，或结果和预期不一样时读这份文件，按现象找对应的小节。错误信息在标准错误输出里以“错误:”开头，通常已经写明是哪个文件、为什么、下一步做什么；先照它说的做。

## 不知道哪里出了问题

```bash
foreman doctor    # 加 --json 输出结构化结果
```

它只读不写，逐项列出 Python、git、`foreman` 是否在 PATH、任务板、配置、checkpoint、执行记录，以及派发需要的 droid、模型配置和角色。“问题”一项会让一部分命令用不了，退出码为 1；“注意”不影响当前能做的事。规划本身的问题仍用 `validate`。

“droid”“模型配置”“角色”三项只关系到写了 `role` 的任务。有任务在等用户为角色选模型时，“角色”是问题属于预期：直接执行的任务照常进行，那个任务按没完成汇报。

## 任务板不存在

```bash
foreman init
```

## 命令说“任务板没有任务”，但项目里有任务

看标准错误输出：提示“没有任务板或配置”说明从当前目录往上（到 git 仓库根目录为止）没找到 `planning/tasks.json` 或 `.task-management/config.json`。项目根目录在另一个 git 仓库里，或者当前目录本身是一个独立的 git 仓库时会这样；`cd` 到项目根目录再运行。

## execution 命令提示“找不到执行记录或任务”

写的既不是已有的 `execution_id`，也不是任务板上的任务。任务存在但还没 `begin` 过时，提示会改成先运行 `execution begin`。

## execution begin 或 run 提示“任务尚不可开始”

任务不在当前可开始的一批里，提示后面会写原因：依赖还没集成、文件和进行中的任务重叠、角色没配置，或状态不是 PENDING。达到并发上限时会列出正在进行的任务。`batch` 的 `skipped` 能一次看到所有任务的原因。

## run 提示任务没有 role

没有 `role` 的任务由当前会话直接执行，用 `execution begin`（SKILL.md 的 2.2）。要派发就用 `add --replace` 给任务补上 `role`。

## 旧任务板的任务缺 files 或结构化 acceptance

早期任务板把验收命令写在“验收标准”章节的反引号里，没有 `files`。`acceptance <任务ID>` 仍能列出这些命令。要走现在的登记和验收，用 `add --replace` 补齐 `files`、`runtime_dependencies` 和 `acceptance`。不补也能继续用 `update` 改状态、`integrate` 确认集成，但没有文件基线和验收记录。

## 依赖循环或任务一直不被挑中

```bash
foreman validate
```

`add` 写入后只列出这批任务自己的问题；`validate` 检查整个任务板，会列出依赖环、不存在的依赖和缺失的字段。

## execution accept 提示“实际模型尚未核对通过”

派发的任务要先核对子 Agent 实际使用的模型，通过后才能验收：

```bash
foreman execution audit <execution_id>
```

`run` 结束时会自动核对一次；出现这条提示，说明那次没有通过，或者任务是手工用 Task 派发的。仍不通过时不要换模型，也不要改记录：检查实际文件后运行 `execution block <execution_id> --reason "实际模型不符及文件检查结果"`，报告用户。当前会话直接执行的任务没有这一步。

## 派发结果是 permission_rejected

子 Agent 调用了不被允许的操作，整次派发被终止，常见原因是把命令标成了 high 风险。先 `execution inspect` 看已经写入了什么（被终止前的文件会保留），再决定验收还是 `execution retry` 并在原因里写明不要做哪类操作。不要改用 `--skip-permissions-unsafe`。

## run 提示必须重新运行 preflight

通过记录和权限级别、Droid 可执行文件、保护策略绑定，任何一项变化后都要重新运行 `preflight --dispatcher <调度模型ID>`。

## 配置丢失

```bash
foreman init    # 补写默认配置，不动已有任务板
```

## 提示某个文件“读不出来”或“无法使用”

任务板、`.task-management/config.json` 和执行记录损坏时，命令报出文件和出错位置后停下，不改动文件：修好 JSON，或从 git、备份恢复。配置文件里可能有角色，`init` 和 `config set` 不会用默认配置盖掉它；确认不需要其中的内容时才删除它再 `init`。checkpoint 损坏时运行 `foreman execution sync`：原文件另存为 `checkpoint.json.corrupted`，进度按任务板重建，规格路径等上下文从那个文件里找回后用 `checkpoint save` 补上。

## Task 报 Droid configuration not found

1. 运行 `foreman team check`，确认 `.factory/droids/tm-<角色>.md` 存在。
2. 文件是本会话中途生成或修改的：保存 checkpoint，开新会话再继续。

## 在 Windows 上命令直接退出

只支持 macOS 和 Linux。在 WSL 里安装和运行。
