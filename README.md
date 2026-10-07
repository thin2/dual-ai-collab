# Dual AI Collaboration

双 AI 协同开发系统 - 多模型智能路由、任务管理和项目分析的完整解决方案。

## ✨ 核心特性

- 🤖 **多模型适配器路由** - 根据任务复杂度自动选择最优 AI 模型
- 📊 **智能任务调度** - 基于优先级、依赖关系和系统资源的智能调度
- 📈 **任务分析可视化** - 依赖图、关键路径分析、并行机会识别
- 📝 **任务模板系统** - 快速创建标准化任务
- 📉 **执行历史追踪** - 完整的任务执行历史和性能分析
- 🔄 **自动回退机制** - 适配器不可用时自动切换备选方案
- 🎯 **结构化日志** - JSON 格式日志便于分析和监控

## 可恢复会话后端

新增 `app-server` 后端：保持线程上下文、读取事件、追加指导、中断，以及验收失败后在原会话修复。
支持显式 `--isolate` 创建独立 Git worktree，CLI 原有后端继续保留。

```bash
python3 skill/scripts/cli.py run start 001 "实现任务" --backend app-server --isolate
python3 skill/scripts/cli.py run status 001
python3 skill/scripts/cli.py run events 001
# 等执行成功，再运行；失败时启动同会话修复一次，随后需再次验收
python3 skill/scripts/cli.py run complete 001 --repair
```

`--isolate` 需要干净的 Git 工作区。真实 Codex 0.160.1 已跑通执行、失败验收、原线程修复、再次验收；
完整命令、权限与恢复边界见 [会话后端说明](./docs/session-backend.md)。

## 🚀 快速开始

### 安装

```bash
# Python 3.9+，在仓库根目录执行
python3 -m pip install -e '.[analytics,test]'
```

基础任务管理、执行、验收和历史查询仅使用 Python 标准库，可直接运行脚本。
`analytics` 提供调度分析所需的 `psutil`，`test` 提供 pytest；缺少分析依赖不会影响基础命令。

### 初始化项目

```bash
python3 skill/scripts/cli.py init
```

### 配置模型路由

编辑 `.dual-ai-collab/model-routing.json`：

```json
{
  "model_routing": {
    "quick": {
      "adapter": "deepseek-cli",
      "reason": "快速任务使用轻量模型"
    },
    "normal": {
      "adapter": "claude-cli",
      "reason": "常规任务使用平衡模型"
    },
    "heavy": {
      "adapter": "codex",
      "reason": "复杂任务使用强大模型"
    }
  },
  "fallback_chain": {
    "deepseek-cli": ["claude-cli", "codex"],
    "claude-cli": ["codex"],
    "codex": []
  },
  "adapter_commands": {
    "deepseek-cli": ["/path/to/your-codex-compatible-wrapper"],
    "claude-cli": ["claude"],
    "codex": ["codex", "exec", "-"]
  }
}
```

### 基本使用

```bash
# 选择下一个任务
python3 skill/scripts/cli.py select

# 启动任务（使用适配器路由）
python3 skill/scripts/cli.py run start 001 "实现用户登录功能" --backend adapter

# 查看任务状态
python3 skill/scripts/cli.py run status 001

# 生成依赖图
python3 skill/scripts/cli.py visualize -o deps.mmd

# 查看调度建议
python3 skill/scripts/cli.py schedule

# 查看执行历史
python3 skill/scripts/cli.py history
```

## 📚 完整文档

详细使用教程请查看：**[TUTORIAL.md](./TUTORIAL.md)**

教程包含：
- 多模型适配器配置和使用
- 任务管理完整流程
- 依赖可视化和分析
- 智能调度系统
- 模板系统使用
- 故障排查指南
- 最佳实践建议

## 🏗️ 项目架构

```
dual-ai-collab/
├── skill/
│   ├── scripts/
│   │   ├── cli.py                    # 统一 CLI 入口
│   │   ├── task_manager.py           # 任务管理核心
│   │   ├── run_task.py               # 任务执行引擎
│   │   ├── model_router.py           # 模型路由器
│   │   ├── task_history.py           # 执行历史追踪
│   │   ├── task_visualization.py     # 依赖可视化
│   │   ├── task_scheduler.py         # 智能调度器
│   │   ├── task_templates.py         # 任务模板
│   │   └── task_analytics.py         # 分析工具 CLI
│   └── references/                   # 参考文档
├── tests/                            # 测试套件
├── .dual-ai-collab/                  # 项目数据目录
│   ├── config.json                   # 基础配置
│   ├── model-routing.json            # 模型路由配置
│   ├── logs/                         # 执行日志
│   ├── history/                      # 历史记录
│   └── checkpoints/                  # 检查点数据
├── planning/                         # 任务板和规范
│   ├── codex-tasks.md                # 任务板（Markdown 视图）
│   └── tasks.json                    # 任务数据（真相源）
├── README.md                         # 本文件
├── TUTORIAL.md                       # 完整使用教程
└── IMPROVEMENTS.md                   # 改进历史
```

