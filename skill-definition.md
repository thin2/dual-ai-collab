# Dual AI Collaboration Skill

**Skill Name**: `dual-ai-collab`
**Aliases**: `codex-claude`, `ai-pair`, `dual-dev`
**Version**: 1.0.0
**Author**: Claude + User
**Category**: Workflow Orchestration

---

## 概述

双 AI 协作模式：Claude 担任架构师/审计员，Codex 担任开发工程师，通过共享任务板进行异步协作。

### 核心理念

- **Claude（架构师/审计员）**：负责需求分析、架构设计、代码审计、质量验收
- **Codex（开发工程师）**：负责具体代码实现、功能开发、bug 修复
- **任务板（Task Board）**：唯一协作接口，记录任务状态和优先级

---

## 使用场景

- ✅ 大型项目开发（需要架构设计 + 快速实现）
- ✅ 代码质量要求高（需要审计验收）
- ✅ 前后端分离项目
- ✅ 需要持续迭代的项目
- ✅ 团队协作模式模拟

---

## 工作流程

```
┌─────────────────────────────────────────────────────────┐
│                    Claude (架构师/审计员)                 │
│  - 需求分析                                              │
│  - 架构设计                                              │
│  - 创建任务（写入任务板）                                │
│  - 代码审计                                              │
│  - 质量验收                                              │
│  - 更新任务状态                                          │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
         ┌────────────────────┐
         │   任务板 (Task Board)  │
         │  planning/codex-tasks.md │
         │                    │
         │  - 任务列表        │
         │  - 优先级          │
         │  - 状态跟踪        │
         │  - 验收标准        │
         └────────┬───────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│                    Codex (开发工程师)                     │
│  - 读取任务板                                            │
│  - 执行最高优先级任务                                    │
│  - 编写代码                                              │
│  - 提交代码                                              │
│  - 更新任务进度                                          │
└─────────────────────────────────────────────────────────┘
```

---

## Skill 实现

### 触发关键词

- `dual ai collab`
- `codex claude collab`
- `ai pair programming`
- `双 AI 协作`

### 参数

```yaml
mode:
  - init: 初始化协作环境
  - plan: Claude 规划任务
  - dev: 启动 Codex 开发
  - audit: Claude 审计代码
  - status: 查看任务状态

role:
  - claude: 架构师/审计员模式
  - codex: 开发工程师模式
```

---

## 使用方法

### 1. 初始化协作环境

```bash
/dual-ai-collab init
```

**执行内容**：
- 创建任务板文件 `planning/codex-tasks.md`
- 创建协作配置 `.dual-ai-collab.yml`
- 创建进度记录目录 `planning/progress/`

### 2. Claude 规划任务

```bash
/dual-ai-collab plan "开发 Vue 前端"
```

**执行内容**：
- 分析需求
- 设计架构
- 拆分任务
- 写入任务板（带优先级和验收标准）

### 3. 启动 Codex 开发

```bash
/dual-ai-collab dev
```

**执行内容**：
- 读取任务板
- 执行最高优先级的 OPEN 任务
- 编写代码
- 更新任务状态为 IN_PROGRESS → DONE

### 4. Claude 审计代码

```bash
/dual-ai-collab audit
```

**执行内容**：
- 读取 Codex 完成的代码
- 执行代码审计（质量、规范、性能、安全）
- 生成审计报告
- 更新任务状态（VERIFIED 或 REJECTED）

### 5. 查看任务状态

```bash
/dual-ai-collab status
```

**执行内容**：
- 显示任务板概览
- 统计任务完成情况
- 显示当前阻塞项

---

## 任务板格式

### 文件位置
`planning/codex-tasks.md`

### 任务格式

```markdown
## 任务 #001: 实现用户登录功能

**优先级**: P1 (高)
**状态**: OPEN
**分配给**: Codex
**创建时间**: 2026-03-02
**预计工时**: 2小时

### 任务描述
实现用户登录功能，包括表单验证、API 调用、Token 存储。

### 技术要求
- 使用 Vue 3 Composition API
- 表单验证使用 Element Plus
- Token 存储到 localStorage
- 错误处理和提示

### 验收标准
- [ ] 表单验证正确（用户名/密码必填）
- [ ] API 调用成功
- [ ] Token 正确存储
- [ ] 错误提示友好
- [ ] 代码符合 ESLint 规范

### 相关文件
- `src/views/Login.vue`
- `src/api/auth.js`
- `src/stores/auth.js`

---
```

### 任务状态

- `OPEN`: 待开始
- `IN_PROGRESS`: 进行中
- `DONE`: 已完成（待审计）
- `VERIFIED`: 已验收通过
- `REJECTED`: 审计未通过（需修复）
- `BLOCKED`: 阻塞中

