# 任务板 + OMC 多模型协作集成方案

## 🎯 核心理念

将**你的任务板模式**（Claude 规划 + Codex 开发 + Claude 审计）与 **OMC 的多模型协作**结合，实现：

```
Claude (架构师/审计员)
    ↓ 创建任务板 + 定义角色
任务板 (planning/codex-tasks.md) + 角色配置 (AGENTS.md)
    ↓ OMC 读取并分配
OMC 多模型团队 (Codex/Gemini/Claude workers)
    ↓ 按角色并行执行
Claude (审计员)
    ↓ 审计验收，更新任务状态
```

---

## 📋 完整工作流程

### 阶段 1：Claude 规划（架构师模式）

#### 1.1 创建任务板

```markdown
# planning/codex-tasks.md

## 任务 #001: 实现用户登录 API

**优先级**: P1
**状态**: OPEN
**分配给**: Codex (后端开发)
**角色**: 后端架构师
**创建时间**: 2026-03-02
**预计工时**: 2小时

### 任务描述
实现用户登录 API，包括 JWT 认证、密码验证、Token 生成。

### 技术要求
- 使用 FastAPI
- JWT Token 认证
- 密码 bcrypt 加密
- Redis 存储 Token

### 验收标准
- [ ] API 接口正确实现
- [ ] JWT Token 生成和验证
- [ ] 密码加密存储
- [ ] 单元测试覆盖率 > 80%
- [ ] API 文档完整

### 相关文件
- `api/v1/auth.py`
- `services/auth_service.py`
- `tests/test_auth.py`

---

## 任务 #002: 实现登录页面 UI

**优先级**: P1
**状态**: OPEN
**分配给**: Gemini (前端开发)
**角色**: 前端设计师
**创建时间**: 2026-03-02
**预计工时**: 3小时

### 任务描述
设计并实现登录页面，包括表单验证、动画效果、响应式布局。

### 技术要求
- 使用 Vue 3 Composition API
- Element Plus 组件库
- 粒子动画背景
- 毛玻璃效果

### 验收标准
- [ ] 表单验证正确
- [ ] 动画流畅
- [ ] 响应式布局
- [ ] 无障碍访问
- [ ] 组件文档完整

### 相关文件
- `frontend-vue/src/views/Login.vue`
- `frontend-vue/src/api/auth.js`

---
```

#### 1.2 创建角色配置

```markdown
# AGENTS.md

## 项目角色定义

### Codex - 后端架构师

**职责**：
- 实现所有后端 API
- 设计数据库模型
- 编写单元测试
- 性能优化

**技术栈**：
- Python 3.11 + FastAPI
- PostgreSQL + SQLAlchemy
- Redis
- Pytest

**工作规范**：
- 遵循 RESTful API 设计
- 所有接口需要单元测试
- 代码覆盖率 > 80%
- 使用 Type Hints
- 遵循 PEP 8 规范

**任务读取规则**：
- 读取 `planning/codex-tasks.md`
- 执行 `分配给: Codex` 且 `状态: OPEN` 的任务
- 按优先级顺序执行（P1 > P2 > P3）

---

### Gemini - 前端设计师

**职责**：
- 设计 UI 组件
- 实现交互动画
- 优化用户体验
- 编写组件文档

**技术栈**：
- Vue 3 + TypeScript
- Element Plus
- SCSS
- Vitest

**设计规范**：
- 深色主题 + 毛玻璃效果
- 渐变色：#667eea → #764ba2
- 圆角：12px (卡片), 8px (按钮)
- 动画：cubic-bezier(0.4, 0, 0.2, 1)

**任务读取规则**：
- 读取 `planning/codex-tasks.md`
- 执行 `分配给: Gemini` 且 `状态: OPEN` 的任务
- 按优先级顺序执行（P1 > P2 > P3）

---

### Claude - 质量保证

**职责**：
- 代码审查
- 集成测试
- 性能测试
- 文档审核

**审查标准**：
- 代码质量 > 90分
- 安全漏洞零容忍
- 性能指标达标
- 文档完整清晰

**审查流程**：
- 读取 `状态: DONE` 的任务
- 检查验收标准是否满足
- 生成审计报告
- 更新任务状态（VERIFIED 或 REJECTED）

---
```

---

### 阶段 2：OMC 执行（多模型协作）

#### 2.1 方式一：使用 omc-teams（推荐）

```bash
# Claude 调用 omc-teams
/omc-teams 2:codex "
读取 planning/codex-tasks.md 和 AGENTS.md
按照后端架构师角色工作
执行所有分配给 Codex 且状态为 OPEN 的 P1 任务
完成后更新任务状态为 DONE
"

/omc-teams 2:gemini "
读取 planning/codex-tasks.md 和 AGENTS.md
按照前端设计师角色工作
执行所有分配给 Gemini 且状态为 OPEN 的 P1 任务
完成后更新任务状态为 DONE
"
```

