# Dual AI Collaboration

> Claude（架构师/审计员）+ Codex（开发工程师）= 高效协作开发

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
    → 用户审查规划 → Codex 异步开发（后台执行 + 活跃度检测）
    → 双重审计（Codex + Claude）→ 自动修复循环 → 项目完成
```

## 项目结构

```
skill/
├── dual-ai-collab.md           # 核心 Skill 文件（安装到 ~/.claude/skills/）
├── references/                 # 参考文档（按需加载）
│   ├── interview.md            # 访谈策略和规范模板
│   ├── task-board.md           # 任务板格式规范
│   ├── audit.md                # 审计规则和报告格式
│   └── troubleshooting.md      # 故障排查
└── scripts/                    # 辅助脚本
    ├── init_env.sh             # 环境初始化
    ├── check_checkpoint.sh     # checkpoint 恢复检查
    ├── write_checkpoint.sh     # checkpoint 写入/更新
    ├── select_next_task.sh     # 任务领取（支持 --parallel）
    ├── update_task_status.sh   # 状态更新
    ├── detect_stall.sh         # Codex 活跃度检测
    └── summarize_progress.sh   # 进度统计
tests/                          # 测试套件
```

## 测试

```bash
bash tests/run_all_tests.sh
```

## 依赖

- 必需：Claude Code
- 可选：Codex CLI（`npm install -g @openai/codex-cli`）

## 许可证

MIT
