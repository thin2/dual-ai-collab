---
name: task-management
description: 任务规划、拆分、依赖分析和执行管理。支持需求访谈、任务板维护、子 agent 调度执行。
---

# 任务管理技能

完整的任务管理工作流：规划 → 任务板 → 执行 → 验收 → 审查 → 集成确认。

## 核心能力

- 需求访谈和复杂度判断
- 任务拆分和依赖分析
- 任务板管理（CRUD、状态追踪）
- 子 agent 执行调度（基于 complexity→droid 映射）
- 验收标准执行和审查
- 执行历史追踪
- Checkpoint 恢复

## 快速开始

### 检查项目状态

```python
from pathlib import Path
from lib import CheckpointManager, TaskBoard

project_root = Path.cwd()
checkpoint = CheckpointManager(project_root)
print(checkpoint.check())

board = TaskBoard.load(project_root)
stats = board.get_statistics()
print(f"总任务: {stats['total']}")
print(f"按状态: {stats['by_status']}")
```

### 初始化新项目

```python
from pathlib import Path

project_root = Path.cwd()

# 创建目录结构
(project_root / "planning" / "specs").mkdir(parents=True, exist_ok=True)
(project_root / ".task-management").mkdir(parents=True, exist_ok=True)

# 创建空任务板
from lib import write_tasks_document
write_tasks_document({"tasks": []}, project_root / "planning" / "codex-tasks.md")

print("项目初始化完成")
```

## 工作流程

### 1. 规划阶段

#### 1.1 复杂度判断

根据用户需求判断应该投入多少规划精力：

**简单需求**（2-3 轮）：
- Bug 修复、小功能增强
- 边界清晰，技术路线明确
- 直接澄清需求 → 生成任务板

**中等需求**（4-6 轮）：
- 新页面、API 模块
- 需要技术权衡
- 常规访谈 + 可选对抗性提问

**复杂需求**（6-10 轮）：
- 认证、支付、权限、架构变更
- 跨模块重构
- 深入访谈 + 对抗性提问暴露风险

#### 1.2 需求访谈

访谈维度（按复杂度裁剪）：
1. 功能范围和目标
2. 技术实现约束
3. 数据和状态管理
4. 用户体验和交互
5. 性能和可靠性
6. 安全和合规
7. 部署和维护
8. 验收标准

**对抗性提问**（可选，用于中等和复杂需求）：
- 不问显而易见的问题
- 深入细节：并发冲突、边界情况、权衡取舍
- 暴露隐藏假设和技术风险
- 当目标清晰、决策明确时停止

#### 1.3 生成规格和任务板

**规格文档**：
```python
from datetime import datetime
from pathlib import Path

spec_file = Path.cwd() / "planning" / "specs" / f"{datetime.now():%Y%m%d-%H%M%S}-[功能名称].md"
spec_file.parent.mkdir(parents=True, exist_ok=True)

spec_content = """# [功能名称]

## 目标
[核心目标，1-2 句]

## 范围
### 包含
- [功能点]

### 不包含
- [明确排除的内容]

## 技术约束
- [技术栈、性能要求、集成约束]

## 关键决策
1. [决策] - [理由]

## 验收标准
1. [可执行的验收条件]

## 风险和未知项
- [风险] - [缓解措施]
"""

spec_file.write_text(spec_content, encoding="utf-8")
print(f"规格文档已保存: {spec_file}")
```

**任务板**：
```python
from lib import TaskBoard

board = TaskBoard.load(Path.cwd())
document = board.get_document()

# 添加任务
new_task = {
    "id": "001",
    "title": "实现用户登录 API",
    "status": "PENDING",
    "type": "feature",
    "priority": 1,
    "estimated_hours": 2.5,
    "execution_level": "normal",  # quick/normal/heavy
    "dependencies": "无",
    "files": ["src/api/auth.py", "tests/test_auth.py"],
    "sections": [
        {
            "heading": "任务描述",
            "body": "实现基于 JWT 的用户登录接口"
        },
        {
            "heading": "验收标准",
            "body": """
1. 接口返回正确的 JWT token
2. 密码错误返回 401
3. 通过测试：`pytest tests/test_auth.py -k test_login`
"""
        }
    ]
}

document["tasks"].append(new_task)
board.save_document(document)
print(f"任务 {new_task['id']} 已添加")
```

