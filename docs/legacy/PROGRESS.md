# 开发进度记录（旧版）

> **旧版文档，不再更新。** 本文讲的是旧版 dual-ai-collab（代码在 `skill/`），其中的命令和路径不适用于当前的 foreman 技能。当前版本的说明见 [foreman/README.md](../../foreman/README.md)。

## 最近更新：2026-10-07

### 第三轮：可恢复会话后端

- 新增统一能力接口与 app-server 后端，旧 direct / adapter 后端保留，plugin 仍未实现。
- 支持 thread/start、thread/resume、turn/start、turn/steer、turn/interrupt；每轮关闭服务，下一轮恢复持久线程。
- 新增 run capabilities / continue / steer / events / complete --repair。
- 独立运行目录、原子状态写入、任务启动锁、进程异常状态协调；控制请求绑定 run/turn，不自动重放。
- 显式 --isolate 创建干净 Git HEAD 的独立 worktree，状态保存在原项目；不自动合并或清理代码。
- 验收报告与 run/thread/turn 关联，通过才更新 DONE，失败可在原线程修复一次。
- 真实 Codex 0.160.1 已验证：隔离执行 → 验收失败 → 相同线程修复 → 验收通过；验收脚本未改变，原仓库未生成产物。
- 当前不提供交互审批界面，额外权限/输入请求会拒绝并标记 blocked；Claude SDK 和 Windows 实机验证仍待后续。
- 验证：81 项 Python 测试、97 项 Shell 检查通过；编译与 diff 检查通过。
- 详细设计与操作说明：[session-backend.md](./session-backend.md)。

### 第二轮集成

- 统一存储、模板、调度和可视化的 id / 依赖格式，兼容旧 task_num 与列表依赖。
- 新增 templates create --add / --depends-on / --task-file，校验重复、自依赖、缺失依赖和循环，文件锁保护写入并同步 Markdown。
- select --smart 与 schedule 共用可执行候选和资源排序；--parallel 包含依赖已完成的 OPEN 任务。
- 修复空任务板调度、可视化逐字符解析依赖和循环递归问题。
- 新增 check-adapters、完整回退遍历、路径覆盖和配置校验；只在启动前回退，不重跑执行失败的任务。
- 支持 Claude 原生 print / JSON schema 协议，转换输出并处理错误与权限拒绝；Codex 与 Claude 权限模式显式区分。
- 验证：65 项 Python 测试、97 项 Shell 检查通过；编译与 diff 空白检查通过。
- 尚未验证真实模型请求；DeepSeek 等第三方 CLI 仍需用户提供明确协议的包装器。

### 稳定性修复

- 修复执行器读取任务板独立 `model` 字段，保留旧扩展字段兼容与命令行覆盖。
- 调度依赖按需加载；基础 CLI 无需 psutil，缺少依赖时调度命令返回安装提示。
- 新增 pyproject.toml，声明分析和测试可选依赖。
- direct / adapter worker 接入执行历史，涵盖成功、非零退出、异常和正常信号停止；文件使用原子写入和独立执行编号。
- 增加两个后端从执行到验收、手动完成任务的集成测试，以及无可选依赖启动测试。
- 第一轮待办中的 Claude 原生适配、调度接入与模板入库已在第二轮完成；强制终止后的历史恢复仍待实现。以下为此前功能记录。


### ✅ 已完成功能

#### 1. 多模型适配器路由系统
- **文件**: `skill/scripts/model_router.py`
- **功能**:
  - 根据任务执行级别（quick/normal/heavy）自动选择适配器
  - 支持自定义路由配置 `.dual-ai-collab/model-routing.json`
  - 适配器可用性检测和自动回退机制
  - 支持多级回退链（deepseek → claude → codex）
  - 灵活的命令构建系统

