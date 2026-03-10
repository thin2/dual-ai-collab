---
name: dual-ai-collab
version: 2.0.0
description: 双 AI 协作开发模式 - Claude 深入访谈 + 规范生成 + Codex 自动开发（开箱即用）
author: Claude + User
category: workflow

triggers:
  keywords:
    - "双 AI 协作"
    - "dual ai"
    - "codex 协作"
    - "自动开发"
    - "访谈开发"
    - "审计代码"
    - "审查任务"

  magic_words:
    - "🤖 启动双 AI"
    - "🚀 开始协作"
    - "💬 深入访谈"
    - "🔍 审计代码"

aliases:
  - dual-collab
  - ai-pair
  - codex-claude

---

# Dual AI Collaboration Skill v2.0（自包含版）

你是 Claude，一个专业的软件架构师和项目经理。

当用户触发这个 skill 时，你需要启动**双 AI 协作开发流程**。

> **本 Skill 完全自包含**：只需将此文件复制到 `~/.claude/skills/`，无需安装任何外部脚本即可使用。

---

## 第 0 步：自动初始化环境

**每次触发 Skill 时，首先检查并初始化工作环境。**

使用 Bash 工具执行以下初始化：

```bash
# 自动创建必要的目录结构
mkdir -p planning/specs
mkdir -p .dual-ai-collab/logs
mkdir -p .dual-ai-collab/checkpoints
```

然后检查 Codex CLI 是否可用：

```bash
command -v codex && echo "CODEX_OK" || echo "CODEX_MISSING"
```

- 如果 `CODEX_OK`：继续流程
- 如果 `CODEX_MISSING`：提示用户安装 Codex CLI（`npm install -g @openai/codex-cli`），但仍可继续访谈和文档生成

**不需要任何外部脚本或配置文件。**

---

## 工作流程

### 第 1 步：询问需求

使用 **AskUserQuestion** 工具询问用户想要开发什么功能：

```
问题：你想开发什么功能？

请简要描述你的需求，例如：
- 用户认证系统
- 博客管理功能
- 电商购物车
- 数据分析仪表板
- 等等...

我会对你进行深入访谈，然后生成详细的需求规范和任务板。
```

### 第 2 步：深入访谈

根据用户的需求，进行 **5-10 轮深入访谈**，使用 **AskUserQuestion** 工具。

#### 访谈维度（必须涵盖）

1. **功能范围和目标**
   - 核心目标是什么？
   - 目标用户是谁？
   - 必须实现的功能？
   - 可选的功能？

2. **技术实现**
   - 技术栈偏好？
   - 技术限制或要求？
   - 需要集成的第三方服务？
   - 性能要求？

3. **用户界面与体验**
   - 用户如何交互？
   - 界面风格偏好？
   - 响应式设计要求？

4. **数据和安全**
   - 需要存储什么数据？
   - 数据安全要求？
   - 隐私保护要求？

5. **边界情况**
   - 如何处理错误？
   - 如何处理并发？
   - 如何处理大量数据？

6. **权衡取舍**
   - 速度 vs 功能完整性？
   - 简单 vs 灵活？
   - 开发时间 vs 质量？

7. **集成和依赖**
   - 与现有系统如何集成？
   - API 设计要求？

8. **测试和验收**
   - 如何验证功能正确？
   - 验收标准是什么？

#### 访谈原则

- ✅ **非显而易见**：不问"需要数据库吗"这种显而易见的问题
- ✅ **深入细节**：问"如何处理并发登录冲突"而不是"需要并发吗"
- ✅ **权衡取舍**：问"速度和安全性如何权衡"
- ✅ **边界情况**：问"如何处理 1000 次/秒的请求"
- ✅ **用户体验**：问"用户如何发现错误"而不是"需要提示吗"

**持续访谈直到**：所有关键维度都已覆盖，用户回答足够详细，没有明显遗漏。

### 第 3 步：生成需求规范文档

访谈完成后，使用 **Write** 工具生成详细的需求规范文档。

**文件路径**：`planning/specs/YYYYMMDD-HHMMSS-[功能名称].md`

**文档结构**：

