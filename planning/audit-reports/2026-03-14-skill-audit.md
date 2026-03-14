# 审计报告：当前 Skill 状态评估

**审计时间**: 2026-03-14
**审计对象**: `skill/dual-ai-collab.md` 及其配套文档、测试脚本
**审计范围**:
- Skill 主文件
- README 与设计文档
- `tests/` 下自动化测试脚本
- 本地可执行性验证

---

## 审计结论

当前 skill 处于“**核心流程可用，但发布质量与维护一致性不足**”的状态。

从功能角度看，任务选择、状态流转、依赖识别、并行任务识别、进度统计等核心逻辑均有测试覆盖，且本地执行 `bash tests/run_all_tests.sh` 结果为 **65/65 通过**。同时，`codex exec --help` 显示当前 CLI 支持 `exec` 子命令与 `--full-auto` 参数，因此 skill 中最关键的 Codex 调用形式并未失效。

但从产品化、可维护性和信任度角度看，仍存在若干需要优先修复的问题，主要集中在：

- 测试总控脚本对异常退出缺乏严格判定
- 测试统计口径失真，导致测试报表可信度下降
- Skill 实际行为与设计文档存在行为级漂移
- 依赖解锁规则在 skill 与测试之间不一致
- 版本、安装方式、文档链接等信息多处漂移

综合判断：**不建议将当前版本视为“已完全收敛的正式版”继续扩散使用，建议先完成一轮一致性修复。**

---

## 审计方法

本次审计采用以下方式进行：

1. 阅读 Skill 主文件与配套文档，检查版本、流程、安装说明、能力描述是否一致。
2. 阅读 `tests/` 下测试脚本，确认测试覆盖范围与判定逻辑。
3. 本地执行测试套件：`bash tests/run_all_tests.sh`。
4. 本地核查 Codex CLI 帮助信息：`codex --help` 与 `codex exec --help`。
5. 对“文档宣称能力”和“仓库实际可交付内容”进行对账。

---

## 主要发现

### 发现 1：测试总控脚本会将异常退出的测试套件误判为成功

**严重级别**: 高

**证据**

