# 🤖 Codex 自动化工作脚本使用指南

## 📋 快速开始

### 1. 准备任务板

创建任务板文件 `planning/codex-tasks.md`：

```bash
mkdir -p planning
cat > planning/codex-tasks.md << 'EOF'
# Codex 任务板

## 任务 #001: 创建 Hello World 程序

**优先级**: P1
**状态**: OPEN
**分配给**: Codex
**创建时间**: 2026-03-06
**预计工时**: 0.5小时

### 任务描述
创建一个简单的 Python Hello World 程序

### 技术要求
- 使用 Python 3
- 文件名: hello.py
- 输出: "Hello, World!"

### 验收标准
- [ ] 文件创建成功
- [ ] 代码可以运行
- [ ] 输出正确

### 相关文件
- `hello.py`

---
EOF
```

### 2. 启动 Codex Worker

有三种启动方式：

#### 方式 A: 前台运行（推荐测试时使用）

```bash
cd /home/hn/projects/dual-ai-collab
bash scripts/start-codex.sh -f
```

**优点**：可以直接看到输出，方便调试

#### 方式 B: 后台运行（推荐生产使用）

```bash
cd /home/hn/projects/dual-ai-collab
bash scripts/start-codex.sh -b

# 查看日志
bash scripts/start-codex.sh -l

# 停止 worker
bash scripts/start-codex.sh -s
```

**优点**：不占用终端，可以关闭终端继续运行

#### 方式 C: tmux 会话（推荐远程服务器）

```bash
cd /home/hn/projects/dual-ai-collab
bash scripts/start-codex.sh -t

# 连接到会话
tmux attach -t codex-worker

# 分离会话（保持运行）
# 按 Ctrl+B，然后按 D

# 停止会话
tmux kill-session -t codex-worker
```

**优点**：可以随时连接查看，断开后继续运行

---

## 🔧 工作流程

### 完整的双 AI 协作流程

```
┌─────────────────────────────────────────────────────────┐
│ 第 1 步：Claude 创建任务                                 │
│ - 分析需求                                               │
│ - 拆分任务                                               │
│ - 写入任务板 (planning/codex-tasks.md)                  │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ 第 2 步：启动 Codex Worker                              │
│ bash scripts/start-codex.sh -t                          │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ 第 3 步：Codex 自动工作                                 │
│ - 读取任务板                                             │
│ - 领取 OPEN 任务                                         │
│ - 更新状态: OPEN → IN_PROGRESS                          │
│ - 编写代码                                               │
│ - 更新状态: IN_PROGRESS → DONE                          │
│ - 重复直到没有 OPEN 任务                                │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ 第 4 步：Claude 审计代码                                │
│ - 查看 DONE 状态的任务                                  │
│ - 审计代码质量                                           │
│ - 生成审计报告                                           │
│ - 更新状态: DONE → VERIFIED 或 REJECTED                 │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ 第 5 步：处理被拒绝的任务（如果有）                     │
│ - 将 REJECTED 任务改为 OPEN                             │
│ - Codex 重新执行                                         │
│ - Claude 再次审计                                        │
└─────────────────────────────────────────────────────────┘
```

---

## 📝 实际使用示例

### 示例 1: 开发一个简单的 Web API

#### Step 1: Claude 创建任务

```bash
cat > planning/codex-tasks.md << 'EOF'
# Codex 任务板

## 任务 #001: 创建 FastAPI 项目结构

**优先级**: P1
**状态**: OPEN
**分配给**: Codex
**创建时间**: 2026-03-06
**预计工时**: 1小时

### 任务描述
创建一个基础的 FastAPI 项目结构

### 技术要求
- 使用 FastAPI
- 创建 main.py
- 添加健康检查端点 /health
- 添加 requirements.txt

### 验收标准
- [ ] 项目结构创建完成
- [ ] main.py 包含 FastAPI 应用
- [ ] /health 端点返回 {"status": "ok"}
- [ ] requirements.txt 包含必要依赖

### 相关文件
- `main.py`
- `requirements.txt`

---

## 任务 #002: 实现用户登录 API

**优先级**: P1
**状态**: OPEN
**分配给**: Codex
**创建时间**: 2026-03-06
**预计工时**: 2小时

### 任务描述
实现用户登录 API 端点

### 技术要求
- POST /api/auth/login
- 接收 username 和 password
- 返回 JWT token
- 使用 pydantic 进行数据验证

### 验收标准
- [ ] API 端点实现
- [ ] 数据验证正确
- [ ] JWT token 生成
- [ ] 错误处理完善

### 相关文件
- `api/auth.py`
- `models/user.py`
- `utils/jwt.py`

---
EOF
```

#### Step 2: 启动 Codex Worker

```bash
# 在 tmux 中启动
bash scripts/start-codex.sh -t

# 或者后台启动
bash scripts/start-codex.sh -b
```

#### Step 3: 监控进度

```bash
# 实时查看日志
bash scripts/start-codex.sh -l

# 或者查看任务板状态
watch -n 5 'grep -E "\*\*状态\*\*:|状态:" planning/codex-tasks.md'
```

#### Step 4: Claude 审计

