# Dual AI Collaboration Skill

这是一个 OMC Skill，用于启动双 AI 协作开发流程。

## 快速安装

```bash
# 复制到 Claude 配置目录
cp dual-ai-collab.md ~/.claude/skills/

# 重启 Claude Code
```

## 使用方法

使用任意魔法词启动：

```
🤖 启动双 AI
```

或

```
🚀 开始协作
```

或

```
💬 深入访谈
```

## 详细文档

- [安装指南](INSTALL.md)
- [项目主页](../README.md)

## 工作流程

1. 使用魔法词启动
2. Claude 询问你的需求
3. 进行 5-10 轮深入访谈
4. 生成需求规范文档
5. 拆分任务并写入任务板
6. 启动 Codex Worker 自动开发
7. Claude 审计验收

## 特性

- ✅ 自动询问需求
- ✅ 深入访谈（非显而易见的问题）
- ✅ 生成详细规范文档
- ✅ 自动拆分任务
- ✅ 与 Codex Worker 无缝集成

## 示例

```
你：🤖 启动双 AI

Claude：好的！我会帮你启动双 AI 协作开发流程。
       首先，让我了解一下你想开发什么功能。

[开始访谈...]
```

详见 [INSTALL.md](INSTALL.md)