**OMC 内部处理**：
```javascript
// OMC 自动分解任务
mcp__team__omc_run_team_start({
  "teamName": "auth-module",
  "agentTypes": ["codex", "codex"],
  "tasks": [
    {
      "subject": "任务 #001: 实现用户登录 API",
      "description": `
角色：后端架构师
任务板：planning/codex-tasks.md #001

任务描述：
实现用户登录 API，包括 JWT 认证、密码验证、Token 生成。

技术要求：
- 使用 FastAPI
- JWT Token 认证
- 密码 bcrypt 加密
- Redis 存储 Token

验收标准：
- API 接口正确实现
- JWT Token 生成和验证
- 密码加密存储
- 单元测试覆盖率 > 80%
- API 文档完整

相关文件：
- api/v1/auth.py
- services/auth_service.py
- tests/test_auth.py

完成后：
1. 更新任务板状态为 DONE
2. 提交代码
3. 生成完成报告
      `
    }
  ],
  "cwd": "/home/hn/projects/youtu-graphrag-main"
})
```

#### 2.2 方式二：使用 CCG（自动分工）

```bash
# Claude 调用 CCG
/ccg "
读取 planning/codex-tasks.md
自动分配任务：
- 后端任务 → Codex
- 前端任务 → Gemini
并行执行所有 OPEN 状态的 P1 任务
"
```

---

### 阶段 3：Claude 审计（质量保证）

#### 3.1 读取完成的任务

```bash
# Claude 读取任务板
cat planning/codex-tasks.md | grep "状态: DONE"
```

#### 3.2 审计代码

```bash
# 对每个 DONE 任务进行审计
/code-review "
审计任务 #001: 实现用户登录 API
相关文件：
- api/v1/auth.py
- services/auth_service.py
- tests/test_auth.py

审计标准：
- 代码质量
- 安全性
- 性能
- 测试覆盖率
"
```

#### 3.3 生成审计报告

```markdown
# planning/progress/2026-03-02-audit.md

## 任务 #001: 实现用户登录 API

**审计时间**: 2026-03-02 15:30
**审计人员**: Claude
**开发人员**: Codex

### 审计结果

**评分**: 95/100
**状态**: ✅ 通过

### 代码质量 (30/30)
- ✅ 代码结构清晰
- ✅ 命名规范
- ✅ 注释适当
- ✅ 无冗余代码

### 功能完整性 (25/25)
- ✅ API 接口正确实现
- ✅ JWT Token 生成和验证
- ✅ 密码加密存储
- ✅ 错误处理完善

### 测试覆盖率 (20/20)
- ✅ 单元测试覆盖率 85%
- ✅ 所有边界情况测试
- ✅ 错误场景测试

### 安全性 (10/10)
- ✅ 密码 bcrypt 加密
- ✅ JWT Token 安全
- ✅ 输入验证完善

### 性能 (10/10)
- ✅ 响应时间 < 100ms
- ✅ Redis 缓存使用合理

### 改进建议
- 💡 可以添加 Token 刷新机制
- 💡 建议添加登录失败次数限制

### 验收标准检查
- [x] API 接口正确实现
- [x] JWT Token 生成和验证
- [x] 密码加密存储
- [x] 单元测试覆盖率 > 80%
- [x] API 文档完整

**结论**: 通过验收，任务状态更新为 VERIFIED
```

#### 3.4 更新任务状态

```markdown
# planning/codex-tasks.md

## 任务 #001: 实现用户登录 API

**优先级**: P1
**状态**: VERIFIED ✅  # 从 DONE 更新为 VERIFIED
**分配给**: Codex (后端开发)
**角色**: 后端架构师
**创建时间**: 2026-03-02
**完成时间**: 2026-03-02 15:30
**审计评分**: 95/100

...
```

---

## 🔧 实现细节

### 1. 任务板格式增强

在你的任务板模板中添加 `分配给` 和 `角色` 字段：

```markdown
## 任务 #XXX: [任务标题]

**优先级**: P1/P2/P3
**状态**: OPEN/IN_PROGRESS/DONE/VERIFIED/REJECTED/BLOCKED
**分配给**: Codex/Gemini/Claude  # 新增
**角色**: 后端架构师/前端设计师/质量保证  # 新增
**创建时间**: YYYY-MM-DD
**预计工时**: X小时
```

### 2. OMC 任务读取脚本

创建一个辅助脚本，让 OMC 更容易读取任务板：

