# 🤖 Dual AI Collaboration Framework

> 双 AI 协作框架：Claude（架构师/审计员）+ Codex（开发工程师）= 高效开发

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/yourusername/dual-ai-collab)

---

## 📖 简介

Dual AI Collaboration 是一个创新的 AI 协作框架，通过将 **Claude** 和 **Codex** 两个 AI 的优势结合，实现高效的软件开发流程。

### 核心理念

```
Claude (架构师/审计员)          Codex (开发工程师)
        ↓                              ↓
    需求分析                        代码实现
    架构设计                        功能开发
    任务规划                        Bug 修复
    代码审计                        单元测试
    质量验收                        文档编写
        ↓                              ↓
        └──────→  任务板  ←──────────┘
              (唯一协作接口)
```

### 为什么需要双 AI 协作？

| 单一 AI 开发 | 双 AI 协作 |
|-------------|-----------|
| ❌ 缺乏架构设计 | ✅ Claude 提供架构指导 |
| ❌ 代码质量不稳定 | ✅ Claude 审计保证质量 |
| ❌ 容易偏离需求 | ✅ 任务板明确目标 |
| ❌ 缺乏验收标准 | ✅ 每个任务都有验收标准 |
| ❌ 难以追踪进度 | ✅ 任务状态实时跟踪 |

---

## 🚀 快速开始

### 安装

#### 方式一：克隆到你的项目

```bash
# 克隆仓库（请替换为实际的仓库地址）
git clone https://github.com/your-username/dual-ai-collab.git
cd dual-ai-collab

# 查看所有脚本
ls scripts/
# codex-auto-worker.sh  - Codex 自动工作脚本
# start-codex.sh        - 启动管理脚本
# claude-interview.sh   - 访谈脚本
```

#### 方式二：复制到现有项目

```bash
# 复制脚本到你的项目
cp -r dual-ai-collab/scripts /path/to/your/project/
cp -r dual-ai-collab/templates /path/to/your/project/

# 创建必要的目录
mkdir -p /path/to/your/project/planning/{specs,progress}
mkdir -p /path/to/your/project/logs
```

### 初始化项目

```bash
# 在你的项目目录中
cd /path/to/your/project

# 创建目录结构
mkdir -p planning/{specs,progress} logs scripts

# 复制任务板模板
cp templates/codex-tasks.md planning/

# 设置脚本权限
chmod +x scripts/*.sh
```

---

## 📋 使用指南

### 完整工作流程

#### 0️⃣ Claude 深入访谈（新增！⭐）

在创建任务之前，Claude 会通过 **AskUserQuestion** 工具对你进行深入访谈：

```bash
# 方式 1: 使用脚本
bash scripts/claude-interview.sh "用户认证系统"

# 方式 2: 直接告诉 Claude
"我想开发用户认证系统，请对我进行深入访谈"
```

**访谈内容涵盖**：
- 🎯 功能范围和目标
- 💻 技术实现细节
- 🎨 用户界面与体验
- 🔒 数据和安全
- ⚠️ 边界情况处理
- ⚖️ 权衡取舍
- 🔗 集成和依赖
- ✅ 测试和验收

**访谈特点**：
- ✅ 非显而易见的深入问题
- ✅ 持续多轮直到需求明确
- ✅ 生成详细的需求规范文档
- ✅ 根据规范自动拆分任务

详见：[访谈指南](INTERVIEW-GUIDE.md)

#### 1️⃣ Claude 规划任务

访谈完成后，Claude 会：
1. 生成需求规范文档（`planning/specs/`）
2. 根据规范拆分任务
3. 写入任务板（`planning/codex-tasks.md`）

```bash
# 或手动编辑任务板
vim planning/codex-tasks.md
```

**任务板示例**：

```markdown
## 任务 #001: 实现用户登录功能

**优先级**: P1
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

### 验收标准
- [ ] 表单验证正确
- [ ] API 调用成功
- [ ] Token 正确存储
- [ ] 错误提示友好

### 相关文件
- `src/views/Login.vue`
- `src/api/auth.js`
```

#### 2️⃣ Codex 执行开发

```bash
# Codex 读取任务板
cat planning/codex-tasks.md

# 执行最高优先级的 OPEN 任务
# (编写代码...)

# 完成后更新任务状态为 DONE
```

