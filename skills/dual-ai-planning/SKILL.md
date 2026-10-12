---
name: dual-ai-planning
description: 在本地开发项目中做需求规划、任务拆分、依赖分析、任务板维护和断点恢复。适用于用户要求制定开发计划、建立任务板或继续已有任务板；由当前会话直接实现，不调度其他模型 CLI。
---

# 规划与任务板

这是 Dual AI Collaboration 的轻量工作流。当前会话负责规划、实现、验收和自审。无需启动 Codex/Claude CLI、app-server 或子 agent。用户只要规划时，交付规格与任务板后结束；已授权开发时继续实现，不增加逐任务审批。

## 本地工具

将 `<skill>` 替换为本技能目录，在**实际目标项目根目录**运行：

```bash
python3 <skill>/scripts/planning.py checkpoint-check
python3 <skill>/scripts/planning.py board show
```

安装目录的 `source.json` 指向本地 Dual AI Collaboration 仓库；工具复用该仓库，移动仓库后需重新安装。Python 命令只是任务管理程序。入口不提供模型启动或适配器命令；`verify` 会执行任务中列出的验收命令，执行前需阅读确认其属于当前任务。

## 规划

- 先读项目说明、已有规格、任务板和代码，避免重复建任务。只针对影响设计的缺失信息提问；普通小修改无需强行建板。
- 规格保存到 `planning/specs/<主题>.md`：目标、范围、约束、关键决策、可验证的完成标准。问题直接在对话中提出，不创建网页追问流程。仅需规划时不顺便改实现。
- `planning/tasks.json` 是真相源，`planning/codex-tasks.md` 是派生视图。新项目先 `init`，再用 `templates create <类型> <编号> --add` 创建任务，类型用 `templates list` 查看；依赖用 `--depends-on 001`，变量用 `--var key=value`。每个任务都应有明确边界和真实验收命令。
- 复杂任务做一次依赖、验收和范围自查即可；不强制多轮访谈。不要自动调用 grill-me 或另一个 agent。

修改任务细节时，使用源仓库 `skill/scripts/tasks_store.py` 的 `read_tasks_document` / `write_tasks_document`，并用 `platform_utils.FileLock` 锁定 `resolve_task_paths(...).json_path.with_suffix('.json.lock')`。任务章节为 `sections: [{heading, body}]`；`验收标准` 章节内反引号包围的文本会作为命令执行，所以只用反引号包围真正的完整验收命令。写入后同步 Markdown，不单独修改派生视图。

## 当前会话执行

```bash
python3 <skill>/scripts/planning.py select
python3 <skill>/scripts/planning.py board context 001
python3 <skill>/scripts/planning.py update 001 IN_PROGRESS
# 当前会话直接编辑代码；先检查 extract 的命令，再执行验收。
python3 <skill>/scripts/planning.py verify extract 001
python3 <skill>/scripts/planning.py verify run 001
# 仅在验收成功后：
python3 <skill>/scripts/planning.py update 001 AWAITING_REVIEW
# 检查实现和验收结果，note 中填写真实证据，明确这是自审。
python3 <skill>/scripts/planning.py board review 001 --decision approved --note "自审结论与验收证据"
```

`verify run` 不会持久写入运行记录，需把实际结果记入 `planning/progress-reports/`，再进入待审查。未启动后台 worker 时面板执行列仍可能显示 `not_started`，不伪造执行记录。验收失败就修复并重验；不要更新为已通过。

原项目的 `DONE` 表示已确认 Git 集成，不仅仅是实现完成。审查后可保持 `AWAITING_INTEGRATION`；在用户授权提交且目标仓库干净后，用 `board integrate 001 --target <仓库绝对路径> --commit <SHA> --note <说明>` 核验提交及重新验收。该命令不提交、不合并。依赖直到集成确认才解锁，不用手工改 `DONE` 绕过。已有 app-server 执行记录若导致审查拒绝，说明状态冲突，不启动新模型会话补齐状态。

## 上下文与恢复

用任务章节记录约束、关键决策、相关文件和未完成项；详细材料引用规格文件。阶段切换时可用 `checkpoint-write developing current_task=001 task_file=planning/tasks.json` 保存游标。新会话读取 checkpoint、任务和最新进展，再按需读代码；文件记录帮助恢复，不承诺保留聊天窗口的完整上下文。

用户要看网页时复用源仓库 `web_server.py` 与现有多项目登记功能；先检查已有服务，避免重复启动。规划技能不修改 Web 页面或安装新的 Web 服务，也不使用网页的模型执行按钮。
