# 故障排查

## 问题 1：Codex CLI 未安装

```bash
npm install -g @openai/codex-cli
```

## 问题 2：任务一直处于 IN_PROGRESS

回退所有 IN_PROGRESS 任务：
```bash
sed -i 's/\*\*状态\*\*: IN_PROGRESS/\*\*状态\*\*: OPEN/g' planning/codex-tasks.md
```

## 问题 3：对话压缩后流程中断

不需要手动处理。重新触发 Skill（说"继续开发"或"双 AI 协作"），会自动检测 checkpoint 并恢复：
```bash
cat .dual-ai-collab/checkpoints/state.json
```

## 问题 4：Codex 卡死（无响应）

活跃度检测会自动发现并处理。手动检查：
```bash
# 查看 Codex 进程
pgrep -f "codex exec" && echo "进程存在" || echo "无 Codex 进程"

# 查看最近文件变动
find . -name '*.py' -o -name '*.js' -o -name '*.ts' -not -path './node_modules/*' -newer .dual-ai-collab/logs/pids.log 2>/dev/null | head -10

# 手动 kill 卡死的 Codex
pkill -f "codex exec"
```

## 问题 5：流程完成后想清理状态

```bash
rm -f .dual-ai-collab/checkpoints/state.json
```

## 问题 6：任务板格式错误

使用 Read 工具检查格式，用 Edit 工具修复。