#### 3️⃣ Claude 审计代码

```bash
# 使用 skill
/dual-ai-collab audit

# 或手动审计
# 1. 读取 DONE 状态的任务
# 2. 检查相关文件
# 3. 生成审计报告
# 4. 更新任务状态（VERIFIED 或 REJECTED）
```

**审计报告示例**：

```markdown
# 代码审计报告

## 任务 #001: 实现用户登录功能

**评分**: 95/100
**状态**: ✅ 通过

### 优点
- ✅ 代码结构清晰
- ✅ 错误处理完善
- ✅ 符合 Vue 3 最佳实践

### 改进建议
- 💡 建议添加单元测试
- 💡 可以优化表单验证逻辑

### 验收标准检查
- [x] 表单验证正确
- [x] API 调用成功
- [x] Token 正确存储
- [x] 错误提示友好

**结论**: 通过验收，任务状态更新为 VERIFIED
```

#### 4️⃣ 查看进度

```bash
# 使用 skill
/dual-ai-collab status

# 或手动查看
cat planning/codex-tasks.md | grep -E "\*\*状态\*\*:|状态:"
```

---

## 📁 项目结构

```
your-project/
├── planning/
│   ├── codex-tasks.md              # 任务板（核心协作文件）
│   └── progress/                   # 进度记录
│       ├── 2026-03-02-audit.md     # 审计报告
│       └── 2026-03-02-summary.md   # 每日总结
├── .dual-ai-collab.yml             # 协作配置
├── src/                            # 源代码
└── ...
```

---

## 🎯 任务板规范

### 任务状态

| 状态 | 说明 | 负责人 |
|------|------|--------|
| `OPEN` | 待开始 | - |
| `IN_PROGRESS` | 进行中 | Codex |
| `DONE` | 已完成（待审计） | Codex |
| `VERIFIED` | 已验收通过 | Claude |
| `REJECTED` | 审计未通过（需修复） | Claude |
| `BLOCKED` | 阻塞中 | - |

### 优先级

| 优先级 | 说明 | 示例 |
|--------|------|------|
| `P1` | 高优先级（紧急且重要） | 核心功能、阻塞性 Bug |
| `P2` | 中优先级（重要但不紧急） | 功能增强、性能优化 |
| `P3` | 低优先级（可延后） | 文档完善、代码重构 |

### 任务模板

```markdown
## 任务 #XXX: [任务标题]

**优先级**: P1/P2/P3
**状态**: OPEN/IN_PROGRESS/DONE/VERIFIED/REJECTED/BLOCKED
**分配给**: Codex
**创建时间**: YYYY-MM-DD
**预计工时**: X小时

### 任务描述
[详细描述任务内容]

### 技术要求
- [技术要求1]
- [技术要求2]

### 验收标准
- [ ] [验收标准1]
- [ ] [验收标准2]

### 相关文件
- `path/to/file1.js`
- `path/to/file2.vue`

---
```

---

## ⚙️ 配置文件

### `.dual-ai-collab.yml`

```yaml
# 双 AI 协作配置

project:
  name: "My Project"
  type: "fullstack"  # frontend/backend/fullstack/mobile

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
  min_score: 90  # 最低通过分数
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

## 🎨 使用场景

### 场景 1: 全栈项目开发

```bash
# Claude 规划前后端任务
/dual-ai-collab plan "开发博客系统，包括前端（Vue）和后端（FastAPI）"

# Codex 先开发后端 API
# Claude 审计后端代码

# Codex 再开发前端
# Claude 审计前端代码

# 集成测试
# Claude 最终验收
```

### 场景 2: 代码重构

```bash
# Claude 分析现有代码，规划重构任务
/dual-ai-collab plan "重构用户模块，提高可维护性"

# Codex 逐步重构
# Claude 审计每个重构任务

# 确保功能不变，质量提升
```

### 场景 3: Bug 修复

```bash
# Claude 分析 Bug，创建修复任务
/dual-ai-collab plan "修复登录失败 Bug"

# Codex 修复 Bug
# Claude 验证修复效果

