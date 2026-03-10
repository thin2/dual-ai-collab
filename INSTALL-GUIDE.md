# Dual AI Collaboration Framework - 安装指南

v2.0.0 起，框架完全自包含于单个 `.md` 文件，无需外部脚本或配置文件。

---

## 快速安装

### 方式一：一行命令安装（推荐）

```bash
mkdir -p ~/.claude/skills && curl -sSL https://raw.githubusercontent.com/thin2/dual-ai-collab/master/skill/dual-ai-collab.md -o ~/.claude/skills/dual-ai-collab.md
```

执行后重启 Claude Code 即可使用，无需其他操作。

### 方式二：从仓库安装

```bash
git clone https://github.com/thin2/dual-ai-collab.git
cp dual-ai-collab/skill/dual-ai-collab.md ~/.claude/skills/
```

### 方式三：手动安装

```bash
# 1. 创建 skills 目录（如不存在）
mkdir -p ~/.claude/skills

# 2. 下载或复制 Skill 文件到该目录
# 文件来源：skill/dual-ai-collab.md
```

### 重启 Claude Code

安装 Skill 文件后需重启 Claude Code 生效：

- VSCode：Ctrl+Shift+P -> "Reload Window"
- 命令行：重新启动 `claude` 进程

---

## 验证安装

安装后，在 Claude Code 中输入以下任意内容，确认 Skill 已加载：

```
双 AI 协作
```

Claude 应响应并开始访谈流程。若无反应，参考下方故障排查。

手动验证文件是否就位：

```bash
ls -la ~/.claude/skills/dual-ai-collab.md
```

---

## 依赖说明

### 必需

- **Claude Code**：支持 Skills 功能的版本

### 可选

- **Codex CLI**：用于自动化开发模式（Codex 自动读取任务板并实现代码）

  ```bash
  npm install -g @openai/codex-cli
  ```

  若不安装 Codex CLI，仍可使用框架的访谈、规划、任务板管理和代码审计功能，只是无法启动自动化开发流程。

---

## 故障排查

### Skill 未生效

**症状**：输入魔法词后 Claude 无特殊反应。

**排查步骤**：

```bash
# 检查文件是否存在
ls -la ~/.claude/skills/dual-ai-collab.md

# 若文件不存在，重新安装
mkdir -p ~/.claude/skills
curl -sSL https://raw.githubusercontent.com/thin2/dual-ai-collab/master/skill/dual-ai-collab.md \
  -o ~/.claude/skills/dual-ai-collab.md

# 重启 Claude Code
```

### Codex CLI 未找到

**症状**：启动自动开发时提示 "codex: command not found"。

**解决方案**：

```bash
npm install -g @openai/codex-cli
codex --version  # 验证安装
```

### curl 下载失败

**症状**：curl 命令报错或文件为空。

**解决方案**：

```bash
# 检查网络连通性
curl -I https://raw.githubusercontent.com/thin2/dual-ai-collab/master/skill/dual-ai-collab.md

# 或直接从仓库安装
git clone https://github.com/thin2/dual-ai-collab.git
cp dual-ai-collab/skill/dual-ai-collab.md ~/.claude/skills/
```

---

## 更多文档

- [README.md](README.md) - 项目概览与快速开始
- [INTERVIEW-GUIDE.md](INTERVIEW-GUIDE.md) - 深入访谈指南
- [skill/CHANGELOG.md](skill/CHANGELOG.md) - 版本更新日志

---

**遇到问题？** 提交 Issue：https://github.com/thin2/dual-ai-collab/issues
