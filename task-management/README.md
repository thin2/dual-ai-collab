# Task Management Skill

Droid 原生任务管理技能 - 规划、拆分、执行和验收完整工作流。

## 特性

- 🎯 **需求访谈和复杂度判断**：根据需求规模调整规划深度
- 📋 **任务板管理**：CRUD 操作、状态追踪、依赖分析
- 🤖 **原生 Droid 集成**：使用 Task 工具调度子 agent，无需外部进程
- ⚙️ **灵活配置**：用户自定义 complexity→droid 映射
- ✅ **验收自动化**：从任务定义提取并执行验收命令
- 📊 **执行历史**：追踪任务执行记录和性能数据
- 🔄 **Checkpoint 恢复**：长期项目的进度保存和恢复

## 快速开始

### 安装

```bash
# 安装到 Factory/Droid
python install.py --profile task-management

# 默认安装到 ~/.factory/skills/task-management
# 可通过 FACTORY_SKILLS 环境变量或 --target 自定义
```

### 初始化项目

在技能中运行：

```python
from pathlib import Path
from lib import CheckpointManager, TaskBoard
from lib import write_tasks_document

project_root = Path.cwd()

# 创建目录结构
(project_root / "planning" / "specs").mkdir(parents=True, exist_ok=True)
(project_root / ".task-management").mkdir(parents=True, exist_ok=True)

# 创建空任务板
write_tasks_document({"tasks": []}, project_root / "planning" / "codex-tasks.md")

print("项目初始化完成")
```

或使用 CLI 工具：

```bash
cd /path/to/your/project
python ~/.factory/skills/task-management/tools/cli.py init
```

## 核心工作流

### 1. 规划阶段

根据需求复杂度选择合适的规划深度：

- **简单**（2-3 轮）：Bug 修复、小功能
- **中等**（4-6 轮）：新页面、API 模块
- **复杂**（6-10 轮）：认证、支付、架构变更

访谈完成后生成规格文档和任务板。

### 2. 执行阶段

```python
from pathlib import Path
from lib import TaskBoard, TaskExecutor, ExecutionHistory

project_root = Path.cwd()

# 选择下一个任务
board = TaskBoard.load(project_root)
task = board.get_next_task()

# 规划执行
executor = TaskExecutor(project_root)
plan = executor.plan_execution(task['id'])

print(f"任务: {plan['task_id']}")
print(f"复杂度: {plan['complexity']}")
print(f"使用 Droid: {plan['droid']}")

# 更新状态
board.update_task_status(task['id'], "IN_PROGRESS")

# 记录开始
history = ExecutionHistory(project_root)
execution_id = history.record_start(
    task_id=task['id'],
    droid=plan['droid'],
    complexity=plan['complexity']
)
```

然后调用 Task 工具：

```python
Task(
    subagent_type=plan["droid"],
    description=f"实现任务 {plan['task_id']}: {plan['task_title']}",
    prompt=plan["context"],
    complexity=plan["complexity"],
    await=True
)
```

### 3. 验收和审查

```python
# 提取验收命令
commands = board.get_acceptance_commands(task['id'])

# 执行验收（使用 Execute 工具）
# 验收通过后
board.update_task_status(task['id'], "AWAITING_REVIEW")

# 审查通过后
board.update_task_status(task['id'], "AWAITING_INTEGRATION")
```

### 4. 集成确认

完成 Git 提交后确认集成：

```python
task = board.get_task(task['id'])
task["integration"] = {
    "target_repo": "/path/to/repo",
    "commit": "abc123",
    "timestamp": "2026-10-12T10:30:00Z",
    "note": "已合并到 main"
}
task["status"] = "DONE"
board.save_document(board.get_document())
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
    }
  }
}
```

### 使用 CLI 配置

```bash
# 查看配置
python tools/cli.py config show

# 设置 droid 映射
python tools/cli.py config set execution.medium=code-architect

# 查看执行计划
python tools/cli.py plan-execution 001
```

## CLI 命令

```bash
# 初始化
python tools/cli.py init

# 选择下一个任务
python tools/cli.py select

# 任务统计
python tools/cli.py status

# 规划执行
python tools/cli.py plan-execution 001

# 更新状态
python tools/cli.py update 001 IN_PROGRESS

# Checkpoint 管理
python tools/cli.py checkpoint check
python tools/cli.py checkpoint save --phase developing --data current_task=001

# 查看历史
python tools/cli.py history
python tools/cli.py history --task-id 001

# 提取验收命令
python tools/cli.py acceptance 001
```

## 与原版本的差异

### 移除的功能
- ❌ 外部 CLI 进程调度（codex/claude 命令）
- ❌ Adapter routing 和 fallback chain
- ❌ 进程检测和僵尸清理
- ❌ 调度分析（psutil 依赖）
- ❌ app-server 后端

### 新增/改进的功能
- ✅ 原生 Droid Task 工具集成
- ✅ 用户可配置 complexity→droid 映射
- ✅ 简化的执行历史（只记录核心信息）
- ✅ 轻量级 Checkpoint（只保存状态快照）
- ✅ 完全向后兼容旧任务板格式

## 测试

```bash
# 运行测试
python -m pytest tests/test_task_management.py -v

# 测试覆盖
# - 任务板 CRUD
# - 配置系统
# - 复杂度判定
# - 执行计划
# - Checkpoint 管理
# - 执行历史
```

## 迁移指南

### 从 dual-ai-collab 迁移

1. 安装新技能：
```bash
python install.py --profile task-management
```

2. 现有任务板兼容：
- `.task-management/tasks.json` 可以直接使用
- 旧字段会自动标准化（`task_num` → `id`）
- 旧状态需要重新审查和集成确认

3. 配置迁移：
- 删除 `.dual-ai-collab/model-routing.json`
- 创建 `.task-management/config.json`
- 映射 quick→light, normal→medium, heavy→heavy

4. 工作流调整：
- 不再使用 `run start/stop` 命令
- 改为在技能中调用 Task 工具
- 验收仍然使用 Execute 工具执行命令

## 可选工具

### Web UI
保留原有的 `web_server.py` 用于可视化监控：

```bash
python web_server.py 5001
open http://localhost:5001
```

Web UI 支持多项目管理和状态查看。

## 最佳实践

1. **复杂度与需求匹配**：简单需求不要过度规划
2. **任务拆分 1-3 小时**：便于验收和回滚
3. **验收标准可执行**：写具体命令而非描述
4. **配置 droid 映射**：根据项目特点选择合适的 droid
5. **及时更新状态**：保持任务板与实际进度同步
6. **完整集成确认**：不要跳过验证环节

## 故障排查

### 任务板不存在
```bash
python tools/cli.py init
```

### Droid 不存在
检查配置的 droid 是否在 `~/.factory/droids/` 中：
```bash
ls ~/.factory/droids/
```

### 配置丢失
重新生成默认配置：
```bash
python tools/cli.py init
```

### 依赖循环
任务板在写入时会自动检测循环依赖并拒绝保存。

## 架构

```
task-management/
├── SKILL.md              # 技能主文件（完整工作流）
├── README.md            # 本文件
├── lib/                 # 核心库
│   ├── __init__.py
│   ├── store.py         # 任务存储
│   ├── board.py         # 任务板管理
│   ├── config.py        # 配置系统
│   ├── executor.py      # 执行规划
│   ├── history.py       # 执行历史
│   └── checkpoint.py    # Checkpoint 管理
├── tools/
│   └── cli.py           # CLI 工具
└── prompts/             # 提示词模板（预留）
```

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License