#### 2. 任务执行器（Adapter Backend）
- **文件**: `skill/scripts/run_task.py`
- **功能**:
  - 三种后端模式：direct、plugin、adapter
  - adapter backend 完整实现（`_start_adapter`, `cmd_worker_adapter`）
  - 后台进程管理和状态追踪
  - 结构化输出（JSON Schema 验证）
  - 信号处理和优雅终止

#### 3. 任务历史追踪系统
- **文件**: `skill/scripts/task_history.py`
- **功能**:
  - 记录每次任务执行的详细信息
  - 统计成功率、平均耗时、最快/最慢执行时间
  - 支持按任务编号查询历史
  - 生成 Markdown 格式历史报告
  - 持久化存储在 `.dual-ai-collab/history/`

#### 4. 任务依赖可视化
- **文件**: `skill/scripts/task_visualization.py`
- **功能**:
  - 生成 Mermaid 格式依赖图
  - 生成 Graphviz DOT 格式依赖图
  - 关键路径分析（最长依赖链）
  - 并行任务识别（可同时执行的任务）
  - 循环依赖检测
  - 依赖深度分析

#### 5. 智能任务调度系统
- **文件**: `skill/scripts/task_scheduler.py`
- **功能**:
  - 系统资源监控（CPU、内存、磁盘）
  - 任务资源需求估算
  - 基于多因素的优先级计算：
    - 基础优先级（P0/P1/P2/P3）
    - 依赖深度（被依赖越多越优先）
    - 执行级别加权
    - 历史成功率
  - 资源感知调度（内存/CPU 紧张时只执行轻量任务）
  - 剩余时间估算（串行/并行）
  - 多 worker 负载均衡

#### 6. 任务模板系统
- **文件**: `skill/scripts/task_templates.py`
- **功能**:
  - 6 种内置模板：feature、bugfix、refactor、test、docs、optimization
  - 模板变量替换
  - 从模板快速创建任务
  - 自动拆分大任务为子任务
  - 自动生成验收标准
  - 从需求文档生成任务板
  - 支持自定义模板保存和加载

#### 7. 统一分析 CLI
- **文件**: `skill/scripts/task_analytics.py`
- **命令**:
  - `history` - 执行历史报告
  - `visualize` - 依赖图生成（支持 mermaid/dot）
  - `analyze` - 依赖分析报告
  - `schedule` - 智能调度建议
  - `templates list` - 列出可用模板
  - `templates create` - 从模板创建任务
  - `generate` - 从需求文档生成任务板

#### 8. 完整文档
- **文件**:
  - `README.md` - 项目概览和快速开始
  - `TUTORIAL.md` - 完整使用教程（660+ 行）
  - 包含完整工作流示例、故障排查、最佳实践

### 🔧 技术实现要点

#### 多模型调用机制
```python
用户命令 → CLI
  → run_task.py (_start_adapter)
    → model_router.py (resolve_adapter_for_task)
      → 检查可用性 (validate_adapter_available)
        → 尝试回退 (get_fallback_adapter)
          → 构建命令 (build_adapter_command)
            → 启动子进程 (subprocess.Popen)
              → 适配器 CLI 工具 (claude/deepseek/codex)
```

#### 配置文件结构
```
.dual-ai-collab/
├── config.json              # 基础配置
├── model-routing.json       # 模型路由配置
├── logs/
│   ├── task-001.log        # 执行日志
│   ├── task-001.exit       # 退出码
│   └── history/            # 历史日志归档
├── history/
│   └── exec-*.json         # 执行历史记录
└── checkpoints/            # 检查点数据
```

### ⚠️ 待解决问题

#### 1. 适配器配置依赖
- **问题**: 项目依赖外部 AI CLI 工具（claude-cli、deepseek-cli 等）
- **影响**: 用户需要提前安装和配置这些工具
- **当前状态**: 文档已说明配置要求
- **下一步**:
  - 可以添加 `cli.py check-adapters` 命令检测已安装工具
  - 自动生成适配器配置建议

