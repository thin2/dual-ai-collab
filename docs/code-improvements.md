# 实测改进清单与实现结果

本清单来自 Web UI 开发实测，以下八项已实现。验证覆盖 CLI、模拟 app-server 协议和现有 Web API 回归；没有重新调用真实 Claude / Codex 或安装任务依赖。

| 优先级 | 实测问题 | 实现 |
| --- | --- | --- |
| P0 | blocked 无法进入审查 | `board review --force` 允许已手动验收的 blocked 任务；不跳过验收、不改写执行结果 |
| P0 | 无法记录手动验收 | `run verify-manual` 逐条确认验收标准，生成独立报告，进入 AWAITING_REVIEW |
| P1 | 执行中才发现依赖缺失 | `runtime_dependencies` 声明软件依赖，start / continue / repair 预检，stderr 提示缺失项 |
| P1 | 外部 Monitor 解析 JSON 不稳定 | `run watch` 提供纯文本轮询，显示状态、turn 与最近事件，终态退出 |
| P2 | 沙箱限制不清晰 | [沙箱与 blocked 处理](sandbox-limitations.md) 说明权限模式、预安装、恢复和手动验收 |
| P2 | 面板下一步提示不具体 | `board show --verbose` 展示执行时长、阻塞原因及具体命令 |
| P3 | 超时不易定位 | 按优先级提供可覆盖的默认时间，单轮超时记 blocked / timeout，保留原因 |
| P3 | 历史缺少阻塞分析 | 保留原始原因和类别，`history` 展示阻塞次数、类别分布与最近原因 |

## 使用示例

```bash
python3 skill/scripts/cli.py run watch 001
python3 skill/scripts/cli.py board show --verbose
python3 skill/scripts/cli.py run verify-manual 001 --list
# 实际检查每条标准后，逐项确认；以下示例有两条：
python3 skill/scripts/cli.py run verify-manual 001 --confirm 1 --confirm 2 --note "测试环境与结果"
python3 skill/scripts/cli.py board review 001 --force --decision approved --note "代码与验收审查结论"
python3 skill/scripts/cli.py history
```

非交互环境不会默认确认。执行仍是 blocked，审查与最终集成是独立步骤。软件依赖使用新字段，不覆盖原有任务依赖；预检只提示，不自动联网安装或扩大执行权限。

## 代码与验证

- `skill/scripts/run_support.py`：依赖预检、手动验收和 watch。
- `skill/scripts/run_diagnostics.py`：超时策略、阻塞分类、下一步命令。
- `skill/scripts/run_task.py`、`session_backend.py`：命令接入和 worker 状态处理。
- `skill/scripts/task_board.py`、`task_history.py`：审查凭据、详细面板、阻塞历史。
- `tests/test_run_improvements.py`：逐项确认、force 边界、任务变更失效、版本检查、监控容错、超时配置与分类。
- `tests/test_session_backend.py`：模拟协议下的实际超时和历史落盘。
- `tests/test_web_server.py`：现有 Web API 与持久化回归。

验证结果：117 项 Python 测试、97 项 Shell 检查通过；Python 编译与 `git diff --check` 通过。