## 🎯 主要功能模块

### 1. 多模型适配器路由

根据任务执行级别自动选择最优模型：

- **quick** (3分钟) → 轻量模型 (DeepSeek)
- **normal** (5分钟) → 平衡模型 (Claude)
- **heavy** (10分钟) → 强大模型 (Codex)

启动前按可用性和权限模式回退；执行已开始后的失败不会自动切换工具重跑。

### 2. 智能任务调度

基于多个因素的智能调度：

- 任务优先级权重
- 依赖关系深度
- 历史成功率
- 系统资源使用
- 预估执行时间

### 3. 任务分析可视化

- **依赖图生成**：Mermaid / Graphviz DOT 格式
- **关键路径分析**：识别最长依赖链
- **并行机会识别**：发现可并行执行的任务组
- **循环依赖检测**：自动检测并报告

### 4. 执行历史追踪

- 完整的任务执行记录
- 性能统计和趋势分析
- 适配器使用统计
- 成功率和失败分析

### 5. 任务模板系统

预定义模板：

- `feature` - 新功能开发
- `bugfix` - Bug 修复
- `refactor` - 代码重构
- `test` - 测试编写
- `docs` - 文档编写
- `optimization` - 性能优化

支持从需求文档自动生成任务板。

## 📊 使用示例

### 完整工作流

```bash
# 1. 初始化并配置
python3 skill/scripts/cli.py init

# 2. 从模板创建任务
python3 skill/scripts/cli.py templates create feature 001 --add \
  --var feature_name="用户登录API"

# 3. 生成依赖分析
python3 skill/scripts/cli.py analyze

# 4. 查看调度建议
python3 skill/scripts/cli.py schedule

# 5. 执行任务
python3 skill/scripts/cli.py select
python3 skill/scripts/cli.py run start 001 "实现登录API" --backend adapter

# 6. 监控和分析
python3 skill/scripts/cli.py run status 001
python3 skill/scripts/cli.py history
```

### 生成项目报告

```bash
# 依赖可视化
python3 skill/scripts/cli.py visualize -o docs/dependencies.mmd

# 依赖分析报告
python3 skill/scripts/cli.py analyze > docs/analysis.md

# 调度建议报告
python3 skill/scripts/cli.py schedule > docs/schedule.md

# 执行历史报告
python3 skill/scripts/cli.py history > docs/history.md

# 任务摘要
python3 skill/scripts/cli.py summary > docs/summary.md
```

## 🧪 测试

运行完整测试套件：

```bash
python3 -m pytest tests/ -v
```

测试覆盖：

- 适配器路由和回退机制
- 任务生命周期管理
- 配置加载和环境变量
- 错误处理和日志记录
- 进程状态检测
- 历史记录和统计

## 🔧 配置选项

### 基础配置 (`.dual-ai-collab/config.json`)

```json
{
  "default_backend": "adapter",
  "default_sandbox": "workspace-write",
  "log_level": "INFO",
  "enable_error_details": true
}
```

### 模型路由配置 (`.dual-ai-collab/model-routing.json`)

```json
{
  "model_routing": {
    "quick": {"adapter": "deepseek-cli", "reason": "..."},
    "normal": {"adapter": "claude-cli", "reason": "..."},
    "heavy": {"adapter": "codex", "reason": "..."}
  },
  "fallback_chain": {
    "deepseek-cli": ["claude-cli", "codex"],
    "claude-cli": ["codex"],
    "codex": []
  },
  "adapter_commands": {
    "deepseek-cli": ["/path/to/your-codex-compatible-wrapper"],
    "claude-cli": ["claude"],
    "codex": ["codex", "exec", "-"]
  }
}
```

### 环境变量

```bash
# 适配器配置
# 路由在 .dual-ai-collab/model-routing.json 中配置

# 默认设置
export DUAL_AI_DEFAULT_BACKEND=adapter
export DUAL_AI_DEFAULT_SANDBOX=workspace-write

# 日志级别
export DUAL_AI_LOG_LEVEL=DEBUG
```

## 📈 性能特性

- **缓存机制**：进程状态检测缓存（0.5秒 TTL）
- **两阶段检测**：轻量级 `os.kill` + 按需 `ps` 检查
- **僵尸进程处理**：自动检测和清理僵尸进程
- **资源感知**：根据系统资源动态调整任务选择
- **结构化日志**：高效的 JSON 日志格式

