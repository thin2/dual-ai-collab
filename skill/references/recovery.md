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
| `tasks_created` | 跳到第 5 步（等待用户审查） | `state.json` + `planning/codex-tasks.md` |
| `user_approved` | 跳到第 6 步（启动开发） | `state.json` + `planning/codex-tasks.md` |
| `developing` | 继续执行 OPEN/IN_PROGRESS 任务 | `state.json` + `planning/codex-tasks.md` |
| `auditing` | 对 DONE 任务继续审计 | `state.json` + `planning/codex-tasks.md` + `planning/audit-reports/` |
| `fixing` | 对 REJECTED 任务继续修复 | `state.json` + `planning/codex-tasks.md` + `planning/audit-reports/` |

---

## 恢复步骤

1. 读取 `state.json`，提取 `phase`
2. 根据上表确定恢复动作
3. 读取对应的最小文件集
4. 向用户报告恢复状态：

```
🔄 检测到中断的流程，正在恢复...
📍 中断阶段：[phase]
📋 任务板：planning/codex-tasks.md
📊 进度：[completed_tasks]/[total_tasks]
⏩ 继续执行...
```

5. 跳转到对应阶段继续执行

---

## 恢复时的特殊处理

### developing 阶段
- 检查任务板中有无 IN_PROGRESS 的任务
- 有 → 检查对应 Codex 进程是否还在运行（`pgrep -f "codex exec"`）
  - 还在 → 继续轮询
  - 已退出 → 检查退出码，更新状态为 DONE 或回退 OPEN
- 无 → 选择下一个 OPEN 任务继续

### auditing / fixing 阶段
- 读取任务板，找到需要审计/修复的任务继续处理
- `fix_round` 超过 3 → 标记 FAILED

---

## Checkpoint 损坏处理

如果 `state.json` 不是有效 JSON：

1. 备份损坏文件：`cp state.json state.json.corrupted`
2. 检查 `planning/codex-tasks.md` 是否存在
   - 存在 → 根据任务板状态推断当前阶段
   - 不存在 → 从第 1 步重新开始
3. 创建新的 checkpoint
4. 向用户报告：

```
⚠️ Checkpoint 文件损坏，已根据任务板状态恢复
📍 推断阶段：[phase]
⏩ 继续执行...
```
