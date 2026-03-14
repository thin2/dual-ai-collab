# Dual AI Collaboration Framework

> Claude（架构师/审计员）+ Codex（开发工程师）= 高效协作开发

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-2.1.0-blue.svg)](https://github.com/thin2/dual-ai-collab)

## 简介

双 AI 协作框架，让 Claude 和 Codex 分工协作：Claude 负责需求分析、架构设计、代码审计；Codex 负责代码实现。两者通过共享任务板（Task Board）异步协作，无需人工中转。

**v2.1.0 亮点**：支持多 Worker 并行执行、任务依赖管理、进度报告生成。完全自包含，只需复制一个 `.md` 文件即可开箱即用。

## 快速安装

### 方式一：一行命令安装（推荐）

```bash
mkdir -p ~/.claude/skills && curl -sSL https://raw.githubusercontent.com/thin2/dual-ai-collab/master/skill/dual-ai-collab.md -o ~/.claude/skills/dual-ai-collab.md
```

### 方式二：从仓库安装

```bash
git clone https://github.com/thin2/dual-ai-collab.git
cp dual-ai-collab/skill/dual-ai-collab.md ~/.claude/skills/
```

### 方式三：手动安装

```bash
mkdir -p ~/.claude/skills
# 将 skill/dual-ai-collab.md 复制到 ~/.claude/skills/
```

安装后重启 Claude Code（VSCode: Ctrl+Shift+P -> Reload Window）即可生效。

## 快速开始

1. 在 Claude Code 对话框中输入魔法词触发（见下方触发方式）
2. Claude 进行深入访谈（5-10 轮），明确需求
3. Claude 自动生成需求规范文档和任务板
4. 启动 Codex 自动开发（读取任务板逐一实现）
5. Claude 审计代码并验收，标记任务状态

## 工作流程

```
用户需求
   |
   v
Claude 深入访谈 (5-10 轮)
   |
   v
生成需求规范 + 任务板 (planning/codex-tasks.md)
   |
   v
Codex 读取任务 --> 实现代码 --> 更新状态为 DONE
   |
   v
Claude 审计代码 --> VERIFIED (通过) 或 REJECTED (需修复)
   |
   v
所有任务 VERIFIED --> 项目完成
```

## 触发方式

在 Claude Code 对话中输入以下任意内容均可触发：

- 魔法词：`双 AI 协作`、`dual ai`、`codex 协作`
- 命令：`/dual-ai-collab`
- 自然语言：`我想用双 AI 协作开发`、`启动 Codex 开发`、`开始深入访谈`

## 任务板格式

任务板保存在 `planning/codex-tasks.md`，每个任务包含：

- 优先级：P1（高）/ P2（中）/ P3（低）
- 状态：`OPEN` -> `IN_PROGRESS` -> `DONE` -> `VERIFIED` / `REJECTED`
- 任务描述、技术要求、验收标准、相关文件

示例：

```markdown
## 任务 #001: 实现用户登录功能

**优先级**: P1
**状态**: OPEN
**分配给**: Codex

### 验收标准
- [ ] 表单验证正确
- [ ] API 调用成功
- [ ] Token 正确存储
```

## 项目结构

```
dual-ai-collab/
├── skill/
│   ├── dual-ai-collab.md    # 核心 Skill 文件（唯一必需文件）
│   └── CHANGELOG.md         # 版本更新日志
├── tests/                    # 测试套件
│   └── run_all_tests.sh
├── planning/                 # 任务板和需求规范（运行时生成）
├── INSTALL-GUIDE.md         # 详细安装指南
├── INTERVIEW-GUIDE.md       # 访谈指南
├── skill-definition.md      # 架构设计文档
└── LICENSE
```

## 测试

```bash
bash tests/run_all_tests.sh
```

测试套件包含 64 个测试用例（7 个测试套件），覆盖任务领取、状态流转、依赖管理、并行任务识别、进度统计等核心功能。

## 依赖

- 必需：Claude Code（支持 Skills 功能的版本）
- 可选：Codex CLI（用于自动化开发模式）
  ```bash
  npm install -g @openai/codex-cli
  ```

## 文档

- [INSTALL-GUIDE.md](INSTALL-GUIDE.md) - 详细安装指南与故障排查
- [INTERVIEW-GUIDE.md](INTERVIEW-GUIDE.md) - 深入访谈指南
- [skill/CHANGELOG.md](skill/CHANGELOG.md) - 版本更新日志

## 许可证

MIT - 详见 [LICENSE](LICENSE)

## 致谢

- [Claude](https://www.anthropic.com/claude) - Anthropic 出品的 AI 助手
- [OpenAI Codex](https://openai.com/blog/openai-codex) - 代码生成模型
