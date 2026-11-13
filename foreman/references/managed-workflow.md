# 执行记录、验收证据与恢复

写验收证据、处理中断后留下的执行记录，或做交付检查时读这份文件。它给出字段示例和判断依据；命令的先后顺序在 SKILL.md 里。

## 当前会话直接执行

没写 `role` 的任务不派发：`execution begin <task-id>` 登记开始并记录文件基线，当前会话自己实现，做完后 `execution finish <task-id> --outcome completed`。记录的 `details.mode` 是 `direct`，droid 一栏是 `current-session`，没有模型。

和派发相比：

- 相同：开始条件（依赖、文件不重叠、并发上限、`files`、`runtime_dependencies`、结构化 `acceptance`）、`inspect` 的文件差异和 `notices`、验收证据格式、验收后文件或依赖变化使验收失效、`integrate` 的全部检查、`retry`、`block`、`unblock` 和恢复步骤。
- 不同：没有模型核对（`audit` 状态固定为 `not_applicable`，不阻止验收）；结果只有 `completed`、`failed`、`interrupted`；验收记录带 `self_review: true`，表示实现和验收是同一个会话。
- 没有的保护：不经过沙箱和写入守卫，文件范围靠当前会话自己遵守，范围外的改动只在 `inspect` 时报告。当前会话可以联网、可以用 git。

下面各节按派发来写，同样适用于直接执行。

## 运行记录

推荐 `run <task-id> --dispatcher <完整 ID>`。每次派发新建唯一 execution_id，Task description 带 `[tm:<execution_id>]`。记录文件仍位于 `.task-management/history`，旧记录可继续读取；新增字段在 details 中，Web 仍用已有白名单投影。

三种结果分别保存：

- 派发：运行、返回、失败、权限拒绝或中断。返回不代表代码可用。子 Agent 自己被中止时，即使调度进程正常返回，也记为权限拒绝或失败。
- 验收：主 Agent 的文件审查与每项验收证据，含独立时间戳和文件摘要。
- 集成：提交与集成时间，依赖仅在集成确认后解锁。

自动运行捕获真实进程结束时间。手工恢复时未知的结束时间和耗时保持 null，另记录补记时间。所有纠正和重试都用新编号，旧记录不可覆盖当前任务。事件更新和 checkpoint 同步使用项目文件锁，避免并行派发相互覆盖；进程被强杀时可能留下 running，恢复入口会保留它供检查。任务板的每次修改都在同一把文件锁内完成读取和写入，命令行与 Web 同时更新不会互相覆盖。命令行 `update`、`fail` 和 Web 的状态修改都拒绝受管任务（`begin` 过的任务，两种执行方式都算）。

派发结束时状态和派发结果在一次写入中保存。之后的任务板或 checkpoint 更新若被中断，用同一结果重复 `execution finish` 即可补齐；`integrate` 同样可以重复执行：任务板更新丢失时会补齐，已是 DONE 时用同一提交重复只重新同步 checkpoint，换成其他提交会被拒绝。

## 验收定义与证据

任务结构示例：

```json
{
  "id": "001",
  "role": "frontend",
  "files": ["static/js/tasks.js"],
  "runtime_dependencies": ["web_server.py", "web_projects.py", "foreman", "templates", "static", "pyproject.toml"],
  "acceptance": [
    {"id": "language", "scenario": "打开任务页和空列表", "expected": "页面及空态为中文", "method": "browser"},
    {"id": "race", "scenario": "延迟旧 GET 并提交状态更新", "expected": "旧响应不覆盖新状态", "method": "browser"},
    {"id": "syntax", "scenario": "运行语法检查", "expected": "退出码 0", "method": "command", "command": "node --check static/js/tasks.js"}
  ]
}
```

主 Agent 审查任务内容后，通过现有受控工具执行 command，不把任意任务板文本直接作为可信 shell 脚本自动运行。观察浏览器/手工条件后写证据：

```json
{
  "inspection": "检查了实际 diff 和新增文件；修改符合 files，原有用户改动已保留",
  "checks": [
    {"id": "language", "status": "passed", "evidence": "任务页与空列表实际显示中文；截图 planning/language.png"},
    {"id": "race", "status": "passed", "evidence": "延迟 GET 后更新为 BLOCKED，释放旧响应后仍为 BLOCKED"},
    {"id": "syntax", "status": "passed", "evidence": "node --check static/js/tasks.js，退出码 0"}
  ]
}
```

`execution inspect` 报出声明范围外的改动（`undeclared.paths` 不为空）时，证据里还要加一个 `undeclared` 字段，写明这些改动的来源和处理结论，例如 `"undeclared": "notes.md 是子 Agent 的草稿，已删除"`。没有这类改动时不需要这个字段。派发期间只是把已有改动提交进去（HEAD 变化但文件内容没变）不算范围外改动。

`acceptance <task-id> --template` 在任务板目录生成 `acceptance-<task-id>.json`：`checks` 照抄每个验收条件（多出的 scenario、expected 等字段只供参考），`status`、`evidence`、`inspection` 留空，有范围外改动时多一个空的 `undeclared`。原样提交会被拒绝。

`execution` 的 `finish`、`inspect`、`audit`、`accept`、`retry`、`block`、`unblock` 接受任务 ID，指这个任务在任务板上登记的当前执行记录；要操作已被替代的旧记录仍用完整的 execution-id（旧记录只能查看，修改会被拒绝）。

`execution accept <execution-id> --evidence-file <path>` 不替主 Agent 做观察，也不能防止虚报证据。它强制字段完整、条件全覆盖、当前执行模型核对通过，并保留验收时 files 与 runtime_dependencies 的内容摘要和依赖声明。集成前 files、运行依赖（内容或声明）或验收条件有变化都会使验收失效，报错会列出变化的路径。不要根据子 Agent 的“完成”报告生成 passed。

## 中断恢复

1. `execution recover` 找到尚未集成的运行，确认旧进程是否已结束。它不是进程存活检测器。
2. 已停止但仍 running：`execution finish <id> --outcome interrupted`。知道实际结束时间才加 `--ended-at`。
3. `execution inspect <id>` 检查与派发前相比新增/修改/删除的文件，再查看实际 diff 与新增文件内容。摘要不提供作者归属。`notices` 会指出声明的 files 完全没有变化，或派发期间有声明范围外的改动。
4. 核对本次实际模型。权限拒绝后文件可能完整，模型错误也可能留下文件；不要未经检查直接重跑。
5. 完整成果由主 Agent 验收；不完整则 `execution retry <id> --reason <检查结论和续做范围>`；模型不可用/不符则 block，报告用户处理。所有路径都保留现有文件。
6. 任务 BLOCKED（显式 block 或超过重试上限）后等用户处理，再用 `execution unblock <id> --reason <用户的处理结果>` 回到 PENDING，失败次数清零并保留原因。BLOCKED 任务不能 retry。

`recover` 列出的记录带 `current` 字段；为 false 表示已被后续派发替代或未登记到任务板，仅供查阅。

## 可复现交付

`delivery --commit <SHA> --paths <完整依赖路径...>` 比较提交和工作区：缺失文件、未提交修改及只在工作区删除的文件都会阻止通过。它不自动推断全部依赖，也不启动程序。

主 Agent 根据实际入口填写 runtime_dependencies，包括本地库、模板、静态资源和依赖清单。提交前审查暂存区，提交后在临时干净检出中执行实际启动与验收；不要使用工作区未提交的文件补齐检出。需要外部服务或凭据时说明复现前提，不复制真实凭据到检出。

用户要求某些依赖保持未提交时，保持这个边界，明确报告交付因此受阻，不擅自提交。