#### 1.4 规划审计

检查清单：
- ✅ 目标覆盖：是否遗漏用户需求
- ✅ 任务拆分：边界清晰，可独立执行
- ✅ 依赖顺序：合理，无循环依赖
- ✅ 验收标准：可验证，非空泛描述
- ✅ 风险记录：边界情况、失败路径

输出：READY 或 NOT_READY + 具体问题

#### 1.5 用户确认

让用户明确回复：
1. 开始开发
2. 修改规划
3. 取消

确认后保存 checkpoint：
```python
from lib import CheckpointManager

checkpoint = CheckpointManager(Path.cwd())
checkpoint.save(
    phase="developing",
    spec_file="planning/specs/20261012-login-feature.md",
    task_file="planning/codex-tasks.md",
    total_tasks=5
)
```

### 2. 执行阶段

#### 2.1 选择任务

```python
from lib import TaskBoard

board = TaskBoard.load(Path.cwd())
task = board.get_next_task()

if task:
    print(f"下一个任务: {task['id']} - {task['title']}")
else:
    print("没有可执行的任务（依赖未满足或全部完成）")
```

#### 2.2 规划执行

```python
from lib import TaskExecutor

executor = TaskExecutor(Path.cwd())
plan = executor.plan_execution("001")

print(f"任务: {plan['task_id']} - {plan['task_title']}")
print(f"复杂度: {plan['complexity']}")
print(f"使用 Droid: {plan['droid']}")
```

#### 2.3 调度子 agent

更新状态并调用 Task 工具：

```python
# 更新状态
board.update_task_status("001", "IN_PROGRESS")

# 记录执行开始
from lib import ExecutionHistory
history = ExecutionHistory(Path.cwd())
execution_id = history.record_start(
    task_id="001",
    droid=plan['droid'],
    complexity=plan['complexity']
)
```

然后使用 Task 工具：

```
Task(
    subagent_type=plan["droid"],
    description=f"实现任务 {plan['task_id']}: {plan['task_title']}",
    prompt=plan["context"],
    complexity=plan["complexity"],
    await=True
)
```

子 agent 完成后记录结果：

```python
# 假设子 agent 成功完成
history.record_completion(execution_id, status="success")

# 如果失败
# history.record_completion(execution_id, status="failed", error_message="...")
```

#### 2.4 验收

提取并执行验收命令：

```python
commands = board.get_acceptance_commands("001")
print(f"验收命令: {commands}")

# 执行验收（使用 Execute 工具）
# Execute(command=commands[0], riskLevel="medium", summary="Run acceptance test")
```

验收通过后：
```python
board.update_task_status("001", "AWAITING_REVIEW")
```

验收失败：修复或重新调度子 agent。

### 3. 审查阶段

审查要点：
- 代码质量：可读性、注释、错误处理
- 功能完整：是否满足任务描述
- 验收通过：所有验收命令成功
- 副作用：是否影响其他模块

```python
# 审查通过
board.update_task_status("001", "AWAITING_INTEGRATION")

# 审查拒绝：回到 IN_PROGRESS，记录问题
```

### 4. 集成确认

将代码集成到目标仓库并提交后，确认集成：

```python
from lib import TaskBoard

board = TaskBoard.load(Path.cwd())
task = board.get_task("001")

# 记录集成信息
task["integration"] = {
    "target_repo": "/path/to/source",
    "commit": "abc123def",
    "timestamp": "2026-10-12T10:30:00Z",
    "note": "已合并到 main 分支"
}

# 重新运行验收确认
# ... 执行验收命令 ...

# 标记完成
task["status"] = "DONE"
board.save_document(board.get_document())
```

只有标记为 DONE 且有有效 integration 记录的任务才会解锁依赖。

### 5. Checkpoint 管理