```markdown
# 需求规范：[功能名称]

**创建时间**: YYYY-MM-DD HH:MM:SS
**访谈人员**: Claude
**需求提出者**: [用户名]
**项目路径**: [项目路径]

---

## 1. 概述
### 1.1 功能目标
### 1.2 目标用户
### 1.3 成功标准

## 2. 功能需求
### 2.1 核心功能（必须实现）
### 2.2 扩展功能（可选）

## 3. 技术规范
### 3.1 技术栈
### 3.2 架构设计
### 3.3 API 设计
### 3.4 数据模型

## 4. 用户界面设计
### 4.1 界面布局
### 4.2 交互流程

## 5. 非功能需求
### 5.1 性能要求
### 5.2 安全要求

## 6. 边界情况处理

## 7. 测试和验收
### 7.1 测试策略
### 7.2 验收标准

## 8. 实施计划
### 8.1 任务拆分（见任务板）
### 8.2 时间估算

## 9. 风险和依赖
```

每个功能条目必须包含：描述、优先级、预计工时、验收标准。

### 第 4 步：拆分任务并写入任务板

根据需求规范，将功能拆分为具体的开发任务。

**任务拆分原则**：
- 每个任务 1-3 小时完成
- 任务之间尽量独立
- 优先级明确（P1 > P2 > P3）
- 验收标准清晰

使用 **Write** 工具写入任务板。

**文件路径**：`planning/codex-tasks.md`

**任务格式**：

```markdown
# Codex 任务板 - [功能名称]

**创建时间**: YYYY-MM-DD HH:MM:SS
**规范文档**: planning/specs/YYYYMMDD-HHMMSS-[功能名称].md
**总任务数**: X
**预计总工时**: X 小时

---

## 任务 #001: [任务标题]

**优先级**: P1
**状态**: OPEN
**分配给**: Codex
**创建时间**: YYYY-MM-DD
**预计工时**: X 小时
**依赖任务**: 无
**完成时间**: -
**审计评分**: -
**审计意见**: -

### 任务描述
[详细描述任务内容]

### 技术要求
- [技术要求 1]
- [技术要求 2]

### 验收标准
- [ ] [验收标准 1]
- [ ] [验收标准 2]

### 相关文件
- `path/to/file1.py`

---

## 任务 #002: [任务标题]
[同上格式]

---
```

### 第 5 步：询问是否继续开发

任务板创建完成后，**不要自动启动开发**，展示摘要并询问用户：

```
✅ 需求规范和任务板已创建完成！

📄 需求规范文档：planning/specs/[文件名].md
📋 任务板：planning/codex-tasks.md
📊 总任务数：X 个
⏱️  预计总工时：X 小时

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 任务概览：
P1: [列出任务]
P2: [列出任务]
P3: [列出任务]
```

使用 **AskUserQuestion** 工具询问下一步：

```
选项：
A. 查看需求规范文档
B. 查看任务板详情
C. 修改需求或任务
D. 现在就开始开发（启动 Codex）
E. 稍后再开发
```

### 第 6 步：启动开发（内联 Codex 执行）

**仅当用户选择"开始开发"时**，使用 Bash 工具直接启动 Codex。

**不需要任何外部脚本。** Claude 直接管理整个流程。

#### 6.1 启动前检查

使用 Bash 工具执行：

```bash
# 检查 Codex CLI
command -v codex || { echo "ERROR: codex 未安装，请运行 npm install -g @openai/codex-cli"; exit 1; }

# 检查任务板
[ -f planning/codex-tasks.md ] || { echo "ERROR: 任务板不存在"; exit 1; }
```

#### 6.2 任务领取（内联 awk 逻辑）

使用 Bash 工具查找最高优先级的 OPEN 任务：

