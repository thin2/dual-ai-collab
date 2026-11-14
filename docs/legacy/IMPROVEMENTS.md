# Dual AI Collab 改进总结（旧版）

> **旧版文档，不再更新。** 本文讲的是旧版 dual-ai-collab（代码在 `skill/`），其中的命令和路径不适用于当前的 foreman 技能。当前版本的说明见 [foreman/README.md](../../foreman/README.md)。

## 1. 僵尸进程检测修复 ✅

**问题**: Worker 进程退出后变成僵尸进程，`os.kill(pid, 0)` 对僵尸进程返回成功，导致状态检测错误。

**解决方案**:
- `platform_utils.py:is_process_running()` 增加僵尸进程检测
- 使用 `ps -p PID -o stat=` 检查进程状态
- 僵尸进程（状态包含 'Z'）被视为已终止

**测试**: `tests/test_run_task_pytest.py::test_start_end_to_end_with_stub_codex`

---

## 2. 性能优化 ✅

**问题**: `is_process_running` 每次调用都执行 `ps` 命令，高频调用时开销大。

**解决方案**:
- 实现两阶段检测：先用轻量的 `os.kill(pid, 0)`，仅在成功时才调用 `ps`
- 添加短期缓存（0.5秒 TTL），避免重复调用
- Unix 和 Windows 平台都实现了缓存机制

**性能提升**:
- 不存在的进程检测：仅需 `os.kill`，无需 `ps`
- 存在的进程检测：0.5秒内重复调用直接返回缓存结果

**测试**: `tests/test_run_task_pytest.py` - 性能测试验证缓存有效性

---

## 3. 错误处理改进 ✅

**问题**: Worker 崩溃时只有退出码，缺少详细错误信息。

**解决方案**:
- 添加 `.error.json` 文件记录崩溃详情
- 包含：错误类型、消息、时间戳、进程信息
- `status` 命令返回 `error_details` 字段
- Worker 捕获所有异常并记录详细信息

**错误信息结构**:
```json
{
  "error_type": "OSError",
  "error_message": "...",
  "timestamp": "2026-10-03T...",
  "pid": 12345,
  "exit_code": 127
}
```

**测试**: `tests/test_error_handling.py`

---

## 4. 可观测性增强 ✅

**问题**: 缺少结构化日志和性能指标，难以追踪和分析。

**解决方案**:
- 实现结构化日志系统（`structured_logging.py`）
- 支持事件日志、性能指标、耗时跨度
- 所有关键操作添加日志点：
  - `task_start.started` / `task_start.completed`
  - `worker_spawned`
  - `worker_execution.started` / `worker_execution.completed`
  - `codex_execution.started` / `codex_execution.completed`
- 添加性能指标：
  - `prompt_size` - 提示词大小
  - `task_start_duration` - 启动耗时
  - `worker_duration` - Worker 总耗时
  - `codex_duration` - Codex 执行耗时

**日志格式**:
```json
{
  "timestamp": "2026-10-03T17:07:01.650266+00:00",
  "level": "INFO",
  "event": "task_start.started",
  "task_num": "001",
  "backend": "direct"
}
```

**测试**: `tests/test_structured_logging.py`

---

## 5. 配置管理改进 ✅

**问题**: 配置硬编码，缺少灵活性和扩展性。

**解决方案**:
- 实现分层配置系统（`config.py`）
- 配置优先级：环境变量 > 配置文件 > 默认值
- 支持的配置项：
  - `default_backend` - 默认执行后端
  - `default_sandbox` - 默认沙箱模式
  - `log_level` - 日志级别
  - `process_check_cache_ttl` - 进程检测缓存 TTL
- 配置文件：`.dual-ai-collab/config.json`
- 环境变量前缀：`DUAL_AI_`

**配置示例**:
```json
{
  "default_backend": "direct",
  "default_sandbox": "workspace-write",
  "log_level": "INFO",
  "process_check_cache_ttl": 0.5
}
```

**环境变量**:
```bash
export DUAL_AI_DEFAULT_SANDBOX=read-only
export DUAL_AI_LOG_LEVEL=DEBUG
```

**测试**: `tests/test_config.py`

---

## 测试覆盖

**总测试数**: 36 个
**通过率**: 100%

**新增测试**:
- `tests/test_config.py` - 配置管理测试（4个）
- `tests/test_error_handling.py` - 错误处理测试（2个）
- `tests/test_structured_logging.py` - 结构化日志测试（3个）

**改进的测试**:
- `tests/test_run_task_pytest.py` - 端到端测试现在验证僵尸进程检测

---

## 向后兼容性

所有改进保持向后兼容：
- 默认行为不变
- 现有 API 签名保持兼容
- 配置系统使用合理的默认值
- 结构化日志为可选功能

---

## 使用建议

1. **生产环境**:
   - 设置 `log_level=INFO` 获取关键事件
   - 使用配置文件统一管理多个环境
   - 启用错误详情收集以便故障排查

2. **开发环境**:
   - 设置 `log_level=DEBUG` 获取详细日志
   - 使用环境变量快速切换配置
   - 查看 `.error.json` 文件诊断崩溃

3. **性能监控**:
   - 收集结构化日志中的 metric 事件
   - 分析 `duration_seconds` 指标识别瓶颈
   - 监控 `prompt_size` 避免超大提示词

---

## 后续改进方向

1. **更多可观测性**:
   - 添加内存使用监控
   - 支持分布式追踪
   - 导出指标到 Prometheus

2. **更灵活的配置**:
   - 支持任务级别配置覆盖
   - 配置验证和模式定义
   - 热重载配置文件

3. **更好的错误处理**:
   - 自动重试机制
   - 错误分类和聚合
   - 错误通知集成

4. **性能进一步优化**:
   - 使用 psutil 替代 ps 命令
   - 异步进程监控
   - 批量状态查询优化