```python
from lib import CheckpointManager

checkpoint = CheckpointManager(Path.cwd())

# 保存进度
checkpoint.save(
    phase="developing",
    current_task="003",
    completed_tasks=2,
    task_file="planning/codex-tasks.md"
)

# 检查状态
print(checkpoint.check())

# 清除
checkpoint.clear()
```

## 配置系统

### Complexity → Droid 映射

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
    },
    "by_hours": {
      "<=1": "light",
      "<=3": "medium",
      ">3": "heavy"
    }
  }
}
```

### 配置管理

```python
from lib import ExecutionConfig

config = ExecutionConfig(Path.cwd())

# 查看配置
print(config.get_all_settings())

# 修改映射
config.set_droid_for_complexity("medium", "code-architect")

# 测试复杂度判定
task = {"type": "feature", "estimated_hours": 2}
complexity = config.determine_complexity(task)
print(f"复杂度: {complexity}")
```

### 复杂度判定规则

优先级：
1. **显式 execution_level**：quick → light, normal → medium, heavy → heavy
2. **任务类型**：docs/test → light, feature/bugfix → medium, refactor/architecture → heavy
3. **预估时间**：≤1h → light, ≤3h → medium, >3h → heavy
4. **默认值**：medium

## 执行历史

```python
from lib import ExecutionHistory

history = ExecutionHistory(Path.cwd())

# 查看任务历史
records = history.get_task_history("001")
for record in records:
    print(f"{record.start_time}: {record.status} (droid: {record.droid})")

# 查看所有历史
all_records = history.get_all_history()
print(f"总执行次数: {len(all_records)}")
```

## 可视化

### 依赖图（Mermaid）

```python
from lib import read_tasks_document

document = read_tasks_document()
tasks = document.get("tasks", [])

# 生成 Mermaid 图
lines = ["graph TD"]
for task in tasks:
    task_id = task["id"]
    title = task.get("title", "")
    lines.append(f'  {task_id}["{task_id}: {title}"]')
    
    deps = task.get("dependencies", "")
    if deps and deps != "无":
        for dep in deps.replace("#", "").split(","):
            dep = dep.strip()
            if dep:
                lines.append(f'  {dep} --> {task_id}')

mermaid_code = "\n".join(lines)
print(mermaid_code)

# 保存到文件
Path("planning/dependencies.mmd").write_text(mermaid_code, encoding="utf-8")
```

## 最佳实践

1. **规划投入与需求匹配**：简单需求不要过度规划
2. **任务拆分 1-3 小时**：便于验收和回滚
3. **验收标准可执行**：避免"功能正常"这种描述
4. **依赖关系明确**：前后端可通过接口契约并行开发
5. **及时更新任务板**：状态变更后立即同步
6. **记录关键决策**：在任务或规格中记录 why，不只是 what
7. **集成确认**：不要跳过集成验证环节

## 故障排查

### 任务板不存在
```python
# 初始化项目
from lib import write_tasks_document
write_tasks_document({"tasks": []}, "planning/codex-tasks.md")
```

### 依赖循环
```python
# 检测循环依赖
from lib import read_tasks_document

document = read_tasks_document()
# 任务板会在写入时检测循环依赖并拒绝
```

### 配置丢失
```python
# 恢复默认配置
from lib import ExecutionConfig
config = ExecutionConfig(Path.cwd())
config.save()  # 写入默认配置
```

### Droid 不存在
如果配置的 droid 不存在，Task 工具会失败。检查：
```bash
ls ~/.factory/droids/
```

确保配置的 droid 名称存在。

## 与其他工具配合

### Web UI
可选的任务监控界面，见仓库中的 `web_server.py`。

### CLI 工具
`tools/cli.py` 提供命令行接口，便于脚本和 CI 集成。

### Git 集成
任务完成后，建议的提交流程：
1. 在独立分支完成任务
2. 验收通过
3. 提交并推送
4. 运行集成确认
5. 标记 DONE

## 限制和注意事项

- Task 工具不能直接指定模型，只能通过 complexity 和自定义 droid 间接控制
- 集成确认需要手动触发，不会自动检测 Git 提交
- 历史记录只保存元数据，不保存完整日志
- 循环依赖检测在写入时进行，读取时不校验
