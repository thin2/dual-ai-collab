# 🎯 Dual AI Collaboration Skill 安装指南

## 📦 安装方式

### 方式 1：复制到 Claude 配置目录（推荐）

```bash
# 复制 skill 文件
cp skill/dual-ai-collab.md ~/.claude/skills/

# 重启 Claude Code 或重新加载配置
```

### 方式 2：使用 OMC Skill 管理器

```bash
# 如果你安装了 oh-my-claudecode
/skill add dual-ai-collab skill/dual-ai-collab.md
```

---

## 🪄 魔法词

安装完成后，你可以使用以下任意魔法词启动双 AI 协作流程：

### 主要魔法词

```
🤖 启动双 AI
```

```
🚀 开始协作
```

```
💬 深入访谈
```

### 关键词触发

也可以使用这些关键词：

```
双 AI 协作
```

```
dual ai
```

```
codex 协作
```

```
自动开发
```

```
访谈开发
```

### 别名

```
/dual-collab
```

```
/ai-pair
```

```
/codex-claude
```

---

## 🚀 使用示例

### 示例 1：使用魔法词

```
你：🤖 启动双 AI

Claude：好的！我会帮你启动双 AI 协作开发流程。

首先，让我了解一下你想开发什么功能。

[AskUserQuestion 工具弹出]
问题：你想开发什么功能？

请简要描述你的需求，例如：
- 用户认证系统
- 博客管理功能
- 电商购物车
- 数据分析仪表板
- 等等...

我会对你进行深入访谈，然后生成详细的需求规范和任务板。
```

### 示例 2：使用关键词

```
你：我想用双 AI 协作开发一个博客系统

Claude：好的！我会启动双 AI 协作流程。

[开始访谈...]
```

### 示例 3：使用别名

```
你：/dual-collab

Claude：好的！我会帮你启动双 AI 协作开发流程。

[开始访谈...]
```

---

## 📋 完整流程演示

### 第 1 步：启动

```
你：🤖 启动双 AI
```

### 第 2 步：回答初始问题

```
Claude：[AskUserQuestion]
问题：你想开发什么功能？

你：用户认证系统
```

### 第 3 步：深入访谈（5-10 轮）

```
Claude：[AskUserQuestion - 第 1 轮]
问题 1：用户认证的核心目标是什么？
选项：
A. 简单的用户名密码登录
B. 支持多种登录方式（邮箱、手机、第三方）
C. 企业级 SSO 集成
D. 其他（请说明）

你：B

问题 2：必须实现的核心功能有哪些？（多选）
选项：
A. 用户注册
B. 用户登录
C. 密码重置
D. 邮箱验证
E. 手机验证
F. 第三方登录（Google、GitHub 等）
G. 多因素认证（MFA）

你：A, B, C, D, F
```

```
Claude：[AskUserQuestion - 第 2 轮]
问题 1：后端技术栈偏好？
选项：
A. FastAPI (Python)
B. Express (Node.js)
C. Spring Boot (Java)
D. 其他（请说明）

你：A

问题 2：Token 管理策略？
选项：
A. JWT（无状态）
B. Session（有状态）
C. JWT + Refresh Token
D. OAuth 2.0

你：C
```

```
Claude：[AskUserQuestion - 第 3 轮]
问题 1：密码安全策略？
选项：
A. 基础加密（bcrypt）
B. 密码强度要求（长度、复杂度）
C. 密码定期更换
D. 多因素认证（MFA）
E. 所有以上

你：A, B

问题 2：如何防止暴力破解？
选项：
A. 登录失败次数限制
B. 验证码（CAPTCHA）
C. IP 黑名单
D. 账户临时锁定
E. 所有以上

你：A, B, D
```

[继续 2-7 轮访谈...]

### 第 4 步：生成文档

