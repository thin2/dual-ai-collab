# 执行记录、验收证据与恢复

写验收证据、处理用户叫停或中断后留下的执行记录、做需要模拟器或真机的验证，或做交付检查时读这份文件。它给出字段示例和判断依据；命令的先后顺序在 SKILL.md 里。

## 目录

1. 当前会话直接执行
2. 运行记录
3. 验收定义与证据
4. 用户叫停
5. 长时间任务和设备验证
6. 中断恢复
7. 没有 git 的项目
8. 可复现交付

## 当前会话直接执行

没写 `role` 的任务不派发：`execution begin <task-id>` 登记开始并记录文件基线，当前会话自己实现，做完后 `execution finish <task-id> --outcome completed`。记录的 `details.mode` 是 `direct`，droid 一栏是 `current-session`，没有模型。

和派发相比：

- 相同：开始条件（依赖、文件不重叠、并发上限、`files`、`runtime_dependencies`、结构化 `acceptance`）、`inspect` 的文件差异和 `notices`、验收证据格式、验收后文件或依赖变化使验收失效、`integrate` 的全部检查、`retry`、`pause`、`block`、`unblock`、`track` 和恢复步骤。
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

`execution inspect` 报出声明范围外的改动（`undeclared.paths` 不为空）时，证据里还要加一个 `undeclared` 字段，写明这些改动的来源和处理结论，例如 `"undeclared": "notes.md 是子 Agent 的草稿，已删除"`，或 `"undeclared": "notes.md 是上个会话留下的备注，和本任务无关，保留"`。不是自己写的文件不要为了让这一项消失而删除。没有这类改动时不需要这个字段。派发期间只是把已有改动提交进去（HEAD 变化但文件内容没变）不算范围外改动。

`acceptance <task-id> --template` 在任务板目录生成 `acceptance-<task-id>.json`：开头是任务当前执行的 `execution_id`，`checks` 照抄每个验收条件（多出的 scenario、expected 等字段只供参考），`status`、`evidence`、`inspection` 留空，有范围外改动时多一个空的 `undeclared`。原样提交会被拒绝。

证据和执行记录是绑定的，`accept` 为此做两项检查，都针对“拿旧证据充数”：

- 证据里的 `execution_id` 不是任务当前这次执行时拒绝。返工之后，上一次执行的证据不能接着用。
- 证据文件的修改时间早于这次执行登记结束（`execution finish`）时拒绝。实现还没结束时看到的结果不算数。

两种情况都运行 `acceptance <task-id> --template --force` 重新生成框架，再逐项重新观察。框架里的 `execution_id` 不要改。手写的证据可以不带这个字段，这时只检查时间；从标准输入读入的证据没有文件时间，只检查 `execution_id`。

`execution` 的 `finish`、`inspect`、`audit`、`accept`、`retry`、`pause`、`block`、`unblock`、`track` 接受任务 ID，指这个任务在任务板上登记的当前执行记录；要操作已被替代的旧记录仍用完整的 execution-id（旧记录只能查看，修改会被拒绝）。

`execution accept <execution-id> --evidence-file <path>` 不替主 Agent 做观察，也不能防止虚报证据。它强制字段完整、条件全覆盖、当前执行模型核对通过，并保留验收时 files 与 runtime_dependencies 的内容摘要和依赖声明。集成前 files、运行依赖（内容或声明）或验收条件有变化都会使验收失效，报错会列出变化的路径。不要根据子 Agent 的“完成”报告生成 passed。

## 用户叫停

用户让正在做的任务停下（改主意、要先确认设计、先做别的），不是这次执行失败了，用 `pause` 而不是 `retry`。两种执行方式都一样：

```bash
foreman execution finish 001 --outcome interrupted
foreman execution pause 001 --reason "用户要先确认设计稿；列表已完成，详情页没动"
```

- 任务回到 PENDING，失败次数不变，叫停多少次都不会因此 BLOCKED。已有文件保留，不还原。
- `--reason` 写两件事：用户为什么叫停，已经做完和还没做的部分。它会出现在 `show` 和下次开始时的任务上下文里，开头标着“用户叫停（不计失败次数）”。
- 恢复由用户决定。不要因为任务又出现在 `batch` 里就自己重新开始：用户说继续时再 `execution begin`（派发的任务用 `run`），先看已有改动，在它之上接着做。
- 只有登记为 `interrupted` 的执行可以 `pause`。执行自己出错、没做完，或派发超时被终止，都是失败的尝试，用 `retry`。
- 叫停时登记过的进程还在运行，`pause` 会列出来（见下一节）。

## 长时间任务和设备验证

要启动模拟器、连接真机、打包安装或等待构建的任务，一次验证可能要几分钟到几十分钟。规划和执行时多做四件事：