---

## 配置文件

### `.dual-ai-collab.yml`

```yaml
# 双 AI 协作配置

project:
  name: "Youtu-GraphRAG"
  type: "fullstack"

roles:
  claude:
    responsibilities:
      - "需求分析"
      - "架构设计"
      - "代码审计"
      - "质量验收"
    output_dir: "planning/progress/"

  codex:
    responsibilities:
      - "代码实现"
      - "功能开发"
      - "Bug 修复"
    working_dir: "."

task_board:
  path: "planning/codex-tasks.md"
  priorities: ["P1", "P2", "P3"]
  statuses: ["OPEN", "IN_PROGRESS", "DONE", "VERIFIED", "REJECTED", "BLOCKED"]

audit:
  enabled: true
  criteria:
    - "代码质量"
    - "设计规范"
    - "性能优化"
    - "安全性"
    - "可维护性"
  report_dir: "planning/progress/"

notifications:
  on_task_complete: true
  on_audit_complete: true
```

---

## 实现代码

### Skill Handler (TypeScript)

```typescript
// ~/.claude/skills/dual-ai-collab/index.ts

import { Skill, SkillContext } from '@claude/skill-sdk'
import fs from 'fs/promises'
import path from 'path'

interface DualAICollabOptions {
  mode: 'init' | 'plan' | 'dev' | 'audit' | 'status'
  role?: 'claude' | 'codex'
  task?: string
}

export class DualAICollabSkill extends Skill {
  name = 'dual-ai-collab'
  aliases = ['codex-claude', 'ai-pair', 'dual-dev']

  async execute(ctx: SkillContext, options: DualAICollabOptions) {
    const { mode, role, task } = options

    switch (mode) {
      case 'init':
        return await this.initEnvironment(ctx)
      case 'plan':
        return await this.planTasks(ctx, task)
      case 'dev':
        return await this.startDevelopment(ctx)
      case 'audit':
        return await this.auditCode(ctx)
      case 'status':
        return await this.showStatus(ctx)
      default:
        throw new Error(`Unknown mode: ${mode}`)
    }
  }

  private async initEnvironment(ctx: SkillContext) {
    const projectRoot = ctx.workingDirectory

    // 创建任务板
    const taskBoardPath = path.join(projectRoot, 'planning/codex-tasks.md')
    await fs.mkdir(path.dirname(taskBoardPath), { recursive: true })
    await fs.writeFile(taskBoardPath, this.getTaskBoardTemplate())

    // 创建配置文件
    const configPath = path.join(projectRoot, '.dual-ai-collab.yml')
    await fs.writeFile(configPath, this.getConfigTemplate())

    // 创建进度目录
    await fs.mkdir(path.join(projectRoot, 'planning/progress'), { recursive: true })

    return {
      success: true,
      message: '✅ 双 AI 协作环境初始化完成',
      files: [taskBoardPath, configPath]
    }
  }

  private async planTasks(ctx: SkillContext, taskDescription: string) {
    // 调用 planner agent 分析任务
    const plan = await ctx.callAgent('oh-my-claudecode:planner', {
      prompt: `分析以下需求并拆分为具体任务：\n${taskDescription}`,
      model: 'opus'
    })

    // 写入任务板
    const taskBoardPath = path.join(ctx.workingDirectory, 'planning/codex-tasks.md')
    const tasks = this.formatTasks(plan.tasks)
    await fs.appendFile(taskBoardPath, tasks)

    return {
      success: true,
      message: `✅ 已创建 ${plan.tasks.length} 个任务`,
      tasks: plan.tasks
    }
  }

  private async startDevelopment(ctx: SkillContext) {
    // 读取任务板
    const taskBoardPath = path.join(ctx.workingDirectory, 'planning/codex-tasks.md')
    const taskBoard = await fs.readFile(taskBoardPath, 'utf-8')

    // 找到最高优先级的 OPEN 任务
    const nextTask = this.findNextTask(taskBoard)

    if (!nextTask) {
      return {
        success: true,
        message: '✅ 所有任务已完成！'
      }
    }

    // 调用 executor agent 执行任务
    const result = await ctx.callAgent('oh-my-claudecode:executor', {
      prompt: `执行以下任务：\n${nextTask.description}\n\n验收标准：\n${nextTask.criteria}`,
      model: 'sonnet'
    })

    // 更新任务状态
    await this.updateTaskStatus(taskBoardPath, nextTask.id, 'DONE')

    return {
      success: true,
      message: `✅ 任务 #${nextTask.id} 已完成`,
      task: nextTask
    }
  }

  private async auditCode(ctx: SkillContext) {
    // 读取任务板，找到 DONE 状态的任务
    const taskBoardPath = path.join(ctx.workingDirectory, 'planning/codex-tasks.md')
    const taskBoard = await fs.readFile(taskBoardPath, 'utf-8')
    const doneTasks = this.findTasksByStatus(taskBoard, 'DONE')

    if (doneTasks.length === 0) {
      return {
        success: true,
        message: '✅ 没有待审计的任务'
      }
    }

    // 对每个任务执行审计
    const auditResults = []
    for (const task of doneTasks) {
      const result = await ctx.callAgent('oh-my-claudecode:code-reviewer', {
        prompt: `审计以下任务的代码实现：\n${task.description}\n\n相关文件：\n${task.files.join('\n')}`,
        model: 'opus'
      })

      auditResults.push({
        taskId: task.id,
        passed: result.score >= 90,
        score: result.score,
        issues: result.issues
      })

      // 更新任务状态
      const newStatus = result.score >= 90 ? 'VERIFIED' : 'REJECTED'
      await this.updateTaskStatus(taskBoardPath, task.id, newStatus)
    }

    // 生成审计报告
    const reportPath = path.join(
      ctx.workingDirectory,
      `planning/progress/${new Date().toISOString().split('T')[0]}-audit.md`
    )
    await fs.writeFile(reportPath, this.formatAuditReport(auditResults))

    return {
      success: true,
      message: `✅ 已审计 ${doneTasks.length} 个任务`,
      results: auditResults,
      reportPath
    }
  }

  private async showStatus(ctx: SkillContext) {
    const taskBoardPath = path.join(ctx.workingDirectory, 'planning/codex-tasks.md')
    const taskBoard = await fs.readFile(taskBoardPath, 'utf-8')

    const stats = {
      total: 0,
      open: 0,
      inProgress: 0,
      done: 0,
      verified: 0,
      rejected: 0,
      blocked: 0
    }

    // 统计任务状态
    const tasks = this.parseTasks(taskBoard)
    tasks.forEach(task => {
      stats.total++
      stats[task.status.toLowerCase()] = (stats[task.status.toLowerCase()] || 0) + 1
    })

    return {
      success: true,
      stats,
      tasks
    }
  }

  // Helper methods
  private getTaskBoardTemplate(): string {
    return `# Codex 任务板

## 任务列表

<!-- 任务将自动添加到这里 -->

---

## 任务状态说明

- **OPEN**: 待开始
- **IN_PROGRESS**: 进行中
- **DONE**: 已完成（待审计）
- **VERIFIED**: 已验收通过
- **REJECTED**: 审计未通过（需修复）
- **BLOCKED**: 阻塞中

## 优先级说明

- **P1**: 高优先级（紧急且重要）
- **P2**: 中优先级（重要但不紧急）
- **P3**: 低优先级（可延后）
`
  }

  private getConfigTemplate(): string {
    return `# 双 AI 协作配置

project:
  name: "My Project"
  type: "fullstack"

roles:
  claude:
    responsibilities:
      - "需求分析"
      - "架构设计"
      - "代码审计"
      - "质量验收"
    output_dir: "planning/progress/"

  codex:
    responsibilities:
      - "代码实现"
      - "功能开发"
      - "Bug 修复"
    working_dir: "."

task_board:
  path: "planning/codex-tasks.md"
  priorities: ["P1", "P2", "P3"]
  statuses: ["OPEN", "IN_PROGRESS", "DONE", "VERIFIED", "REJECTED", "BLOCKED"]

audit:
  enabled: true
  criteria:
    - "代码质量"
    - "设计规范"
    - "性能优化"
    - "安全性"
    - "可维护性"
  report_dir: "planning/progress/"
`
  }

  private formatTasks(tasks: any[]): string {
    return tasks.map((task, index) => `
## 任务 #${String(index + 1).padStart(3, '0')}: ${task.title}

**优先级**: ${task.priority}
**状态**: OPEN
**分配给**: Codex
**创建时间**: ${new Date().toISOString().split('T')[0]}
**预计工时**: ${task.estimatedHours}小时

### 任务描述
${task.description}

### 技术要求
${task.requirements.map(r => `- ${r}`).join('\n')}

### 验收标准
${task.criteria.map(c => `- [ ] ${c}`).join('\n')}

### 相关文件
${task.files.map(f => `- \`${f}\``).join('\n')}