# 确保 Bug 已解决，无副作用
```

---

## 📊 最佳实践

### 1. 任务拆分原则

✅ **好的任务拆分**：
```markdown
## 任务 #001: 实现用户登录表单
## 任务 #002: 实现登录 API 调用
## 任务 #003: 实现 Token 存储和管理
```

❌ **不好的任务拆分**：
```markdown
## 任务 #001: 实现整个用户认证系统
```

**原则**：
- 每个任务 2-4 小时完成
- 任务之间相对独立
- 明确的验收标准（至少 3 条）

### 2. 审计频率

| 任务优先级 | 审计频率 |
|-----------|---------|
| P1 | 每个任务完成后立即审计 |
| P2 | 批量审计（3-5 个任务） |
| P3 | 阶段性审计（每周） |

### 3. 沟通机制

- ✅ 使用任务板作为唯一真相来源
- ✅ 审计报告详细记录问题和建议
- ✅ 定期同步进度（每日/每周）
- ✅ 重要决策记录在 `planning/progress/` 中

### 4. 质量保证

- ✅ 代码审计评分 ≥ 90 分才能通过
- ✅ 所有验收标准必须满足
- ✅ 关键功能需要测试覆盖
- ✅ 安全性问题零容忍

---

## 🔧 高级功能

### 自动化工作流

创建 `scripts/auto-collab.sh`：

```bash
#!/bin/bash
# 自动化协作流程

while true; do
  # Codex 执行下一个任务
  echo "🔧 Codex 开始开发..."
  /dual-ai-collab dev

  # 检查是否还有任务
  if [ $? -ne 0 ]; then
    echo "✅ 所有任务已完成！"
    break
  fi

  # Claude 审计代码
  echo "🔍 Claude 开始审计..."
  /dual-ai-collab audit

  # 等待一段时间
  sleep 5
done
```

### 并行开发

```bash
# 启动多个 Codex 实例并行开发不同模块
/dual-ai-collab dev --module frontend &
/dual-ai-collab dev --module backend &
/dual-ai-collab dev --module database &
```

### 持续集成

```yaml
# .github/workflows/dual-ai-collab.yml
name: Dual AI Collaboration

on:
  push:
    branches: [ main ]

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run Claude Audit
        run: /dual-ai-collab audit --ci
```

---

## 📈 成功案例

### 案例 1: Youtu-GraphRAG 项目

**项目规模**：
- 前端：Vue 3 + Element Plus（9个页面，8个组件）
- 后端：FastAPI + Neo4j（11个 API 模块）
- 开发时间：3 天

**协作模式**：
- Claude：设计架构、制定规范、代码审计
- Codex：实现所有代码
- 结果：前端审计评分 97/100，后端测试覆盖率 100%

**关键数据**：
- 任务总数：23 个
- 审计通过率：95.7%（22/23）
- 平均任务完成时间：2.3 小时
- 代码质量评分：96/100

---

## 🤝 贡献指南

欢迎贡献！请遵循以下步骤：

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

### 贡献方向

- 📝 完善文档和示例
- 🐛 修复 Bug
- ✨ 添加新功能
- 🎨 改进 UI/UX
- 🧪 添加测试用例

---

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

## 🙏 致谢

- [Claude](https://www.anthropic.com/claude) - 强大的 AI 助手
- [OpenAI Codex](https://openai.com/blog/openai-codex) - 优秀的代码生成模型
- [oh-my-claudecode](https://github.com/cyanheads/oh-my-claudecode) - OMC 框架

---

## 📞 联系方式

- GitHub Issues: [提交问题](https://github.com/your-username/dual-ai-collab/issues)（请替换为实际仓库地址）
- 项目文档: 查看本仓库的 README 和 docs 目录

---

## 🗺️ 路线图

### v1.0.0 (当前版本)
- ✅ 基础协作框架
- ✅ 任务板管理
- ✅ 代码审计功能
- ✅ 进度跟踪

### v1.1.0 (计划中)
- [ ] Web UI 界面
- [ ] 实时协作看板
- [ ] 统计报表
- [ ] 团队协作支持

### v2.0.0 (未来)
- [ ] 多 AI 模型支持
- [ ] 自动化测试集成
- [ ] CI/CD 集成
- [ ] 云端协作平台

---

**⭐ 如果这个项目对你有帮助，请给个 Star！**

---

<div align="center">
  Made with ❤️ by Claude + User
</div>
