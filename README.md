# Dual AI Collaboration

> Claude（规划者 / 审计者）+ Codex（执行者）= 轻量但可恢复的双 AI 协作开发流程

## 安装

```bash
# 方法一：克隆仓库后使用跨平台安装器（推荐）
git clone https://github.com/thin2/dual-ai-collab.git
cd dual-ai-collab
python install.py
```

Windows 用户可直接运行：

```bat
install.cmd
```

如果你只想手动复制文件，正确目录结构应为：

```bash
mkdir -p ~/.claude/skills/dual-ai-collab
cp dual-ai-collab/skill/dual-ai-collab.md ~/.claude/skills/dual-ai-collab/
cp -r dual-ai-collab/skill/scripts ~/.claude/skills/dual-ai-collab/
cp -r dual-ai-collab/skill/references ~/.claude/skills/dual-ai-collab/
```

不要执行下面这种复制方式，它会多出一层 `skill/` 目录：

```bash
cp -r dual-ai-collab/skill ~/.claude/skills/dual-ai-collab
```

方法二：只下载主文件（不推荐，缺 `scripts/` 和 `references/`）

```bash
mkdir -p ~/.claude/skills
curl -sSL https://raw.githubusercontent.com/thin2/dual-ai-collab/master/skill/dual-ai-collab.md -o ~/.claude/skills/dual-ai-collab.md
```

> 注意：方法二只下载主文件，skill 运行时仍依赖 `scripts/` 和 `references/`。建议使用 `python install.py` 完整安装。

## 当前状态

当前 skill 已可实际使用：

- 默认 `direct` backend：通过 `codex` 后台执行任务
- 无 `codex` 时：可切换到 `Claude-only`
- 新增 `adapter` backend：可通过本地 CLI 适配器执行，当前内置 `claude-cli`

## 使用

在 Claude Code 中输入以下任意内容触发：

- `双 AI 协作`、`dual ai`、`codex 协作`
- `/dual-ai-collab`

## 纯规划技能 (Planning-Only)

如果你只需要规划能力（访谈、规格生成、任务板、审计），不需要执行：

```bash
python install.py --skill planning
```

触发词：`规划`、`planning`、`需求分析`、`任务规划`

产出物（specs、tasks.json、codex-tasks.md）与 dual-ai-collab 格式兼容，可以随时切换到 dual-ai-collab 继续执行。

安装两个技能：

```bash
python install.py --skill both
```

## 工作流程

```
用户需求 → Claude 深入访谈 → 生成需求规范 + 任务板
    → Claude 先审计规划，必要时由 Codex 补漏
    → 用户确认规划
    → Codex 异步开发（后台执行 + 活跃度检测 + 验证门控）
    → 分级审计（轻量核验 / 标准审计 / 完整审计）
    → 按需返工修复 → 项目完成
```

当前版本的关键原则：

- 规划文档必须先审计，再交给用户确认，确认后才进入开发。
- 前端任务按复杂度分级：新页面/复杂交互先做设计，小修小补可直接实现。
- 任务完成后自动运行验收标准中的可执行命令，验证通过才标记 DONE。
- 审计按复杂度分级：高风险任务走完整审计，低风险任务走轻量核验。
- 卡死恢复优先做根因调查（systematic-debugging 思路），再决定重试或跳过。
- Skill 支持 checkpoint 恢复，长流程在对话压缩或中断后可以继续。
- 卡死检测支持任务级 `执行级别` 和 `卡死阈值`，避免长任务被过早判定失败。
- Shell 脚本为薄封装，核心逻辑由 Python 实现（并发安全、原子写入、状态机解析）。
- 当 Codex CLI 不可用时，流程会降级为 `Claude-only` 模式，由 Claude 直接按任务板执行和验证。
- 执行器支持 `direct` 和 `adapter` 两种后台模型；`adapter` 默认可接 `claude-cli`。
- 访谈按复杂度分级：简单需求 2-3 轮，中等需求 4-6 轮，复杂需求 6-10 轮。

## 跨平台使用

仓库现在同时支持 Linux/macOS 和 Windows，但推荐把 `Python` 入口视为正式接口：

```bash
# Linux / macOS / Windows（PowerShell、cmd 都可）
python skill/scripts/cli.py init
python skill/scripts/cli.py select
python skill/scripts/cli.py update 001 DONE
python skill/scripts/cli.py run start 001 "实现任务"
python skill/scripts/cli.py run start 001 "实现任务" --backend adapter
python skill/scripts/cli.py verify run 001
```

如果你想显式使用 `adapter` backend：

```bash
# Linux / macOS
export DUAL_AI_ADAPTER=claude-cli
python skill/scripts/cli.py run start 001 "实现任务" --backend adapter
```

```powershell
# PowerShell
$env:DUAL_AI_ADAPTER="claude-cli"
python skill/scripts/cli.py run start 001 "实现任务" --backend adapter
```

也可使用自定义命令适配器：

```bash
# Linux / macOS
export DUAL_AI_ADAPTER=custom-json
export DUAL_AI_CUSTOM_CMD_JSON='["my-runner", "--prompt", "{prompt}"]'
python skill/scripts/cli.py run start 001 "实现任务" --backend adapter
```

