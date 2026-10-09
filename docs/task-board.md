# 任务面板与交付流程

在项目根目录执行 `python3 /path/to/skill/scripts/cli.py`（下文简称 `<cli>`）。`planning/tasks.json` 保存任务定义，Markdown 是同步视图。`board show` 将运行记录、验收报告、审查与集成凭据聚合成只读面板。

```bash
python3 <cli> board show
python3 <cli> board show --json
python3 <cli> board context 001 --output /tmp/task-001.md
python3 <cli> run start 001 "实现任务" --backend app-server \
  --context-task-file planning/tasks.json --workdir /path/to/source --isolate
python3 <cli> run status 001
python3 <cli> run complete 001
python3 <cli> board review 001 --decision approved --note "已检查实现、边界情况和验收报告"
# 在原仓库集成代码并提交后：
python3 <cli> board integrate 001 --target /path/to/source --commit COMMIT_SHA \
  --note "确认该提交包含任务 001 的改动"
```

任务流程：`OPEN → IN_PROGRESS → AWAITING_REVIEW → AWAITING_INTEGRATION → DONE`。执行状态独立显示；运行成功或隔离目录验收通过均不解锁依赖。`board review --decision rejected` 表示退回修复，使用 `run continue` 后重新验收。

`board integrate` 不合并、不提交代码。它要求目标 Git 工作区干净、指定提交已进入 HEAD 历史，并在目标目录重新执行全部验收命令。隔离任务的目标必须是原仓库。审查者负责核对提交包含任务改动；工具不能证明代码语义等价。非 Git 项目可以执行和审查，暂不能自动确认集成。

集成记录绑定任务定义和执行轮次。重新执行、修改任务内容或验收标准、重新验收、手动改变状态都会使旧证据失效。目标仓库回退到集成提交之前也会阻止依赖解锁。验收报告保存于 `.dual-ai-collab/integration-reports`；缺失报告会使确认失效。运行数据和报告应保留并加入 Git 忽略规则。

旧 `DONE` / `VERIFIED` 仍能读取，但显示待确认集成，完成率不再计入这些无集成凭据的任务。迁移时先审查，再执行 `board integrate`。纯 Markdown 任务板的 `board show`、`board context` 不会自动写出 JSON；修改操作沿用原有迁移机制。

上下文包最多 64 KiB，包含任务章节（目标、约束、相关文件、决策）、项目头部的规范引用、依赖集成状态和验收命令，不递归读取规范文件或历史日志。主模型需维护任务中的决策并按需阅读引用文件。app-server 使用 `--context-task-file` 后，每次 start / continue / repair 都刷新快照，保存为该 run 的 `context.md` 并加入 prompt，同时复用原 thread。此选项不适用于 direct / adapter，它们可使用导出文件作为 `--prompt-file`。

所有 board 子命令支持 `--task-file`。自定义任务板运行验收时也应给 `run complete` 传相同的 `--task-file`。直接 CLI、Adapter 或同步实现先用 `verify run` 验收，再 `update 001 AWAITING_REVIEW`，之后走相同的审查和集成确认。

## 实测中的阻塞处理

`board show --verbose` 可查看耗时、阻塞原因和下一步命令。`run watch 001` 提供不依赖外部 JSON 解析的持续监控。

若执行因环境限制 blocked，而你已在合适环境逐条完成实际测试，可用 `run verify-manual 001 --list` 查看标准，再逐项 `--confirm` 并提供测试证据。随后 `board review --force` 允许进入审查，不跳过验收，不改写 blocked 执行结果。详见 [沙箱与 blocked 处理](sandbox-limitations.md)。