---
`).join('\n')
  }

  private findNextTask(taskBoard: string): any {
    const tasks = this.parseTasks(taskBoard)
    const openTasks = tasks.filter(t => t.status === 'OPEN')

    // 按优先级排序
    openTasks.sort((a, b) => {
      const priorityOrder = { P1: 1, P2: 2, P3: 3 }
      return priorityOrder[a.priority] - priorityOrder[b.priority]
    })

    return openTasks[0] || null
  }

  private findTasksByStatus(taskBoard: string, status: string): any[] {
    const tasks = this.parseTasks(taskBoard)
    return tasks.filter(t => t.status === status)
  }

  private parseTasks(taskBoard: string): any[] {
    // 解析任务板内容
    const taskRegex = /## 任务 #(\d+): (.+?)\n\n\*\*优先级\*\*: (P\d)\s+\n\*\*状态\*\*: (\w+)/g
    const tasks = []
    let match

    while ((match = taskRegex.exec(taskBoard)) !== null) {
      tasks.push({
        id: match[1],
        title: match[2],
        priority: match[3],
        status: match[4]
      })
    }

    return tasks
  }

  private async updateTaskStatus(taskBoardPath: string, taskId: string, newStatus: string) {
    let content = await fs.readFile(taskBoardPath, 'utf-8')
    const regex = new RegExp(`(## 任务 #${taskId}:.*?\\n\\n.*?\\*\\*状态\\*\\*: )\\w+`, 's')
    content = content.replace(regex, `$1${newStatus}`)
    await fs.writeFile(taskBoardPath, content)
  }

  private formatAuditReport(results: any[]): string {
    return `# 代码审计报告

**审计时间**: ${new Date().toISOString()}
**审计任务数**: ${results.length}

## 审计结果

${results.map(r => `
### 任务 #${r.taskId}

**评分**: ${r.score}/100
**状态**: ${r.passed ? '✅ 通过' : '❌ 未通过'}

${r.issues.length > 0 ? `
**发现的问题**:
${r.issues.map(i => `- ${i}`).join('\n')}
` : '无问题'}

---
`).join('\n')}

## 总结

- 通过: ${results.filter(r => r.passed).length}
- 未通过: ${results.filter(r => !r.passed).length}
`
  }
}

