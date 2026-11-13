# 配置

要改并发或重试上限，或者想把直接执行任务的一部分交给通用子 Agent 时读这份文件。角色和模型不在这里改：它们由 `team set` 和 `team remove` 维护（SKILL.md 的 1.6）。

配置文件是 `.task-management/config.json`，`init` 时写入默认值。主要内容：

```json
{
  "roles": {
    "backend": {
      "droid": "tm-backend",
      "model": "custom:<模型ID>",
      "description": "接口、数据库和业务逻辑",
      "read_only": false
    }
  },
  "parallel": {
    "max_parallel": 2,
    "max_retries": 2
  },
  "execution": {"light": "worker", "medium": "worker", "heavy": "worker"}
}
```

```bash
foreman config show                          # 查看全部配置
foreman config set parallel.max_parallel=3   # 每批最多几个任务，也是同时处于 IN_PROGRESS 的任务数上限
foreman config set parallel.max_retries=3    # 一个任务的失败次数超过它之后变成 BLOCKED
```

- `config set` 只接受 `parallel.max_parallel`、`parallel.max_retries` 和 `execution.light`、`execution.medium`、`execution.heavy`。
- `roles` 不要手改。
- 配置文件损坏时，命令报出文件和出错位置后停下；`init` 和 `config set` 不会用默认值盖掉它，因为里面可能有角色。

## 按复杂度选通用子 Agent

`execution` 一栏只用于一种情况：当前会话直接执行一个任务时，想把其中一部分工作交给通用子 Agent。

```bash
foreman plan-execution 001 --json            # 按任务复杂度给出 droid 和 Task 参数
foreman config set execution.medium=<droid>  # 改某个复杂度对应的 droid
```

复杂度的判定顺序：任务的 `execution_level`（quick → light，normal → medium，heavy → heavy）；任务类型（docs、test → light，feature、bugfix → medium，refactor、architecture → heavy，对应关系在配置的 `complexity_rules.by_type` 里）；预估时间（≤1 小时 light，≤3 小时 medium，更长 heavy）；都没有时是 medium。

这种子 Agent 不固定模型，也没有隔离和模型核对，成果仍由当前会话负责并走正常的验收。要固定模型和隔离，给任务写 `role` 走派发。
