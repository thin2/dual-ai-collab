# Dual AI Collaboration - 架构设计文档

**版本**: 2.1.0
**最后更新**: 2026-03-10
**状态**: 正式发布

---

## 目录

1. [核心架构](#核心架构)
2. [实现方式](#实现方式)
3. [工作流程](#工作流程)
4. [目录结构](#目录结构)
5. [任务状态机](#任务状态机)
6. [任务板格式规范](#任务板格式规范)
7. [设计决策记录](#设计决策记录)
8. [未来路线图](#未来路线图)

---

## 核心架构

### 角色分工

| 角色 | 身份 | 职责 |
|------|------|------|
| Claude | 架构师 / 审计员 | 需求访谈、规范生成、任务拆分、代码审计、质量验收 |
| Codex | 开发工程师 | 读取任务板、实现代码、更新任务状态 |
| 任务板 | 协作接口 | 唯一信息交换媒介，记录任务定义、状态、验收标准 |

### 协作原则

- **异步协作**：Claude 和 Codex 通过任务板异步通信，互不阻塞
- **单一真相来源**：`planning/codex-tasks.md` 是任务状态的唯一权威
- **验收驱动**：每个任务必须有明确的验收标准，Claude 依据标准审计
- **自包含运行**：无需外部服务或数据库，纯文件驱动

---

## 实现方式

### 纯 Markdown Skill（非 TypeScript SDK）

v2.0.0 完全放弃了 TypeScript 实现，改用纯 Markdown Skill 文件。

**安装路径**

```
~/.claude/skills/dual-ai-collab.md
```

**触发方式**

关键词触发（Claude Code 自动识别）：

```
双 AI 协作 / dual ai / codex 协作 / 自动开发 / 访谈开发 / 审计代码 / 审查任务
```

魔法词触发：

```
启动双 AI / 开始协作 / 深入访谈 / 审计代码
```

**执行工具**

Skill 内部使用 Claude Code 内置工具，无需外部依赖：

- `Bash` - 初始化目录、运行检查
- `Read` - 读取任务板和需求文档
- `Write` - 生成需求规范、创建任务板
- `Edit` - 更新任务状态
- `AskUserQuestion` - 执行用户访谈

---

## 工作流程

```
用户需求
    |
    v
[第 1 步] Claude 初始询问（AskUserQuestion）
    |      了解用户想开发什么功能
    |
    v
[第 2 步] Claude 深入访谈（5-10 轮 AskUserQuestion）
    |      覆盖：功能范围、技术栈、UI、数据安全、边界情况、权衡取舍
    |
    v
[第 3 步] Claude 生成需求规范（Write）
    |      输出：planning/specs/YYYYMMDD-HHMMSS-[功能名].md
    |
    v
[第 4 步] Claude 拆分任务写入任务板（Write）
    |      输出：planning/codex-tasks.md
    |      每个任务包含：描述、优先级、验收标准、依赖任务
    |
    v
[第 5 步] 展示摘要并等待用户审查
    |      展示任务概览、总工时预估
    |      使用 AskUserQuestion 询问用户是否继续
    |      用户可选择：开始开发 / 修改规划 / 取消
    |
    v
[第 6 步] Codex 执行开发
    |      读取任务板 -> 选取最高优先级 OPEN 任务（检查依赖）
    |      实现代码 -> 更新状态为 IN_PROGRESS -> DONE
    |      自动循环到下一个任务
    |
    v
[第 7 步] 双重审计（Codex + Claude）
    |      Codex 先审查 -> 输出评分和问题清单
    |      Claude 终审 -> 结合 Codex 结果做最终判定
    |      VERIFIED（通过）或 REJECTED（不通过）
    |
    v
[第 8 步] 自动修复循环（REJECTED 任务）
    |      Codex 根据审计意见自动修复
    |      修复后重新进入审计流程
    |      最多修复 3 轮，超过则标记 FAILED
    |
    v
[验收通过] 所有任务 VERIFIED -> 项目完成
[验收失败] 超过修复上限 -> 标记 FAILED -> 通知用户人工介入
```

---

## 目录结构

v2.1.0 自包含版，克隆仓库即可使用：

```
dual-ai-collab/
├── skill/
│   ├── dual-ai-collab.md       # 核心 Skill 文件（安装到 ~/.claude/skills/）
│   └── CHANGELOG.md            # 版本更新日志
├── tests/                      # 测试套件（64 个测试用例，7 个测试套件）
│   └── run_all_tests.sh
└── planning/                   # 运行时生成（不提交到版本库）
    ├── codex-tasks.md          # 任务板（Codex 的工作队列）
    └── specs/                  # 需求规范文档
        └── YYYYMMDD-HHMMSS-[功能名].md
```

**说明**

- `skill/dual-ai-collab.md` 是唯一必需文件，其余均为辅助
- `planning/` 目录在运行时由 Claude 自动创建，建议加入 `.gitignore`

---

## 任务状态机

```
          创建
           |
           v
         OPEN
           |
    Codex 领取任务
           |
           v
       IN_PROGRESS
           |
    Codex 完成实现
           |
           v
          DONE
           |
      Claude 审计
          / \
         /   \
        v     v
    VERIFIED  REJECTED
    (通过)    (退回修复)
                |
         Codex 修复后
                |
                v
          IN_PROGRESS
          (重新循环)
```

附加状态：

- `BLOCKED` - 存在外部依赖阻塞，需要人工介入

状态转换规则：

- 只有 Codex 可以将任务从 `OPEN` 移动到 `IN_PROGRESS`
- 只有 Codex 可以将任务从 `IN_PROGRESS` 移动到 `DONE`
- 只有 Claude 可以将任务从 `DONE` 移动到 `VERIFIED` 或 `REJECTED`
- `REJECTED` 任务必须附带审计意见，说明具体问题

---

## 任务板格式规范

**文件路径**: `planning/codex-tasks.md`

### 文件头

```markdown
# Codex 任务板 - [功能名称]

**创建时间**: YYYY-MM-DD HH:MM:SS
**规范文档**: planning/specs/YYYYMMDD-HHMMSS-[功能名称].md
**总任务数**: N
**预计总工时**: N 小时

---
```

### 任务条目格式

```markdown
## 任务 #001: [任务标题]

**优先级**: P1
**状态**: OPEN
**分配给**: Codex
**创建时间**: YYYY-MM-DD
**预计工时**: N 小时
**依赖任务**: 无 / #XXX
**完成时间**: -
**审计评分**: -
**审计意见**: -

### 任务描述
[详细描述任务内容和背景]

### 技术要求
- [具体技术约束或要求]

### 验收标准
- [ ] [可验证的具体标准]

### 相关文件
- `path/to/file.ext`

---
```

### 字段约束

| 字段 | 允许值 | 说明 |
|------|--------|------|
| 优先级 | P1 / P2 / P3 | P1 最高，Codex 优先选取 |
| 状态 | OPEN / IN_PROGRESS / DONE / VERIFIED / REJECTED / BLOCKED | 状态机见上节 |
| 分配给 | Codex / Claude | 当前责任方 |
| 审计评分 | 0-100 / - | 由 Claude 填写 |

---

## 设计决策记录

### 决策 1：选择纯 Markdown 而非 TypeScript

**背景**：v1.0.0 设计了一套基于 `@claude/skill-sdk` 的 TypeScript 实现，涉及 `DualAICollabSkill` 类、`SkillContext` 接口等。

**问题**：
- `@claude/skill-sdk` 不存在，该 SDK 从未发布
- TypeScript 实现引入了编译步骤、node_modules 依赖、类型定义维护成本
- 用户安装体验差：需要 `npm install`、`tsc` 编译等前置步骤

**决策**：改用纯 Markdown Skill 文件，Claude Code 原生支持加载。

**结果**：
- 安装：复制一个文件到 `~/.claude/skills/` 即可
- 零依赖：不需要 Node.js、npm 或任何外部包
- 逻辑透明：Skill 内容即文档，用户可直接阅读和修改

### 决策 2：自包含设计（用户体验优先）

**背景**：早期版本将 Skill 和辅助脚本分散在多个位置，安装步骤繁琐。

**决策**：将核心逻辑完全内嵌在 `skill/dual-ai-collab.md` 单文件中，辅助脚本作为可选项。

**结果**：
- 用户只需操作一个文件即可完整使用所有功能
- 辅助脚本存在时提升效率，不存在时功能不受影响
- `planning/` 目录由 Skill 自动创建，用户无需手动准备

### 决策 3：awk 任务调度算法

Codex 在读取任务板后，使用以下策略选取下一个任务：

1. 过滤状态为 `OPEN` 的任务
2. 按优先级排序（P1 > P2 > P3）
3. 同优先级内按任务编号升序（即创建顺序）
4. 检查依赖任务是否均已 `VERIFIED`，未满足则跳过
5. 选取第一个满足条件的任务，更新状态为 `IN_PROGRESS`

这一逻辑通过 Bash + awk 实现，无需外部任务调度器，保持工具链简单。

---

## 未来路线图

### v2.2.0（近期）

- 支持多个需求规范文档合并到同一任务板
- 任务依赖关系可视化（ASCII DAG）
- REJECTED 任务自动生成修复指引
- 审计报告模板标准化

### v3.0.0（长期）

- 任务板支持 JSON 格式（同时保留 Markdown 可读性）
- 与 GitHub Issues / Linear 等项目管理工具集成
- HTML 进度报告导出

---

**维护者**: Claude + User
**协议**: MIT