1. **一项验收条件只写一个可观察的结果。** 写“点击登录后进入首页”这样看得见的结果，并注明在哪种设备或系统版本上看。几个行为写成几项：某一项没过时，其余各项的证据仍然有效。`validate` 会提醒 `expected` 里写了多个结果的条件。
2. **先估时间再动手。** 开始设备验证前告诉用户要做哪几步、总共预计多久。明显超出预计还没有结果时停下来，说明卡在哪一步、已经试过什么，由用户决定继续等、换一种验证方式还是叫停；不要一遍遍重装、重启。
3. **按里程碑汇报。** 每完成一个能单独说明的阶段（构建通过、装到设备上、某一项验收条件通过），向用户说一句进展和下一步。
4. **登记留在后台的进程。** dev server、模拟器、端口转发这类命令返回后还在运行的进程，启动后立刻登记：

```bash
foreman execution track 001 --pid <PID> --label "Android 模拟器 Pixel_7"
```

`finish`、`retry`、`pause` 和 `integrate` 会在标准错误输出里列出登记过且还在运行的进程，`inspect` 的 `processes` 给出每个进程的 PID、说明和是否还在运行。不再需要的关掉；要留给用户继续用的，在汇报里写明它还开着、怎么关。登记的是 PID 和进程的启动时间，进程退出后同一个 PID 被别的程序占用不会误报。没有登记的进程不会被发现。

设备上的观察写证据时带上环境：设备或模拟器型号、系统版本、安装的是哪次构建，以及看到的具体内容或截图路径。

## 中断恢复

1. `execution recover` 找到尚未集成的运行，确认旧进程是否已结束。它不是进程存活检测器。
2. 已停止但仍 running：`execution finish <id> --outcome interrupted`。知道实际结束时间才加 `--ended-at`。
3. `execution inspect <id>` 检查与派发前相比新增/修改/删除的文件，再查看实际 diff 与新增文件内容。摘要不提供作者归属。`notices` 会指出声明的 files 完全没有变化，或派发期间有声明范围外的改动。记录还是 running 时也可以运行：这时没有 `notices`，`undeclared` 是当前的快照，接手直接执行的任务前先看它，里面是上个会话留在 files 之外的文件。
4. 核对本次实际模型。权限拒绝后文件可能完整，模型错误也可能留下文件；不要未经检查直接重跑。
5. 完整成果由主 Agent 验收；不完整则 `execution retry <id> --reason <检查结论和续做范围>`；是用户叫停的用 `execution pause <id> --reason <叫停原因和已完成的部分>`，不计失败次数；模型不可用/不符则 block，报告用户处理。所有路径都保留现有文件。
6. 任务 BLOCKED（显式 block 或超过重试上限）后等用户处理，再用 `execution unblock <id> --reason <用户的处理结果>` 回到 PENDING，失败次数清零并保留原因。BLOCKED 任务不能 retry。

`recover` 列出的记录带 `current` 字段；为 false 表示已被后续派发替代或未登记到任务板，仅供查阅。

## 没有 git 的项目

项目不在 git 仓库里时（`doctor` 的“项目”一项会注明），流程照常，三处不同：

- `inspect` 不检查范围外改动，`undeclared.checked` 为假：`files` 之外改了什么要自己核对。
- 集成用 `integrate <task-id> --no-git --note <成果保存在哪里>`。它检查逐项验收、验收后 files 和运行依赖是否变化，然后记录 `mode: no-git` 和已验收内容的摘要（SHA-256）来代替提交。`--note` 必填：没有提交可查时，它是以后找到这份成果的线索。
- `delivery` 要有提交才能比较，用不了。要证明成果能独立运行，把项目复制到别处再启动和验收。

项目在 git 仓库里时 `--no-git` 会被拒绝；已经按一种方式集成的任务不能改记成另一种。以后给项目建了 git 仓库，已经 DONE 的任务不用重新集成，新的任务按提交集成。

## 可复现交付

`delivery --commit <SHA> --paths <完整依赖路径...>` 比较提交和工作区：缺失文件、未提交修改及只在工作区删除的文件都会阻止通过。它不自动推断全部依赖，也不启动程序。

`integrate` 已经对每个任务自己的 files 和 runtime_dependencies 做过同样的比较。`delivery` 用在要交付的任务全部集成之后：对最后的提交运行一次，`--paths` 写各任务 runtime_dependencies 的并集，确认后来的任务没有让前面任务依赖的文件停在未提交状态。

主 Agent 根据实际入口填写 runtime_dependencies，包括本地库、模板、静态资源和依赖清单。提交前审查暂存区，提交后在临时干净检出中执行实际启动与验收；不要使用工作区未提交的文件补齐检出。干净检出放在项目目录之外（例如 `git archive <SHA> | tar -xf - -C <临时目录>`），用完删除：放在项目里会成为未跟踪文件，被进行中的任务记成范围外改动。需要外部服务或凭据时说明复现前提，不复制真实凭据到检出。

用户要求某些依赖保持未提交时，保持这个边界，明确报告交付因此受阻，不擅自提交。