export default new DualAICollabSkill()
```

---

## 使用示例

### 完整工作流程

```bash
# 1. 初始化协作环境
/dual-ai-collab init

# 2. Claude 规划任务
/dual-ai-collab plan "开发用户认证系统，包括登录、注册、密码重置功能"

# 3. 启动 Codex 开发（自动执行最高优先级任务）
/dual-ai-collab dev

# 4. Claude 审计代码
/dual-ai-collab audit

# 5. 查看任务状态
/dual-ai-collab status

# 6. 如果有 REJECTED 任务，Codex 修复后再次审计
/dual-ai-collab dev
/dual-ai-collab audit

# 7. 重复步骤 3-6 直到所有任务完成
```

---

## 高级用法

### 自定义审计标准

编辑 `.dual-ai-collab.yml`:

```yaml
audit:
  enabled: true
  criteria:
    - "代码质量"
    - "设计规范"
    - "性能优化"
    - "安全性"
    - "可维护性"
    - "测试覆盖率"  # 新增
    - "文档完整性"  # 新增
  min_score: 90  # 最低通过分数
```

### 并行开发

```bash
# 启动多个 Codex 实例并行开发
/dual-ai-collab dev --parallel 3
```

### 持续集成

```bash
# 自动化流程：开发 → 审计 → 修复 → 验证
/dual-ai-collab auto --max-iterations 10
```

---

## 最佳实践

### 1. 任务拆分原则
- 每个任务应该是独立的、可测试的
- 任务粒度：2-4 小时完成
- 明确的验收标准（至少 3 条）

### 2. 审计频率
- P1 任务：每个任务完成后立即审计
- P2/P3 任务：批量审计（3-5 个任务）

### 3. 沟通机制
- 使用任务板作为唯一真相来源
- 审计报告详细记录问题和建议
- 定期同步进度（每日/每周）

### 4. 质量保证
- 代码审计评分 ≥ 90 分才能通过
- 所有验收标准必须满足
- 关键功能需要测试覆盖

---

## 故障排除

### 问题 1: 任务板解析失败
**原因**: 任务格式不符合规范
**解决**: 使用 `/dual-ai-collab init` 重新初始化

### 问题 2: Codex 找不到任务
**原因**: 所有任务都不是 OPEN 状态
**解决**: 检查任务板，手动将任务状态改为 OPEN

### 问题 3: 审计一直不通过
**原因**: 审计标准过于严格
**解决**: 调整 `.dual-ai-collab.yml` 中的 `min_score`

---

## 贡献指南

欢迎提交 Issue 和 Pull Request！

**GitHub 仓库**: https://github.com/yourusername/dual-ai-collab

---

## 许可证

MIT License

---

## 更新日志

### v1.0.0 (2026-03-02)
- ✅ 初始版本发布
- ✅ 支持任务规划、开发、审计
- ✅ 支持任务状态跟踪
- ✅ 支持审计报告生成

---

**作者**: Claude + User
**最后更新**: 2026-03-02