```python
# scripts/read_tasks.py

import re
from pathlib import Path

def read_task_board(task_board_path, assignee=None, status="OPEN"):
    """读取任务板，筛选特定分配人和状态的任务"""

    with open(task_board_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 解析任务
    tasks = []
    task_pattern = r'## 任务 #(\d+): (.+?)\n\n(.+?)(?=\n## 任务|$)'

    for match in re.finditer(task_pattern, content, re.DOTALL):
        task_id = match.group(1)
        task_title = match.group(2)
        task_body = match.group(3)

        # 提取字段
        priority = re.search(r'\*\*优先级\*\*: (P\d)', task_body)
        task_status = re.search(r'\*\*状态\*\*: (\w+)', task_body)
        task_assignee = re.search(r'\*\*分配给\*\*: (\w+)', task_body)
        role = re.search(r'\*\*角色\*\*: (.+)', task_body)

        # 筛选
        if task_status and task_status.group(1) == status:
            if assignee is None or (task_assignee and task_assignee.group(1) == assignee):
                tasks.append({
                    'id': task_id,
                    'title': task_title,
                    'priority': priority.group(1) if priority else 'P3',
                    'status': task_status.group(1),
                    'assignee': task_assignee.group(1) if task_assignee else None,
                    'role': role.group(1) if role else None,
                    'body': task_body
                })

    # 按优先级排序
    priority_order = {'P1': 1, 'P2': 2, 'P3': 3}
    tasks.sort(key=lambda x: priority_order.get(x['priority'], 999))

    return tasks

def format_task_for_omc(task):
    """格式化任务为 OMC 可读格式"""
    return f"""
任务 #{task['id']}: {task['title']}

优先级: {task['priority']}
角色: {task['role']}

{task['body']}

完成后：
1. 更新任务板状态为 DONE
2. 提交代码
3. 生成完成报告
"""

if __name__ == '__main__':
    import sys

    assignee = sys.argv[1] if len(sys.argv) > 1 else None
    tasks = read_task_board('planning/codex-tasks.md', assignee=assignee)

    for task in tasks:
        print(format_task_for_omc(task))
        print('---')
```

**使用方式**：
```bash
# 读取分配给 Codex 的任务
python scripts/read_tasks.py Codex

# 读取所有 OPEN 任务
python scripts/read_tasks.py
```

### 3. OMC 调用示例

```bash
# Claude 执行
/omc-teams 2:codex "$(python scripts/read_tasks.py Codex)"
```

---

## 🎯 完整示例

### 示例：开发用户认证系统

#### Step 1: Claude 规划

```bash
# 1. 创建任务板
vim planning/codex-tasks.md

# 2. 创建角色配置
vim AGENTS.md

# 3. 创建任务读取脚本
vim scripts/read_tasks.py
```

#### Step 2: OMC 执行

```bash
# 并行执行
/omc-teams 2:codex "$(python scripts/read_tasks.py Codex)"
/omc-teams 2:gemini "$(python scripts/read_tasks.py Gemini)"
```

#### Step 3: Claude 审计

```bash
# 审计所有 DONE 任务
for task in $(grep "状态: DONE" planning/codex-tasks.md); do
  /code-review "审计任务 $task"
done

# 生成审计报告
vim planning/progress/2026-03-02-audit.md

# 更新任务状态
vim planning/codex-tasks.md
```

---

## 📊 优势对比

| 维度 | 纯任务板模式 | 集成 OMC 模式 |
|------|-------------|--------------|
| **规划** | ✅ Claude 手动规划 | ✅ Claude 手动规划 |
| **执行** | ⚠️ Codex 单线程 | ✅ 多模型并行 |
| **审计** | ✅ Claude 审计 | ✅ Claude 审计 |
| **并行度** | 1 | N (可配置) |
| **角色分工** | ⚠️ 手动分配 | ✅ 自动分配 |
| **状态管理** | ✅ 任务板 | ✅ 任务板 + OMC 状态 |

---

## 💡 最佳实践

1. **任务拆分**：每个任务 2-4 小时，独立可测试
2. **角色明确**：在 AGENTS.md 中详细定义每个角色
3. **并行执行**：独立任务使用 omc-teams 并行
4. **审计严格**：所有 DONE 任务必须经过 Claude 审计
5. **状态同步**：OMC 完成后及时更新任务板状态

---

## 🚀 下一步

1. 将这个集成方案添加到你的 GitHub 仓库
2. 创建示例项目演示完整流程
3. 编写自动化脚本简化操作
4. 在实际项目中测试和优化

这样你就完美结合了任务板管理和 OMC 多模型协作的优势！🎉
