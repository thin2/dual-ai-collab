# Dual AI Collaboration

> Claude（规划者 / 审计者）+ Codex（执行者）= 轻量但可恢复的双 AI 协作开发流程

## 安装

```bash
# 方法一：克隆仓库（推荐，包含脚本和参考文档）
git clone https://github.com/thin2/dual-ai-collab.git
cp -r dual-ai-collab/skill ~/.claude/skills/dual-ai-collab

# 方法二：只安装核心 Skill 文件（脚本需手动补充）
mkdir -p ~/.claude/skills && curl -sSL https://raw.githubusercontent.com/thin2/dual-ai-collab/master/skill/dual-ai-collab.md -o ~/.claude/skills/dual-ai-collab.md
```

> 注意：方法二只下载主文件，skill 运行时依赖 `skill/scripts/` 和 `skill/references/` 目录。建议使用方法一完整安装。

## 使用

在 Claude Code 中输入以下任意内容触发：

- `双 AI 协作`、`dual ai`、`codex 协作`
- `/dual-ai-collab`

## 工作流程

```
用户需求 → Claude 深入访谈 → 生成需求规范 + 任务板
    → Claude 先审计规划，必要时由 Codex 补漏
    → 用户确认规划
    → Codex 异步开发（后台执行 + 活跃度检测 + 验证门控）
    → 三轮审计（Spec Compliance → Code Quality → Claude 综合判定）
    → 按需返工修复 → 项目完成
```

当前版本的关键原则：

- 规划文档必须先审计，再交给用户确认，确认后才进入开发。
- 前端相关任务必须先调用 `ui-ux-pro-max` 生成设计方案，再作为 Codex 的硬约束输入。
- 任务完成后自动运行验收标准中的可执行命令，验证通过才标记 DONE。
- 审计分三轮：规范符合性审查 → 代码质量审查 → Claude 综合判定。
- 卡死恢复优先做根因调查（systematic-debugging 思路），再决定重试或跳过。
- Skill 支持 checkpoint 恢复，长流程在对话压缩或中断后可以继续。
- 卡死检测支持任务级 `执行级别` 和 `卡死阈值`，避免长任务被过早判定失败。
- Shell 脚本为薄封装，核心逻辑由 Python 实现（并发安全、原子写入、状态机解析）。

## 项目结构

```
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
    ├── task_manager.py         # 任务管理核心（状态管理、解析、并发安全）
    ├── run_task.py             # 执行器抽象层（启动 codex exec、管理 run record）
    ├── verify_task.py          # 验收命令提取与执行
    ├── init_env.sh             # 环境初始化
    ├── check_checkpoint.sh     # checkpoint 恢复检查
    ├── write_checkpoint.sh     # checkpoint 写入/更新
    ├── select_next_task.sh     # 任务领取（支持 --parallel）
    ├── update_task_status.sh   # 状态更新
    ├── detect_stall.sh         # Codex 活跃度检测（支持任务级阈值）
    ├── run_task.sh             # 启动/查询/终止单个任务运行
    ├── verify_task.sh          # 提取/执行任务验收命令
    └── summarize_progress.sh   # 进度统计（支持 --report 生成报告）
tests/                          # 测试套件（101 个用例）
```

## 测试

```bash
bash tests/run_all_tests.sh
```

当前仓库测试套件已覆盖核心脚本行为，包括：

- 任务领取和依赖调度
- 状态流转和并发更新安全
- checkpoint 写入、恢复和损坏检测
- 卡死检测与任务级阈值
- 进度统计（含 FAILED 状态和报告生成）
- 验收命令提取与执行
- 执行器 status/stop/start
- 真实脚本黑盒验证

## 依赖

- 必需：Claude Code
- 可选：Codex CLI（`npm install -g @openai/codex-cli`）
- 前端增强：`ui-ux-pro-max` skill（前端任务推荐作为默认前置能力）
- 审计/调试增强：`superpowers@claude-plugins-official`（推荐用于 spec review、code quality review、systematic debugging）

## 许可证

MIT
