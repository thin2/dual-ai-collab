# Dual AI Collaboration Framework - 安装指南

## 🚀 快速安装

### 方法一：一键安装（推荐）

```bash
# 1. 克隆仓库
git clone <你的仓库地址>
cd dual-ai-collab

# 2. 运行安装脚本
bash install.sh
```

安装脚本会自动：
- ✅ 安装 Skill 到 `~/.claude/skills/`
- ✅ 创建配置文件 `.dual-ai-collab.yml`
- ✅ 创建必要的目录结构
- ✅ 设置脚本权限
- ✅ 检查依赖（Codex CLI、tmux）
- ✅ 运行环境检查

---

### 方法二：手动安装 Skill

如果你只想安装 Skill（不需要完整框架）：

```bash
# 1. 创建 skills 目录（如果不存在）
mkdir -p ~/.claude/skills

# 2. 复制 Skill 文件
cp skill/dual-ai-collab.md ~/.claude/skills/

# 3. 重启 Claude Code
# 在 VSCode 中按 Ctrl+Shift+P，输入 "Reload Window"
```

---

## 📋 Skill 使用方法

安装完成后，在 Claude Code 中使用以下方式触发：

### 方式一：魔法词（推荐）

直接输入以下任意魔法词：

```
🤖 启动双 AI
🚀 开始协作
💬 深入访谈
双 AI 协作
dual ai
codex 协作
```

### 方式二：关键词

在对话中包含以下关键词：

```
"我想用双 AI 协作"
"启动 Codex 开发"
"开始深入访谈"
```

### 方式三：Slash 命令

```
/dual-ai-collab
```

---

## 🎯 使用示例

### 示例 1：快速开始

```
用户: 🤖 启动双 AI

Claude: 我会帮你启动双 AI 协作模式...
[进行 5-10 轮深入访谈]
[生成需求规范和任务板]
[询问是否启动 Codex 自动开发]
```

### 示例 2：深入访谈

```
用户: 💬 深入访谈

Claude: 我会对你的需求进行深入访谈...
[询问项目背景、目标用户、核心功能等]
[生成详细的需求文档]
```

### 示例 3：查看状态

```
用户: /dual-ai-collab status

Claude: [显示任务板状态、日志、进度等]
```

---

## 🔧 依赖检查

### 必需依赖

1. **Codex CLI**
   ```bash
   # 检查是否安装
   codex --version

   # 如果未安装，请访问：
   # https://github.com/openai/codex-cli
   ```

2. **Claude Code**
   - 确保已安装 Claude Code VSCode 扩展
   - 版本要求：支持 Skill 功能的版本

### 可选依赖

1. **tmux**（推荐，用于后台运行）
   ```bash
   # Ubuntu/Debian
   sudo apt install tmux

   # macOS
   brew install tmux
   ```

---

## 📁 目录结构

安装后的目录结构：

```
dual-ai-collab/
├── .dual-ai-collab.yml      # 配置文件
├── planning/                 # 任务板目录
│   └── codex-tasks.md       # 任务板模板
├── scripts/                  # 脚本目录
│   ├── codex-auto-worker.sh # Codex 自动工作脚本
│   ├── start-codex.sh       # 启动脚本
│   └── claude-interview.sh  # 深入访谈脚本
├── skill/                    # Skill 文件
│   └── dual-ai-collab.md    # Skill 定义
└── .dual-ai-collab/         # 运行时目录（自动创建）
    ├── logs/                # 日志目录
    └── checkpoints/         # 检查点目录
```

---

## ✅ 验证安装

运行环境检查脚本：

```bash
bash check-env.sh
```

检查项目：
1. ✅ Skill 是否安装到 `~/.claude/skills/`
2. ✅ 配置文件是否存在
3. ✅ .gitignore 是否配置
4. ✅ 日志目录是否创建
5. ✅ Codex CLI 是否安装
6. ✅ tmux 是否安装（可选）
7. ✅ 脚本权限是否正确
8. ✅ 任务板模板是否存在

---

## 🐛 故障排查

### 问题 1：Skill 未生效

**症状**：输入魔法词后没有反应

**解决方案**：
```bash
# 1. 检查 Skill 是否安装
ls -la ~/.claude/skills/dual-ai-collab.md

# 2. 重新安装
cp skill/dual-ai-collab.md ~/.claude/skills/

# 3. 重启 Claude Code
# VSCode: Ctrl+Shift+P -> "Reload Window"
```

### 问题 2：Codex CLI 未安装

**症状**：运行脚本时提示 "codex: command not found"

**解决方案**：
```bash
# 安装 Codex CLI
npm install -g @openai/codex-cli

# 或访问官方文档
# https://github.com/openai/codex-cli
```

### 问题 3：权限错误

**症状**：运行脚本时提示 "Permission denied"

**解决方案**：
```bash
# 设置脚本权限
chmod +x scripts/*.sh
chmod +x check-env.sh
chmod +x install.sh
```

---

## 📚 更多文档

- [QUICKSTART.md](QUICKSTART.md) - 5 分钟快速开始
- [README-USAGE.md](README-USAGE.md) - 日常使用指南
- [INTERVIEW-GUIDE.md](INTERVIEW-GUIDE.md) - 深入访谈指南
- [skill/README.md](skill/README.md) - Skill 详细说明

---

## 💡 提示

1. **首次使用**：建议先运行 `bash install.sh` 完成完整安装
2. **环境检查**：遇到问题时先运行 `bash check-env.sh`
3. **日志查看**：出错时查看 `.dual-ai-collab/logs/worker.log`
4. **配置调整**：根据需要修改 `.dual-ai-collab.yml`

---

**安装遇到问题？** 查看 [故障排查](#-故障排查) 或提交 Issue
