# 恢复执行指南

本文件供对话压缩后快速恢复使用。触发 Skill 时如果检测到 checkpoint，读取本文件即可恢复。

---

## Checkpoint 文件

**路径**: `.dual-ai-collab/checkpoints/state.json`

**字段说明**:

| 字段 | 说明 |
|------|------|
| `phase` | 当前阶段（见下方映射表） |
| `updated_at` | 最后更新时间（UTC） |
| `spec_file` | 需求规范文档路径 |
| `task_file` | 任务板路径（默认 `planning/codex-tasks.md`） |
| `current_task` | 当前执行的任务编号 |
| `total_tasks` | 任务总数 |
| `completed_tasks` | 已完成任务数 |
| `fix_round` | 当前修复轮次（最大 3） |

---

## Phase → 恢复动作

| phase | 恢复动作 | 最小文件集 |
|-------|----------|-----------|
| `interview` | 读取已收集信息，继续访谈 | `state.json` |
| `spec_generated` | 跳到第 4 步（拆分任务） | `state.json` + `spec_file` |
| `tasks_created` | 跳到第 5 步（等待用户审查） | `state.json` + `planning/codex-tasks.md`/`planning/tasks.json` |
| `user_approved` | 跳到第 6 步（启动开发） | `state.json` + `planning/codex-tasks.md`/`planning/tasks.json` |
| `developing` | 继续执行 OPEN/IN_PROGRESS 任务 | `state.json` + `planning/codex-tasks.md`/`planning/tasks.json` |
| `auditing` | 对 AWAITING_REVIEW 任务继续审查 | `state.json` + `planning/codex-tasks.md`/`planning/tasks.json` + `planning/audit-reports/` |
| `fixing` | 对 REJECTED 任务继续修复 | `state.json` + `planning/codex-tasks.md`/`planning/tasks.json` + `planning/audit-reports/` |

---

## 恢复步骤

1. 读取 `state.json`，提取 `phase`
2. 根据上表确定恢复动作
3. 读取对应的最小文件集
4. 向用户报告恢复状态：

```
🔄 检测到中断的流程，正在恢复...
📍 中断阶段：[phase]
📋 任务板：planning/codex-tasks.md（真相源：planning/tasks.json）
📊 进度：[completed_tasks]/[total_tasks]
⏩ 继续执行...
```

5. 跳转到对应阶段继续执行

---

## 恢复时的特殊处理

### developing 阶段
- 检查任务板中有无 IN_PROGRESS 的任务
- 有 → 通过执行器查询运行状态：`python3 "$SKILL_DIR/scripts/run_task.py" status XXX`
  - running → 继续轮询
  - success → app-server 使用 `run complete XXX`，验收通过后进入待审查；不直接更新 DONE
  - failed/stopped/blocked/interrupted → 读取 events、result 和 worker 日志；需要修复时使用 `run continue XXX "修复说明"` 复用原 thread，避免重复 start
  - not_found → 检查执行目录与任务编号，再决定是否首次 start
- 先运行 `board show --json` 聚合任务阶段、执行、验收、审查和集成状态；面板本身只读，不恢复进程
- 待审查任务读取记录里的 workdir 和验收报告，使用 `board review`；待集成任务在原仓库完成集成和提交后使用 `board integrate`
- 旧 DONE / VERIFIED 需要显式审查和集成确认，不按旧状态自动解锁依赖
- `--context-task-file` 关联的任务板会在 continue / repair 时刷新快照；维护任务章节中的规范引用与决策，不将整个聊天记录复制给执行模型
- 无 → 选择下一个 OPEN 任务继续
- 如果当前是 Claude-only 模式：不查询后台进程，直接继续同步执行下一个任务

### auditing / fixing 阶段
- 读取任务板，找到需要审计/修复的任务继续处理
- `fix_round` 超过 3 → 标记 FAILED

---

## Checkpoint 损坏处理

如果 `state.json` 不是有效 JSON：

1. 备份损坏文件：`cp state.json state.json.corrupted`
2. 检查 `planning/codex-tasks.md` 或 `planning/tasks.json` 是否存在
   - 存在 → 根据任务板状态推断当前阶段
   - 不存在 → 从第 1 步重新开始
3. 创建新的 checkpoint
4. 向用户报告：

```
⚠️ Checkpoint 文件损坏，已根据任务板状态恢复
📍 推断阶段：[phase]
⏩ 继续执行...
```

在入口检查脚本中，损坏 checkpoint 会输出：

```text
CHECKPOINT_CORRUPTED
state.json.corrupted
```

此时应优先检查任务板和审计报告，再按上面的恢复步骤继续。

## 已实现但环境阻塞的人工验收

先用 `board show --verbose` 和 `run watch XXX` 确认原因。解决环境问题通常应 `run continue`；如果已经在合适环境实际验证所有标准，可先 `run verify-manual XXX --list`，逐项确认后传入 `--confirm 编号` 和 `--note 测试证据`。不得替用户猜测或默认确认。随后 `board review XXX --force --decision approved --note 审查结论` 允许 blocked 任务通过审查；最终集成仍须目标仓库自动验收。执行历史保留原始 blocked 原因。
