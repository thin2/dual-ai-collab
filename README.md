# Dual AI Collaboration

多 AI 协同开发系统 - 包含多个技能版本以适应不同的使用场景。

## 技能版本

### 1. Task Management (推荐 - Droid 原生)

**适用场景**：Factory Droid 环境

完全原生的 Droid 任务管理技能，使用 Task 工具调度子 agent，无需外部进程。

**特性**：
- ✅ 原生 Droid Task 工具集成
- ✅ 用户可配置 complexity→droid 映射
- ✅ 轻量级 Checkpoint 和执行历史
- ✅ 完整的规划和验收工作流
- ✅ 向后兼容旧任务板

**安装**：
```bash
python3 install.py --profile task-management
# 默认安装到 ~/.factory/skills/task-management
```

**详细文档**：[task-management/README.md](./task-management/README.md)

---

### 2. Dual AI Planning (轻量级)

**适用场景**：Codex 环境，只需规划功能

轻量级规划技能，由当前会话直接执行，不启动外部模型 CLI。

**特性**：
- 需求规划和任务拆分
- 任务板维护
- 依赖分析
- Checkpoint 恢复
- 复用本地仓库代码

**安装**：
```bash
python3 install.py --profile planning
# 默认安装到 ~/.codex/skills/dual-ai-planning
```

**适用场景**：
- 只需要任务规划和管理
- 由当前会话直接实现，无需调度其他模型
- 兼容现有 Web 面板

---

### 3. Dual AI Collab (完整版 - Legacy)

**适用场景**：需要完整的 Claude+Codex 协作流程

原始的双 AI 协作系统，支持多种执行后端和模型路由。

**特性**：
- Claude 规划 + Codex/Claude 执行
- 多模型适配器路由和回退
- app-server 后端支持
- 完整的审计和恢复机制

**安装**：
```bash
python3 install.py --profile full
# 默认安装到 ~/.claude/skills/dual-ai-collab
```

**详细文档**：[README-legacy.md](./README-legacy.md)（原 README.md）

---

## 快速选择

| 场景 | 推荐技能 | 理由 |
|------|---------|------|
| 使用 Droid/Factory | **task-management** | 原生集成，最简洁 |
| 使用 Codex，只需规划 | **dual-ai-planning** | 轻量，无外部依赖 |
| 需要 Claude+Codex 完整协作 | **dual-ai-collab** | 功能最全 |
| 从旧版本迁移 | **task-management** | 向后兼容，架构更简单 |

## Web UI（所有版本共享）

可选的任务监控界面：

```bash
python3 web_server.py 5001
open http://localhost:5001
```

支持多项目管理和任务状态可视化。

## 迁移指南

### 从 dual-ai-collab 迁移到 task-management

1. **安装新技能**：
```bash
python3 install.py --profile task-management
```

2. **现有任务板兼容**：
   - `planning/tasks.json` 可以直接使用
   - 旧字段自动标准化
   - 需要重新做集成确认以解锁依赖

3. **配置迁移**：
   - 删除 `.dual-ai-collab/model-routing.json`
   - 创建 `.task-management/config.json`
   - 映射：quick→light, normal→medium, heavy→heavy

4. **工作流调整**：
   - 不再使用 `run start/stop` 命令
   - 在技能中直接调用 Task 工具
   - 验收仍使用 Execute 工具

详见：[task-management/README.md](./task-management/README.md)

## 测试

```bash
# 运行所有测试
python3 -m pytest tests/ -v

# 只测试新的 task-management
python3 -m pytest tests/test_task_management.py -v

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
├── task-management/           # 新版：Droid 原生技能
│   ├── SKILL.md
│   ├── README.md
│   ├── lib/                  # 核心库
│   └── tools/                # CLI 工具
├── skills/
│   └── dual-ai-planning/     # 轻量版：Codex 规划技能
├── skill/                    # 完整版：Legacy dual-ai-collab
│   ├── dual-ai-collab.md
│   ├── scripts/
│   └── references/
├── tests/                    # 测试
├── docs/                     # 文档
├── web_server.py            # Web UI（可选）
└── install.py               # 统一安装脚本
```

## 贡献

欢迎提交 Issue 和 Pull Request！

贡献指南：[CONTRIBUTING.md](./CONTRIBUTING.md)

## 许可证

MIT License

## 版本历史

- **v3.0** (2026-10) - 添加 task-management 技能（Droid 原生）
- **v2.0** (2026-10) - 添加 dual-ai-planning 轻量技能
- **v1.0** - 完整 dual-ai-collab 系统