#### 2. 适配器命令接口标准化
- **问题**: 假设所有适配器都支持 `exec -C -s -m -c` 参数
- **影响**: 实际工具可能接口不一致
- **建议**:
  - 为每个适配器创建适配层脚本
  - 或在 `build_adapter_command` 中添加适配器特定逻辑

#### 3. Plugin Backend 未实现
- **文件**: `run_task.py:262-263, 407-408, 414-415`
- **状态**: 占位符，抛出 `CliError`
- **优先级**: 低（adapter backend 已满足需求）

### 📝 使用注意事项

#### 必需配置
1. 安装 Python 依赖：`pip install psutil`
2. 安装至少一个 AI CLI 工具（claude/deepseek/codex）
3. 配置 `.dual-ai-collab/model-routing.json` 使用实际安装的工具
4. 运行 `python3 skill/scripts/cli.py init` 初始化目录结构

#### 推荐工作流
```bash
# 1. 初始化
python3 skill/scripts/cli.py init

# 2. 配置模型路由（根据本地实际工具）
vim .dual-ai-collab/model-routing.json

# 3. 创建任务（从模板或手动）
python3 skill/scripts/cli.py templates create feature 001 --var feature_name="登录"

# 4. 分析依赖和调度
python3 skill/scripts/cli.py visualize -o deps.mmd
python3 skill/scripts/cli.py schedule

# 5. 执行任务
python3 skill/scripts/cli.py select  # 选择最优任务
python3 skill/scripts/cli.py run start 001 "实现登录" --backend adapter

# 6. 监控和分析
python3 skill/scripts/cli.py run status 001
python3 skill/scripts/cli.py history
```

### 🎯 下次继续开发建议

#### 优先级 1：适配器检测工具
```bash
python3 skill/scripts/cli.py check-adapters
# 输出：
# ✓ claude-cli: 可用 (/usr/local/bin/claude)
# ✗ deepseek-cli: 未安装
# ✗ codex: 未安装
#
# 建议配置：
# {
#   "model_routing": {
#     "quick": {"adapter": "claude-cli"},
#     "normal": {"adapter": "claude-cli"},
#     "heavy": {"adapter": "claude-cli"}
#   }
# }
```

#### 优先级 2：适配器包装脚本
为不同 CLI 工具创建统一接口包装器：
```bash
skill/scripts/adapters/
├── claude_adapter.py
├── deepseek_adapter.py
└── openai_adapter.py
```

#### 优先级 3：Web UI 界面
使用 Flask/FastAPI 创建简单的 Web 管理界面：
- 任务看板
- 依赖关系图可视化（集成 Mermaid.js）
- 执行历史图表（Chart.js）
- 实时日志查看

#### 优先级 4：CI/CD 集成
- GitHub Actions 工作流示例
- 自动运行任务验证
- 性能回归检测

### 📊 代码统计

- 新增文件：7 个
- 修改文件：2 个
- 代码行数：约 2,500 行（不含测试）
- 文档行数：约 1,100 行

### 🔗 相关文件清单

**核心功能模块**:
- `skill/scripts/model_router.py` (260 行)
- `skill/scripts/run_task.py` (881 行，修改）
- `skill/scripts/task_history.py` (新增)
- `skill/scripts/task_visualization.py` (新增)
- `skill/scripts/task_scheduler.py` (新增)
- `skill/scripts/task_templates.py` (新增)
- `skill/scripts/task_analytics.py` (新增)

**CLI 入口**:
- `skill/scripts/cli.py` (47 行，修改）

**配置和工具**:
- `skill/scripts/config.py` (97 行)
- `skill/scripts/tasks_store.py` (现有)
- `skill/scripts/structured_logging.py` (现有)

**文档**:
- `README.md` (完全重写)
- `TUTORIAL.md` (新增，662 行)
- `PROGRESS.md` (本文件)

---

**最后更新**: 2026-10-06
**状态**: 核心流程已实现，新增功能仍需集成和兼容性验证
**下次重点**: 适配器检测和配置简化