```powershell
# PowerShell
$env:DUAL_AI_ADAPTER="custom-json"
$env:DUAL_AI_CUSTOM_CMD_JSON='["my-runner", "--prompt", "{prompt}"]'
python skill/scripts/cli.py run start 001 "实现任务" --backend adapter
```

兼容入口说明：

- Linux/macOS：现有 `skill/scripts/*.sh` 仍然可用
- Windows：新增 `skill/scripts/*.cmd`，也可直接运行 `skill\\scripts\\cli.cmd`
- 如果验收命令显式写成 `bash xxx.sh`，Windows 需要安装 Git Bash 或 WSL；更推荐把任务板里的验收命令写成 `python`、`npm`、`pytest` 这类跨平台命令

## 项目结构

```
install.py                       # 跨平台安装器（支持 --skill dual/planning/both）
install.cmd                      # Windows 安装入口
skill/
├── dual-ai-collab.md           # 核心 Skill 文件（安装到 ~/.claude/skills/）
├── references/                 # 参考文档（按需加载）
│   ├── interview.md            # 访谈策略和规范模板
│   ├── task-board.md           # 任务板格式规范
│   ├── audit.md                # 审计规则和报告格式
│   ├── prompt-templates.md     # 阶段化提示词模板
│   ├── recovery.md             # 对话压缩/中断后的恢复指引
│   └── troubleshooting.md      # 故障排查
└── scripts/                    # 辅助脚本
    ├── cli.py                  # 跨平台统一入口
    ├── platform_utils.py       # 跨平台锁、进程、shell 工具
    ├── task_manager.py         # 任务管理核心（状态管理、解析、并发安全）
    ├── run_task.py             # 执行器抽象层（direct / adapter、run record、后台 worker）
    ├── verify_task.py          # 验收命令提取与执行
    ├── init_env.sh             # 环境初始化
    ├── init_env.cmd            # Windows 包装入口
    ├── check_checkpoint.sh     # checkpoint 恢复检查
    ├── write_checkpoint.sh     # checkpoint 写入/更新
    ├── select_next_task.sh     # 任务领取（支持 --parallel）
    ├── update_task_status.sh   # 状态更新
    ├── detect_stall.sh         # Codex 活跃度检测（支持任务级阈值）
    ├── run_task.sh             # 启动/查询/终止单个任务运行
    ├── verify_task.sh          # 提取/执行任务验收命令
    └── summarize_progress.sh   # 进度统计（支持 --report 生成报告）
planning-skill/                  # 纯规划技能（独立安装）
├── planning-collab.md          # 规划 Skill 文件
├── references/                 # 规划专用参考文档
│   ├── interview.md
│   ├── task-board.md
│   └── prompt-templates.md
└── scripts/                    # 规划专用脚本（无执行器）
    ├── cli.py
    ├── task_manager.py
    ├── tasks_store.py
    └── platform_utils.py
tests/                          # Shell 黑盒测试 + Python 单元测试
```

## 测试

```bash
bash tests/run_all_tests.sh
```

也可以只运行 Python 单元测试：

```bash
python tests/run_python_tests.py
```

> 当前完整回归仍包含 shell 黑盒测试，因此 Windows 上更适合先运行 `python tests/run_python_tests.py`，或做 Python smoke test，例如 `python skill/scripts/cli.py init`、`python skill/scripts/cli.py summary`。如果需要完整 shell 回归，建议在 Git Bash、WSL 或 CI 的 Linux runner 中执行。

当前仓库测试主要覆盖以下核心行为：

- 任务领取和依赖调度
- 状态流转和并发更新安全
- checkpoint 写入、恢复和损坏检测
- 卡死检测与任务级阈值
- 进度统计（含 FAILED 状态和报告生成）
- 验收命令提取与执行
- 执行器 status/stop/start
- 真实脚本黑盒验证
- 安装器、任务存储、运行状态和 CLI 的 Python 单元测试

## 依赖

- 必需：Claude Code
- 自动开发增强：Codex CLI（`npm install -g @openai/codex-cli`）
  - 安装后可使用后台异步执行、并行 worker、run record 管理
  - 未安装时仍可使用 `Claude-only` 模式完成访谈、规划、实现和验证，但执行会改为同步、不可并行
- 可选 adapter：Claude CLI（`claude`）
  - 当 `DUAL_AI_ADAPTER=claude-cli` 且使用 `--backend adapter` 时启用
  - 适合保留现有后台 worker / stall 检测 / run record 流程，但不依赖 `codex`
- 可选自定义 adapter：
  - 设置 `DUAL_AI_ADAPTER=custom-json`
  - 设置 `DUAL_AI_CUSTOM_CMD_JSON` 为 JSON argv 数组
  - 若数组中包含 `{prompt}`，启动时会直接替换；否则 prompt 会通过 stdin 传入
- 前端增强：`ui-ux-pro-max` skill（前端任务推荐作为默认前置能力）
- 审计/调试增强：`superpowers@claude-plugins-official`（推荐用于 spec review、code quality review、systematic debugging）

## 许可证

MIT
