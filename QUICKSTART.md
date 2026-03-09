# 🤖 Dual AI Collaboration Framework - 快速开始

## 📖 5 分钟快速上手

### 第 1 步：准备环境

```bash
# 1. 确保已安装必要工具
which codex   # Codex CLI
which tmux    # tmux（可选，用于后台运行）

# 2. 克隆项目
cd ~/projects
git clone https://github.com/yourusername/dual-ai-collab.git
cd dual-ai-collab

# 3. 查看项目结构
tree -L 2
```

### 第 2 步：提出需求

告诉 Claude 你想开发什么：

```
我想开发一个用户认证系统，请对我进行深入访谈
```

### 第 3 步：回答访谈问题

Claude 会问你一系列深入的问题，例如：

```
问题 1：用户认证的核心目标是什么？
选项：
A. 简单的用户名密码登录
B. 支持多种登录方式（邮箱、手机、第三方）
C. 企业级 SSO 集成
D. 其他

问题 2：密码安全策略？
选项：
A. 基础加密（bcrypt）
B. 密码强度要求 + 定期更换
C. 多因素认证（MFA）
D. 所有以上
```

### 第 4 步：Claude 生成规范和任务

访谈完成后，Claude 会自动：

1. **生成需求规范**：`planning/specs/20260306-用户认证系统.md`
2. **拆分任务**：写入 `planning/codex-tasks.md`

### 第 5 步：启动 Codex Worker

```bash
# 在 tmux 中启动（推荐）
bash scripts/start-codex.sh -t

# 或者后台启动
bash scripts/start-codex.sh -b
```

### 第 6 步：监控进度

```bash
# 查看任务状态
grep "状态:" planning/codex-tasks.md

# 查看日志
bash scripts/start-codex.sh -l

# 或者实时监控
watch -n 5 'grep -E "\*\*状态\*\*:|状态:" planning/codex-tasks.md'
```

### 第 7 步：审计代码

当任务完成（状态变为 DONE）时：

```bash
# 查看完成的任务
grep -A 20 -E "\*\*状态\*\*: DONE|状态: DONE" planning/codex-tasks.md

# 审计代码
cat [相关文件]

# 更新状态
sed -i 's/\*\*状态\*\*: DONE/\*\*状态\*\*: VERIFIED/' planning/codex-tasks.md
```

---

## 🎯 完整示例

### 示例：开发博客系统

```bash
# 1. 提出需求
"我想开发一个博客系统，请对我进行深入访谈"

# 2. 回答 Claude 的访谈问题（5-10 轮）
# Claude 会问：
# - 博客的核心功能？
# - 技术栈偏好？
# - 用户体验要求？
# - 数据存储方式？
# - 权限控制？
# - 等等...

# 3. Claude 生成规范和任务
# 文件：planning/specs/20260306-140000-博客系统.md
# 任务：planning/codex-tasks.md（包含 10+ 个任务）

# 4. 启动 Codex
bash scripts/start-codex.sh -t

# 5. 监控进度（每 2 小时检查一次）
watch -n 7200 'grep -cE "\*\*状态\*\*: DONE|状态: DONE" planning/codex-tasks.md'

# 6. 审计和验收
# 当任务完成时，审计代码并更新状态

# 7. 完成！
echo "✅ 博客系统开发完成"
```

---

## 📚 详细文档

- **访谈指南**：[INTERVIEW-GUIDE.md](INTERVIEW-GUIDE.md) - 如何进行深入访谈
- **使用指南**：[README-USAGE.md](README-USAGE.md) - 日常使用流程
- **集成方案**：[INTEGRATION.md](INTEGRATION.md) - 与 OMC 集成
- **主文档**：[README.md](README.md) - 项目概述

---

## 💡 核心优势

### 传统开发 vs 双 AI 协作

| 维度 | 传统开发 | 双 AI 协作 |
|------|---------|-----------|
| **需求分析** | 自己思考，容易遗漏 | Claude 深入访谈，全面覆盖 |
| **任务规划** | 手动拆分，耗时费力 | 自动拆分，合理有序 |
| **代码实现** | 自己编写，速度慢 | Codex 自动开发，速度快 |
| **代码审计** | 自己检查，容易疏忽 | Claude 严格审计，质量高 |
| **文档记录** | 经常忘记写 | 自动生成规范文档 |
| **进度追踪** | 难以追踪 | 任务板实时更新 |

### 时间对比

**开发一个用户认证系统**：

- **传统方式**：
  - 需求分析：2 小时
  - 任务规划：1 小时
  - 代码实现：8 小时
  - 代码审查：2 小时
  - **总计：13 小时**

- **双 AI 协作**：
  - 需求访谈：30 分钟（回答问题）
  - 任务规划：自动（5 分钟）
  - 代码实现：自动（2 小时，Codex 并行）
  - 代码审计：1 小时（Claude）
  - **总计：4 小时（你的实际工作时间）**

**效率提升：3 倍以上！**

---

## 🎉 开始使用

现在就试试吧！

```bash
cd ~/projects/dual-ai-collab

# 告诉 Claude
"我想开发 [你的功能]，请对我进行深入访谈"
```

祝你使用愉快！🚀
