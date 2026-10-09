# Web UI 使用指南

## 快速开始

### 1. 安装依赖

```bash
# 安装 Flask（如果还未安装）
python3 -m pip install --user Flask
```

### 2. 启动服务

```bash
cd /Users/hanning/dual-ai-collab
python3 web_server.py 5001
```

### 3. 访问界面

打开浏览器访问：http://localhost:5001

## 多项目管理

页面顶部选择当前项目，使用“登记项目”填写现有目录的绝对路径和项目名称。登记不会创建或搬迁项目文件；没有任务板的目录显示为空列表。

- 项目地址：`/project/{project_id}/tasks`，详情：`/project/{project_id}/task/{task_id}`。
- 同号任务在不同项目中相互独立，返回列表会保留当前项目。
- 默认注册表：工具仓库的 `.dual-ai-collab/projects.json`。启动前可用 `DUAL_AI_PROJECTS_FILE=/absolute/path/projects.json` 指定其他位置。
- 重启服务会保留登记结果；已丢失的项目目录在选择器中标记为不可用。
- 原 `/api/tasks`、`/api/board` 和 `/task/{id}` 继续指向默认项目。
- “已完成”统计和筛选只计入具有有效集成确认的任务，旧 DONE / VERIFIED 显示“待确认集成”。手动更新状态不等于集成确认。

本版不提供网页设计追问或模型调用，不会因打开页面、登记项目或切换项目启动模型 CLI。模型执行仍沿用现有项目内 CLI 工作流。

新增接口：

```text
GET  /api/projects
POST /api/projects                       {"name": "项目名称", "path": "/absolute/path"}
GET  /api/projects/{id}/tasks
GET  /api/projects/{id}/tasks/{task_id}
PUT  /api/projects/{id}/tasks/{task_id}    {"status": "IN_PROGRESS"}
GET  /api/projects/{id}/board
GET  /api/projects/{id}/history
```

本地服务保持绑定 `127.0.0.1`。更换项目根目录不会改变服务进程工作目录。升级后需要重启 Web 服务，再刷新页面。

## 功能说明

### 主页 - 任务列表

**URL**: http://localhost:5001

**功能**：
- 📊 顶部统计面板：总任务、进行中、待审查、已完成
- 🎯 任务筛选：按状态筛选（全部/待办/进行中/待审查/已完成）
- 📝 任务列表：显示所有任务的基本信息
- 🔄 自动刷新：每 5 秒自动更新任务状态

**操作**：
- 点击任务卡片 → 进入任务详情页
- 点击筛选按钮 → 按状态过滤任务

### 任务详情页

**URL**: http://localhost:5001/task/{task_id}

**功能**：
- 📋 完整任务信息：描述、优先级、预计时间、依赖任务
- ✅ 验收标准：列出所有验收条件
- 📁 相关文件：显示任务涉及的文件
- 🔄 状态更新：下拉选择新状态并更新
- 🔄 自动刷新：每 5 秒自动更新

**操作**：
1. 选择新状态（下拉框）
2. 点击"更新状态"按钮
3. 等待更新完成（显示成功/失败消息）

## API 端点

### GET /api/tasks
获取所有任务列表

**响应**：
```json
{
  "success": true,
  "tasks": [...]
}
```

### GET /api/tasks/{id}
获取单个任务详情

**响应**：
```json
{
  "success": true,
  "task": {...}
}
```

### PUT /api/tasks/{id}
更新任务状态

**请求体**：
```json
{
  "status": "IN_PROGRESS"
}
```

**响应**：
```json
{
  "success": true,
  "message": "任务 001 状态已更新为 IN_PROGRESS"
}
```

### GET /api/board
获取任务板统计信息

**响应**：
```json
{
  "success": true,
  "stats": {
    "total": 5,
    "by_status": {...},
    "completed": 0,
    "completion_rate": 0.0
  }
}
```

### GET /api/history
获取执行历史记录

**响应**：
```json
{
  "success": true,
  "history": [...]
}
```

## 技术细节

### 架构
- **后端**：Flask 2.3+
- **前端**：原生 HTML + CSS + JavaScript
- **数据**：`planning/tasks.json`

### 自动刷新机制
- 页面每 5 秒自动调用 API 刷新数据
- 页面失去焦点时停止刷新（节省资源）
- 页面重新获得焦点时恢复刷新

### 响应式设计
- 支持桌面浏览器（Chrome/Firefox/Safari）
- 移动端基本适配

## 故障排查

### 端口被占用
如果 5001 端口被占用，使用其他端口：
```bash
python3 web_server.py 8080
```

### 任务列表为空
检查 `planning/tasks.json` 是否存在且格式正确

### API 返回错误
查看终端中的 Flask 日志输出

### 页面不刷新
- 检查浏览器控制台是否有 JavaScript 错误
- 确认 API 端点正常响应

## 与 CLI 配合使用

Web UI 和 CLI 共享同一个数据文件，可以配合使用：

```bash
# CLI 创建任务
python3 skill/scripts/cli.py templates create feature 006 --add

# Web UI 中立即可见新任务（刷新后）

# Web UI 更新状态后，CLI 也能看到
python3 skill/scripts/cli.py board show
```

## 后续扩展

**计划中的功能**（未实现）：
- 任务创建和编辑
- WebSocket 实时推送
- 执行日志实时查看
- 依赖关系可视化图
- 拖拽式任务管理

这些功能可以根据实际需求逐步添加。