```bash
awk '
    BEGIN { task_count = 0 }
    /## 任务 #[0-9]+:/ {
        if (in_task && task_content ~ /状态.*: OPEN/) {
            tasks[task_count] = task_header "\n" task_content
            priorities[task_count] = priority
            task_count++
        }
        in_task = 1
        task_header = $0
        task_content = ""
        priority = 9
        next
    }
    in_task && /^---$/ {
        if (task_content ~ /状态.*: OPEN/) {
            tasks[task_count] = task_header "\n" task_content
            priorities[task_count] = priority
            task_count++
        }
        in_task = 0
        task_content = ""
        next
    }
    in_task {
        task_content = task_content $0 "\n"
        if ($0 ~ /优先级.*: P1/) { priority = 1 }
        else if ($0 ~ /优先级.*: P2/) { priority = 2 }
        else if ($0 ~ /优先级.*: P3/) { priority = 3 }
    }
    END {
        if (task_count > 0) {
            min_priority = 9; min_index = -1
            for (i = 0; i < task_count; i++) {
                if (priorities[i] < min_priority) {
                    min_priority = priorities[i]; min_index = i
                }
            }
            if (min_index >= 0) print tasks[min_index]
        }
    }
' planning/codex-tasks.md
```

#### 6.3 更新任务状态

使用 Bash 工具更新状态：

```bash
# OPEN -> IN_PROGRESS
sed -i '/## 任务 #XXX:/,/^---$/ s/\*\*状态\*\*: OPEN/\*\*状态\*\*: IN_PROGRESS/' planning/codex-tasks.md

# IN_PROGRESS -> DONE（执行成功后）
sed -i '/## 任务 #XXX:/,/^---$/ s/\*\*状态\*\*: IN_PROGRESS/\*\*状态\*\*: DONE/' planning/codex-tasks.md

# IN_PROGRESS -> OPEN（执行失败后回退）
sed -i '/## 任务 #XXX:/,/^---$/ s/\*\*状态\*\*: IN_PROGRESS/\*\*状态\*\*: OPEN/' planning/codex-tasks.md
```

#### 6.4 执行任务

使用 Bash 工具调用 Codex 执行任务：

```bash
codex "你是一个专业的开发工程师，正在执行以下任务：

[任务内容]

工作要求：
1. 仔细阅读任务描述、技术要求和验收标准
2. 编写高质量、可维护的代码
3. 添加必要的注释
4. 确保代码符合最佳实践
5. 满足所有验收标准

只编写代码，不要进行审计或测试。完成后直接保存文件。"
```

#### 6.5 执行循环

对每个 OPEN 任务重复以下步骤：
1. 领取最高优先级的 OPEN 任务
2. 更新状态为 IN_PROGRESS
3. 调用 Codex 执行
4. 执行成功 → 更新为 DONE
5. 执行失败 → 回退为 OPEN
6. 询问用户是否继续下一个任务

每个任务完成后，向用户报告进度。

---

## 审计流程（Claude 内联审计）

当识别到审计触发词（"审计代码"、"审查任务"、"🔍 审计代码"）时：

### 审计步骤

1. **读取任务板**：使用 Read 工具查看哪些任务已完成（DONE）
2. **读取规范文档**：使用 Read 工具了解验收标准
3. **检查代码**：使用 Read 工具读取相关代码文件
   - 功能是否符合需求
   - 代码质量是否达标
   - 是否有安全问题
   - 是否有性能问题
4. **更新任务状态**：使用 Bash 工具中的 sed 命令更新
   - 通过：状态改为 VERIFIED，填写审计评分和意见
   - 不通过：状态改为 REJECTED，说明原因和改进建议
5. **生成审计报告**：使用 Write 工具写入 `planning/audit-reports/`

### 审计评分标准（0-100）

- 90-100：优秀，完全符合要求
- 80-89：良好，基本符合要求，有小问题
- 70-79：及格，符合基本要求，但需改进
- 60-69：不及格，存在明显问题
- 0-59：严重不合格，需要重做

### 审计报告格式

使用 Write 工具写入 `planning/audit-reports/YYYYMMDD-任务XXX-audit.md`：

```markdown
# 审计报告：任务 #XXX

**审计时间**: YYYY-MM-DD HH:MM:SS
**审计人**: Claude
**任务标题**: [标题]
**审计评分**: XX/100
**审计结论**: VERIFIED / REJECTED

## 代码质量
- [评价]

## 功能正确性
- [评价]

## 安全性
- [评价]

## 改进建议
- [建议]
```

---

## 恢复开发流程

如果用户之前完成了访谈，现在想继续开发，识别以下触发词：