```
Claude：✅ 访谈完成！

现在我会：
1. 生成详细的需求规范文档
2. 根据规范拆分任务
3. 写入任务板

请稍等...

[生成 planning/specs/20260306-140000-用户认证系统.md]
[生成 planning/codex-tasks.md]

✅ 需求规范和任务板已创建完成！

📄 需求规范文档：planning/specs/20260306-140000-用户认证系统.md
📋 任务板：planning/codex-tasks.md
📊 总任务数：8 个
⏱️  预计总工时：16 小时

现在可以启动 Codex Worker 开始自动开发：

方式 1：在 tmux 中启动（推荐）
bash scripts/start-codex.sh -t

方式 2：后台启动
bash scripts/start-codex.sh -b

方式 3：前台启动（测试）
bash scripts/start-codex.sh -f
```

### 第 5 步：启动 Codex

```bash
bash scripts/start-codex.sh -t
```

### 第 6 步：监控进度

```bash
# 查看任务状态
grep "状态:" planning/codex-tasks.md

# 查看日志
bash scripts/start-codex.sh -l
```

### 第 7 步：审计验收

```
你：任务完成了，请帮我审计

Claude：好的，我来审计已完成的任务。

[审计代码...]
[生成审计报告...]
[更新任务状态...]

✅ 审计完成！
- 任务 #001: VERIFIED (评分: 95/100)
- 任务 #002: VERIFIED (评分: 92/100)
- 任务 #003: REJECTED (需要添加输入验证)
```

---

## 🎯 Skill 特性

### 自动化流程

1. ✅ **自动询问需求**：使用 AskUserQuestion 询问用户需求
2. ✅ **深入访谈**：5-10 轮深入访谈，涵盖所有关键维度
3. ✅ **生成规范文档**：详细的需求规范文档（10 个章节）
4. ✅ **拆分任务**：根据规范自动拆分任务
5. ✅ **写入任务板**：格式化的任务板，可直接使用

### 访谈质量保证

- ✅ **非显而易见**：不问显而易见的问题
- ✅ **深入细节**：问具体的实现细节
- ✅ **权衡取舍**：帮助用户做出明智的选择
- ✅ **边界情况**：考虑各种边界情况
- ✅ **用户体验**：关注用户体验细节

### 文档质量保证

- ✅ **结构完整**：10 个标准章节
- ✅ **内容详细**：每个章节都有详细内容
- ✅ **可追溯**：任务板引用规范文档
- ✅ **可执行**：任务拆分合理，可直接开发

---

## 🔧 配置选项

### 自定义魔法词

如果你想添加自己的魔法词，编辑 `skill/dual-ai-collab.md`：

```yaml
triggers:
  magic_words:
    - "🤖 启动双 AI"
    - "🚀 开始协作"
    - "💬 深入访谈"
    - "你的自定义魔法词"  # 添加这里
```

### 自定义访谈维度

如果你想调整访谈维度，编辑 skill 文件中的"访谈维度"部分。

---

## 📚 相关文档

- **[QUICKSTART.md](../QUICKSTART.md)** - 5 分钟快速上手
- **[INTERVIEW-GUIDE.md](../INTERVIEW-GUIDE.md)** - 完整访谈指南
- **[README-USAGE.md](../README-USAGE.md)** - 日常使用流程
- **[README.md](../README.md)** - 项目主文档

---

## 💡 使用技巧

### 技巧 1：准备好你的需求

在启动前，先想清楚：
- 你想开发什么功能？
- 大概的技术栈偏好？
- 有什么特殊要求？

### 技巧 2：详细回答问题

访谈时，尽量详细回答：
- 不要只选 A/B/C，可以补充说明
- 如果有特殊需求，选择"其他"并说明
- 如果不确定，可以问 Claude 建议

### 技巧 3：查看生成的文档

访谈完成后，先查看生成的规范文档：
```bash
cat planning/specs/最新的文件.md
```

如果有遗漏或不满意，可以要求 Claude 修改。

### 技巧 4：分阶段开发

如果任务很多，可以分阶段：
```bash
# 只保留 P1 任务为 OPEN
# 将 P2/P3 任务改为 BLOCKED

# 等 P1 完成后，再开启 P2
```

---

## 🎉 开始使用

现在就试试吧！

```
🤖 启动双 AI
```

或者

```
我想用双 AI 协作开发一个 [你的功能]
```

祝你使用愉快！🚀