```bash
# 查看完成的任务
grep -A 20 -E "\*\*状态\*\*: DONE|状态: DONE" planning/codex-tasks.md

# 审计代码
cat main.py
cat api/auth.py

# 生成审计报告
cat > planning/progress/2026-03-06-audit.md << 'EOF'
# 代码审计报告

## 任务 #001: 创建 FastAPI 项目结构
**评分**: 95/100
**状态**: ✅ 通过

### 优点
- 项目结构清晰
- 代码规范
- 健康检查端点正常

### 改进建议
- 建议添加日志配置

**结论**: 通过验收
EOF

# 更新任务状态
sed -i 's/状态: DONE/状态: VERIFIED/' planning/codex-tasks.md
```

---

## ⚙️ 配置选项

### 环境变量

```bash
# 自定义任务板路径
export TASK_BOARD="custom/path/tasks.md"

# 最大迭代次数（防止无限循环）
export MAX_ITERATIONS=20

# 任务间隔时间（秒）
export SLEEP_BETWEEN_TASKS=10

# 然后启动
bash scripts/start-codex.sh -f
```

### 修改脚本配置

编辑 `scripts/codex-auto-worker.sh`：

```bash
# 在文件开头修改默认值
TASK_BOARD="${TASK_BOARD:-planning/codex-tasks.md}"
MAX_ITERATIONS="${MAX_ITERATIONS:-10}"
SLEEP_BETWEEN_TASKS="${SLEEP_BETWEEN_TASKS:-5}"
```

---

## 📊 查看统计报告

脚本会自动生成统计报告：

```bash
# 查看日志中的统计报告
tail -n 20 .dual-ai-collab/logs/worker.log
```

输出示例：

```
📊 任务统计报告
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
总任务数:     5
待开始:       0
进行中:       0
已完成:       3 (等待审计)
已验收:       2
被拒绝:       0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 🐛 故障排除

### 问题 1: codex 命令不可用

```bash
# 检查 codex 是否安装
which codex

# 如果没有，检查 PATH
echo $PATH

# 添加到 PATH
export PATH="$HOME/.nvm/versions/node/v20.20.0/bin:$PATH"
```

### 问题 2: 任务板解析失败

确保任务板格式正确：

```markdown
## 任务 #001: 任务标题

**优先级**: P1
**状态**: OPEN
**分配给**: Codex

### 任务描述
...

---
```

**注意**：
- 任务 ID 必须是数字
- 状态必须是: OPEN, IN_PROGRESS, DONE, VERIFIED, REJECTED
- 每个任务必须以 `---` 结尾

### 问题 3: Worker 卡住不动

```bash
# 停止 worker
bash scripts/start-codex.sh -s

# 或者强制停止
pkill -f codex-auto-worker

# 清理 tmux 会话
tmux kill-session -t codex-worker

# 重新启动
bash scripts/start-codex.sh -t
```

### 问题 4: 日志文件过大

```bash
# 清理日志
rm .dual-ai-collab/logs/worker.log
rm .dual-ai-collab/logs/codex-worker-nohup.log

# 或者归档
mv .dual-ai-collab/logs/worker.log .dual-ai-collab/logs/worker-$(date +%Y%m%d).log
```

---

## 💡 最佳实践

### 1. 任务拆分

✅ **好的任务拆分**：
- 每个任务 1-3 小时完成
- 任务独立，可单独测试
- 验收标准明确

❌ **不好的任务拆分**：
- 任务过大（超过 4 小时）
- 任务之间强依赖
- 验收标准模糊

### 2. 监控和日志

```bash
# 使用 tmux 方便监控
bash scripts/start-codex.sh -t

# 定期查看日志
tail -f .dual-ai-collab/logs/worker.log

# 定期检查任务板
watch -n 10 'grep -cE "\*\*状态\*\*: DONE|状态: DONE" planning/codex-tasks.md'
```

### 3. 审计频率

- P1 任务：每个任务完成后立即审计
- P2 任务：批量审计（3-5 个）
- P3 任务：阶段性审计

### 4. 错误处理

如果任务执行失败：
1. 查看日志找到错误原因
2. 修改任务描述使其更清晰
3. 将状态改回 OPEN
4. Codex 会自动重新执行

---

## 🚀 高级用法

### 并行运行多个 Worker

```bash
# Worker 1: 处理后端任务
TASK_BOARD="planning/backend-tasks.md" bash scripts/start-codex.sh -t

# Worker 2: 处理前端任务
TASK_BOARD="planning/frontend-tasks.md" bash scripts/start-codex.sh -t
```

### 定时启动

```bash
# 添加到 crontab
crontab -e

# 每天早上 9 点启动
0 9 * * * cd /home/hn/projects/dual-ai-collab && bash scripts/start-codex.sh -b
```

### 集成到 CI/CD

```yaml
# .github/workflows/codex-worker.yml
name: Codex Auto Worker

on:
  push:
    paths:
      - 'planning/codex-tasks.md'

jobs:
  codex-work:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run Codex Worker
        run: bash scripts/start-codex.sh -f
```

---

## 📞 获取帮助

```bash
# 查看帮助
bash scripts/start-codex.sh -h

# 查看脚本源码
cat scripts/codex-auto-worker.sh
cat scripts/start-codex.sh
```

---

**祝你使用愉快！🎉**