## 🛠️ 故障排查

### 适配器不可用

```bash
# 检查命令是否可用
which deepseek-cli claude codex

# 查看回退日志
grep "adapter_fallback" .dual-ai-collab/logs/task-*.log
```

### 任务卡住

```bash
# 检查状态
python3 skill/scripts/cli.py run status TASK_NUM

# 查看日志
tail -f .dual-ai-collab/logs/task-TASK_NUM.log

# 强制停止
python3 skill/scripts/cli.py run stop TASK_NUM
```

更多问题排查请参见 [TUTORIAL.md](./TUTORIAL.md#故障排查)。

## 📝 改进历史

详见 [IMPROVEMENTS.md](./IMPROVEMENTS.md)，包括：

- 僵尸进程检测修复
- 性能优化（缓存和两阶段检测）
- 结构化日志系统
- 多模型适配器路由
- 智能任务调度
- 任务分析可视化

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 🔗 相关链接

- [完整使用教程](./TUTORIAL.md)
- [改进历史](./IMPROVEMENTS.md)
- [任务板规范](./skill/references/task-board.md)

## 当前实现边界

- direct 和 adapter worker 会记录开始与结束历史，状态包括 `running`、`success`、`failed` 和 `stopped`。历史文件原子写入，每次执行使用独立编号。
- 历史中的 `success` 表示执行进程正常退出，不等同于验收通过，也不会自动将任务板标记为 `DONE`。应先运行 `verify run`，通过后再执行 `update TASK_NUM DONE`。
- 历史记录从 worker 启动时开始；强制杀死进程（如 SIGKILL）或主机断电后的历史状态恢复尚未实现。
- `templates create` 默认输出 JSON；加 `--add` 会校验并写入任务板。`select --smart` 与 `schedule` 共用依赖筛选和资源排序，默认 `select` 保留优先级排序。
- adapter 支持 Codex 协议和 Claude 原生协议；DeepSeek 等第三方 CLI 需显式配置兼容包装器。plugin 后端暂未实现。

## 新增命令与适配协议

```bash
# 只检查配置与可执行文件，不发起模型请求或检查登录
python3 skill/scripts/cli.py check-adapters

# 创建并入库；依赖必须存在，编号不能重复（001 与 1 视为同一编号）
python3 skill/scripts/cli.py templates create docs 002 --var topic=登录 --depends-on 001 --add

# 选择满足依赖与资源条件的任务；需要 analytics 可选依赖
python3 skill/scripts/cli.py select --smart
python3 skill/scripts/cli.py select --smart --parallel
```

任务统一使用 `id`，依赖写为 `"#001, #002"` 或 `"无"`；读取时兼容旧的 `task_num` 与列表依赖。
`--add` 使用与状态更新相同的文件锁，拒绝重复编号、自身依赖、不存在的依赖与循环依赖，并同步 Markdown。
模板中的验收条目是建议，仍需补充项目实际的可执行验收命令。

Claude 原生配置示例：

```json
{
  "model_routing": {"normal": {"adapter": "claude-cli"}},
  "adapter_commands": {"claude-cli": ["claude"]},
  "adapter_protocols": {"claude-cli": "claude"},
  "fallback_chain": {"claude-cli": []}
}
```

```bash
python3 skill/scripts/cli.py run start 001 "实现任务" --backend adapter --sandbox provider-default
```

`provider-default` 使用 Claude 的 `default` 权限模式，不等同于 Codex 的操作系统沙箱，也不会自动绕过权限提示。
Claude 调用使用 `--print`、`--output-format json`、`--json-schema`，并转换返回的 `structured_output`；错误、权限拒绝或无效输出会记为失败。
接口依据 [Claude 官方 CLI 文档](https://code.claude.com/docs/en/cli-reference) 和 [结构化输出文档](https://code.claude.com/docs/en/headless)。

需要 `workspace-write` / `read-only` 等 Codex 沙箱时，回退会跳过 Claude 原生协议；
使用 `provider-default` 时则跳过 Codex 协议。候选耗尽直接报错，不启动已知不可用的 worker。
`adapter_paths` 会同时作用于检测和实际启动。自定义包装器可显式设置 `adapter_protocols` 为 `codex`。
示例里的 `/path/to/your-codex-compatible-wrapper` 需要替换；未提供包装器时请移除该命令项，不假设存在统一的 DeepSeek CLI。

`check-adapters` 仅确认可执行文件存在；此次原生协议集成使用模拟 CLI 验证，真实账号与模型调用尚未验证。