- [tests/run_all_tests.sh#L35](/home/hn/projects/dual-ai-collab/tests/run_all_tests.sh#L35)
- [tests/run_all_tests.sh#L40](/home/hn/projects/dual-ai-collab/tests/run_all_tests.sh#L40)
- [tests/run_all_tests.sh#L75](/home/hn/projects/dual-ai-collab/tests/run_all_tests.sh#L75)

**问题描述**

`run_test_suite()` 虽然捕获了子测试脚本的退出码：

- `output=$(bash "$test_file" 2>&1) || exit_code=$?`

但后续逻辑并未基于 `exit_code` 判定失败，而是仅通过统计输出中的 `✅` 与 `❌` 个数来汇总结果。如果某个测试脚本因为语法错误、提前退出、运行异常而没有输出 `❌`，总控脚本仍可能把该套件计为成功。

**影响**

- CI 绿灯可能出现误报
- 测试报表不能可靠反映真实失败
- 后续重构时容易放过真实回归

**建议**

- 将 `exit_code != 0` 作为硬失败条件纳入汇总逻辑
- 当测试套件异常退出时，至少强制为该套件记一次失败
- 最终汇总应同时参考断言失败数和脚本退出码

---

### 发现 2：测试统计已出现“总数小于通过数”的失真现象

**严重级别**: 中高

**证据**

- [tests/test_parallel.sh#L148](/home/hn/projects/dual-ai-collab/tests/test_parallel.sh#L148)
- [tests/test_parallel.sh#L149](/home/hn/projects/dual-ai-collab/tests/test_parallel.sh#L149)
- [tests/test_parallel.sh#L150](/home/hn/projects/dual-ai-collab/tests/test_parallel.sh#L150)
- [tests/test_helpers.sh#L135](/home/hn/projects/dual-ai-collab/tests/test_helpers.sh#L135)
- [tests/test_helpers.sh#L150](/home/hn/projects/dual-ai-collab/tests/test_helpers.sh#L150)

**问题描述**

并行任务测试中存在单个 `it` 用例下执行多个断言的情况，例如：

- 同一个测试标题下先执行 `assert_not_contains`
- 再执行 `assert_contains`

而当前测试框架的 `TESTS_RUN` 只在 `it()` 中累加一次，但每次断言成功都会调用 `pass()` 并增加通过计数。这会造成：

- 用例总数与断言总数混淆
- 某些套件出现“总数 7，通过 8”的不合理结果

**影响**

- 测试统计结果失真
- 审计者无法准确判断测试覆盖面和失败密度
- 长期会削弱测试数据的参考价值

**建议**

- 明确“统计对象”是测试用例还是断言数，并统一口径
- 若按用例统计，一个 `it` 内应只保留一个最终断言结论
- 若按断言统计，应重构测试框架，让 `TESTS_RUN` 在每次断言时累加

---

### 发现 3：Skill 行为与设计文档存在行为级漂移

**严重级别**: 中高

**证据**

- [skill-definition.md#L102](/home/hn/projects/dual-ai-collab/skill-definition.md#L102)
- [skill-definition.md#L103](/home/hn/projects/dual-ai-collab/skill-definition.md#L103)
- [skill/dual-ai-collab.md#L308](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L308)
- [skill/dual-ai-collab.md#L310](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L310)
- [skill/dual-ai-collab.md#L705](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L705)

**问题描述**

设计文档中描述的流程是：

- 先生成任务板
- 再由用户确认是否继续
- 然后启动 Codex 开发

而 skill 主文件中的实际逻辑已经变成：

- 任务板创建后直接自动启动开发
- 全程无需用户确认

这不只是文案差异，而是产品行为本身发生了变化。

**影响**

- 用户预期与实际执行不一致
- 在需求尚未最终确认时，skill 可能已经开始改动代码
- 审计、演示、对外说明时容易出现口径冲突

**建议**

- 明确产品决策：到底是“确认后执行”还是“自动执行”
- 如果保留自动执行，则应同步更新 `skill-definition.md`、README 和相关说明
- 如果恢复确认机制，则应修改 skill 主文件，避免跳过用户确认

---

### 发现 4：依赖判定规则在 Skill 与测试之间不一致

**严重级别**: 中

**证据**

- [skill/dual-ai-collab.md#L267](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L267)
- [skill/dual-ai-collab.md#L288](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L288)
- [tests/test_dependencies.sh#L17](/home/hn/projects/dual-ai-collab/tests/test_dependencies.sh#L17)
- [tests/test_dependencies.sh#L24](/home/hn/projects/dual-ai-collab/tests/test_dependencies.sh#L24)

**问题描述**

Skill 主文件中的依赖检查逻辑允许：

- 依赖任务状态为 `DONE` 或 `VERIFIED` 时继续执行

但测试脚本中的 `check_deps()` 实现只接受：

- 依赖任务状态为 `VERIFIED`

也就是说，测试所验证的并不是 skill 文档中真正声明的行为。

**影响**

- 实现语义与测试语义不一致
- 用户若按文档理解，测试无法充分保障真实行为
- 如果项目要求“审计通过后才能解锁下游任务”，当前 skill 主体会过早放行

**建议**

- 统一依赖语义，并在 skill、测试、文档三处同步
- 推荐明确以下二选一：
  - `DONE` 即可解锁，强调开发流水线效率
  - 必须 `VERIFIED` 才解锁，强调质量门禁

---

### 发现 5：文档、版本号、安装说明存在多处漂移

**严重级别**: 中

**证据**

- [README.md#L6](/home/hn/projects/dual-ai-collab/README.md#L6)
- [README.md#L120](/home/hn/projects/dual-ai-collab/README.md#L120)
- [README.md#L127](/home/hn/projects/dual-ai-collab/README.md#L127)
- [skill/dual-ai-collab.md#L3](/home/hn/projects/dual-ai-collab/skill/dual-ai-collab.md#L3)
- [skill/README.md#L36](/home/hn/projects/dual-ai-collab/skill/README.md#L36)
- [skill/CHANGELOG.md#L3](/home/hn/projects/dual-ai-collab/skill/CHANGELOG.md#L3)

**问题描述**

当前存在以下不一致：

- README 显示版本 `2.1.0`，但 skill frontmatter 已是 `2.2.0`
- README 写“测试套件包含 39 个测试用例”，本地实际运行结果为 65 个
- README 建议安装 `@openai/codex-cli`，skill 主文件中则写 `@openai/codex`
- `skill/README.md` 链接到 `INSTALL.md`，但该文件不存在
- CHANGELOG 尚未记录 `2.2.0`

**影响**

- 用户不知道该以哪份文档为准
- 安装和排障时容易误导
- 版本发布可信度下降

**建议**

- 统一版本号、安装命令、测试数量、触发方式说明
- 删除失效链接或补齐缺失文件
- 为 `2.2.0` 补充正式更新记录

---

## 正向观察

以下方面表现较好，可作为后续整理的基础：

- Skill 主文件结构完整，覆盖访谈、任务拆分、执行、审计、进度报告等完整链路
- 核心 task board 约定相对统一，便于 Bash/awk/sed 处理
- 测试套件覆盖了任务选择、状态更新、统计、依赖、并行识别等关键基础逻辑
- 本地验证显示 `codex exec --full-auto` 的 CLI 入口仍然有效

---

## 风险评估

### 立即风险

- 测试误报成功，导致回归未被发现
- 用户按旧文档理解流程，实际却触发自动开发
- 依赖门禁语义不清，影响串并行任务调度

### 中期风险

- 文档漂移继续扩大，维护成本显著上升
- 新贡献者难以分辨“当前真实行为”
- 对外发布时更容易积累安装与使用反馈问题

---

## 整改优先级建议

### P0：立即修复

1. 修复测试总控脚本的失败判定逻辑，使异常退出直接计为失败。
2. 统一测试统计口径，消除“总数小于通过数”的问题。

### P1：本轮版本内修复

1. 明确“是否需要用户确认后再启动开发”的产品行为，并同步到 skill 与设计文档。
2. 明确依赖任务应以 `DONE` 还是 `VERIFIED` 作为解锁条件，并同步更新测试与说明。

### P2：发版前整理

1. 统一 README、skill、CHANGELOG 中的版本信息。
2. 统一 Codex 安装命令表述。
3. 删除或修复失效文档链接。
4. 重新核对测试数量说明。

---

## 复审建议

建议在完成整改后进行一次短周期复审，重点验证：

1. 测试套件异常退出时，总控是否会正确报错。
2. 测试统计是否恢复一致。
3. 设计文档与 skill 实际行为是否完全一致。
4. 依赖规则是否在 skill、测试、README 中保持统一。
5. 版本、安装方式、触发词说明是否完成对齐。

---

## 附：本次实际验证结果

### 本地测试

执行命令：

```bash
bash tests/run_all_tests.sh
```

结果：

- 测试套件数量：7
- 汇总通过：65
- 汇总失败：0
- 观察到并行测试套件存在“总数 7，通过 8”的统计失真

### CLI 验证

执行命令：

```bash
codex --help
codex exec --help
```

结果：

- `codex` 可用
- `exec` 子命令存在
- `--full-auto` 参数存在

---

## 最终结论

该 skill 已具备继续演进的基础，但当前更适合定义为“**可运行的候选版本**”而非“**已经收敛的正式版本**”。

如果以用户信任、文档一致性和测试有效性作为上线门槛，建议先完成一轮针对测试机制与文档漂移的整改，再考虑继续推广或发版。