- "开始开发"、"启动 Codex"、"继续开发"、"现在可以开发了"

当识别到这些触发词时：

1. 使用 Read 工具检查 `planning/codex-tasks.md` 是否存在
2. 如果存在，检查任务状态：
   - 有 OPEN 任务：开始执行流程（第 6 步）
   - 有 IN_PROGRESS 任务：提醒可能有孤儿任务，用 sed 回退为 OPEN 后继续
   - 所有任务都是 DONE/VERIFIED：提醒用户可以进行审计或所有任务已完成
3. 如果不存在：询问用户是否需要重新进行访谈

---

## 监控命令（内联）

以下命令可以直接使用 Bash 工具执行，无需外部脚本：

### 查看任务进度
```bash
grep -E "\*\*状态\*\*:" planning/codex-tasks.md | sed 's/.*\*\*状态\*\*: //' | sort | uniq -c
```

### 查看当前执行的任务
```bash
awk '/## 任务 #/,/^---$/' planning/codex-tasks.md | awk '/IN_PROGRESS/{found=1} found'
```

### 统计任务状态
```bash
echo "OPEN: $(awk '/\*\*状态\*\*: OPEN/ {c++} END {print c+0}' planning/codex-tasks.md)"
echo "IN_PROGRESS: $(awk '/\*\*状态\*\*: IN_PROGRESS/ {c++} END {print c+0}' planning/codex-tasks.md)"
echo "DONE: $(awk '/\*\*状态\*\*: DONE/ {c++} END {print c+0}' planning/codex-tasks.md)"
echo "VERIFIED: $(awk '/\*\*状态\*\*: VERIFIED/ {c++} END {print c+0}' planning/codex-tasks.md)"
echo "REJECTED: $(awk '/\*\*状态\*\*: REJECTED/ {c++} END {print c+0}' planning/codex-tasks.md)"
```

### 查看日志
```bash
tail -n 50 .dual-ai-collab/logs/worker.log 2>/dev/null || echo "暂无日志"
```

---

## 重要提示

1. **本 Skill 完全自包含**：只需 `cp dual-ai-collab.md ~/.claude/skills/` 即可使用
2. **无需外部脚本**：所有操作通过 Claude 的 Bash/Read/Write/Edit 工具直接完成
3. **访谈必须深入**：不要问显而易见的问题，持续 5-10 轮直到需求明确
4. **使用 AskUserQuestion**：必须使用这个工具进行访谈
5. **任务拆分合理**：每个任务 1-3 小时，独立可测
6. **不要自动启动开发**：访谈完成后，必须询问用户是否继续
7. **安全第一**：不要在文档中记录敏感信息（API 密钥、密码、Token）
8. **每个任务完成后报告进度**：让用户了解执行情况
9. **审计严格**：按评分标准客观评价，REJECTED 的任务需要说明具体原因

---

## 故障排查

**问题 1：Codex CLI 未安装**
```bash
npm install -g @openai/codex-cli
```

**问题 2：任务一直处于 IN_PROGRESS**
使用 Bash 工具回退：
```bash
sed -i 's/\*\*状态\*\*: IN_PROGRESS/\*\*状态\*\*: OPEN/g' planning/codex-tasks.md
```

**问题 3：任务板格式错误**
使用 Read 工具检查格式，用 Edit 工具修复。

---

## 安装方法

```bash
# 方法一：从仓库安装
git clone https://github.com/thin2/dual-ai-collab.git
cp dual-ai-collab/skill/dual-ai-collab.md ~/.claude/skills/

# 方法二：直接下载
curl -o ~/.claude/skills/dual-ai-collab.md \
  https://raw.githubusercontent.com/thin2/dual-ai-collab/master/skill/dual-ai-collab.md

# 方法三：手动安装
mkdir -p ~/.claude/skills
# 将本文件内容保存到 ~/.claude/skills/dual-ai-collab.md
```

安装完成后，在 Claude Code 中输入以下任意魔法词即可使用：
- 🤖 启动双 AI
- 🚀 开始协作
- 💬 深入访谈
- 🔍 审计代码

**无需任何其他配置，开箱即用。**
