# 沙箱限制与 blocked 处理

本文描述本项目执行器的处理方式。实际文件和网络能力取决于所选后端、CLI 配置与宿主环境，不能仅凭沙箱名称断言“所有环境都禁止网络或安装”。

## 模式选择

| 模式 | 本项目行为 | 适用场景 |
| --- | --- | --- |
| `read-only` | 给 Codex 指定只读沙箱 | 阅读、检查与规划 |
| `workspace-write` | 给 Codex 指定工作区写入沙箱 | 在指定目录实现任务；不保证能联网或写入系统包目录 |
| `danger-full-access` | 请求 Codex 全访问模式 | 仅在明确了解执行环境和权限范围时显式选择；宿主约束仍可能存在 |
| `provider-default` | 使用适配器自身权限策略 | 原生 Claude CLI；app-server 不支持此值，不代表已经获得额外权限 |

app-server 使用 `approvalPolicy=never`。执行器请求额外权限或人工输入时，当前实现拒绝并记录请求，最终标记 blocked；不会自动扩大权限或安装软件。

## 依赖预检与预安装

任务的 `dependencies` 仍是任务编号依赖。软件依赖在 `planning/tasks.json` 中单独声明：

```json
{
  "id": "001",
  "dependencies": "无",
  "runtime_dependencies": {
    "python": ["Flask>=2.3", "flask-cors"],
    "system": ["git"],
    "python_executable": "/absolute/path/to/venv/bin/python"
  }
}
```

`run start` 在启动 worker 前检查，continue / repair 也检查。缺失依赖输出 WARNING 到 stderr，stdout 仍为命令的 JSON 结果；默认不阻止启动，不自动安装。Python 包通过指定解释器的发行包元数据检查版本，系统工具检查 PATH。省略解释器时检查启动 CLI 的 Python。依赖约束解析需要项目声明的 `packaging` 包，仅支持包名和版本约束，不展开 extras、URL 或环境标记。

应在运行环境中预先安装所需依赖，例如用指定虚拟环境的 Python 执行 `-m pip install ...`。确认网络和目录可写后再执行安装。隔离 worktree 不会复制被忽略的 `.venv`；可显式指定已准备好的解释器绝对路径，并在任务指令与验收命令中使用它。预检不是沙箱内部探测，也不能保证模型会使用该解释器。

## blocked 后怎样继续

```bash
python3 skill/scripts/cli.py run watch 001
python3 skill/scripts/cli.py board show --verbose
python3 skill/scripts/cli.py history
```

`watch` 默认每 5 秒显示状态、turn 和最近事件，成功返回 0，失败、blocked、stopped 或 interrupted 返回 1；Ctrl-C 仅停止监控，返回 130。不会假造进度百分比。先解决依赖、权限或任务描述问题，再使用 `run continue 001 "环境已修复，请继续"`；这不会偷偷切换沙箱。

如果实现已完成、执行器只是无法在自身环境验收，可以在合适环境实际测试后记录人工验收：

```bash
python3 skill/scripts/cli.py run verify-manual 001 --list
# 示例有两条标准；必须先实际检查每条，再确认对应编号：
python3 skill/scripts/cli.py run verify-manual 001 \
  --confirm 1 --confirm 2 --note "记录测试环境、操作与结果"
python3 skill/scripts/cli.py board review 001 --force \
  --decision approved --note "审查过实现和手动验收证据"
```

交互终端不传 `--confirm` 时会逐条询问；非交互调用必须显式列出全部编号。未全部确认、标准为空、进程仍在运行、确认期间任务或轮次发生变化都会拒绝写入。报告保存于 `.dual-ai-collab/manual-reports`，记录每条标准、说明、任务指纹、run_id 和原执行状态。

`--force` 仅允许已手动验收的 blocked 任务进入审查，不能跳过验收、不能把 failed/running 强行改为成功。执行记录仍为 blocked。任务通过审查后还需实际集成；`board integrate` 仍在目标仓库执行自动验收，满足后才解锁依赖。

## 超时与历史

app-server 单轮默认超时按任务优先级取值：P0 1800 秒、P1 1200 秒、P2 600 秒、P3 300 秒，其他优先级 600 秒。优先级不是工作量估计，长任务应显式设置合适时间。

配置优先顺序：`run start --timeout` > `app_server_turn_timeout` > `app_server_priority_timeouts` 中对应优先级 > 内置默认。continue / repair 沿用已记录超时。超时请求中断并关闭服务，记为 blocked / timeout，不自动重试。协议请求超时仍可能是 failed，不与单轮执行超时混淆。

历史保留 blocked 的原始原因；超时与协议审批请求有确定分类，模型文本中的依赖缺失、沙箱限制、权限拒绝分类是关键词提示，无法识别则为 unknown。用 `history` 查看阻塞次数和类别分布，不把手动验收算成执行成功。
