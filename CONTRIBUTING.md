# 贡献指南

现在维护的是 `foreman/`（技能）、`web_server.py` 和 `web_projects.py`（Web UI）、`install.py`（安装脚本）和它们的测试。`skill/` 是旧版 dual-ai-collab，不再加功能，只保证它的测试还能通过。

## 开发环境

需要 Python 3.9 以上和 git，在 macOS 或 Linux 上开发；foreman 不支持 Windows。

```bash
git clone <repo-url>
cd dual-ai-collab
pip install -e ".[test]"   # Flask（Web UI 和它的测试）和 pytest
```

foreman 本身只用标准库，不安装也能运行：`foreman/bin/foreman --version`。旧版的调度分析另外需要 `pip install -e ".[analytics]"`。

## 测试

```bash
# foreman 和安装脚本：改 foreman/ 或 install.py 时先跑这一组
python -m pytest tests/test_foreman*.py tests/test_install_pytest.py -q

# Web UI
python -m pytest tests/test_web_server.py tests/test_web_markdown.py tests/test_multi_project.py -q

# 全部 Python 测试和旧版的 shell 测试套件，CI 跑的就是这两条
python -m pytest tests -v --tb=short
bash tests/run_all_tests.sh
```

行为变了就加测试，并确认新测试在没有这次修改时会失败。

### 文档也有测试

`tests/test_foreman_skill.py` 把 `foreman/SKILL.md`、`foreman/references/`、两份 README 和 `docs/web-ui.md` 当作产品的一部分来检查：

- 文档里写的每一条 `foreman ...` 命令都要能被命令行解析。
- 每个命令和子命令都要在 `SKILL.md` 或它链接的 reference 里出现。
- `SKILL.md` 正文不超过 500 行，只放每次都会用到的主流程；只在部分情况下需要的细节放进 `foreman/references/`。
- 每个 reference 都要从 `SKILL.md` 链接，开头写明什么时候读它，不链接别的文件；超过 100 行时开头要有和小节标题一致的目录。
- 文中引用的章节号要存在，文档之间的相对链接要指向存在的文件。

## 发布新版本

版本号写在三个地方，测试会检查它们一致：

1. `foreman/SKILL.md` 开头的 `version`，`foreman --version` 输出的就是它
2. `pyproject.toml` 的 `version`
3. `README.md` 末尾“版本历史”最上面的一条

## 代码质量

```bash
ruff check .          # 没装 ruff 时用 uvx ruff check .
ruff check --fix .    # 修复可以自动修复的问题
python -m compileall -q skill/scripts foreman web_server.py web_projects.py install.py
```

`foreman/`、`web_server.py`、`web_projects.py`、`install.py` 和它们的测试要保持没有 lint 发现。旧版 `skill/` 和它的测试里还有没清理的发现，新改动不要再增加。

## 提交规范

使用 Conventional Commits 格式：

- `feat:` 新功能
- `fix:` Bug 修复
- `docs:` 文档更新
- `test:` 测试相关
- `refactor:` 重构
- `style:` 只改格式或 lint
- `ci:` CI/CD 相关

正文写为什么改，以及改了之后行为有什么不同。AI 工具参与的提交，结尾保留该工具自己的 `Co-authored-by:` 署名行。

## CI

`.github/workflows/ci.yml` 在推送到 `master` 或 `feat/*` 分支、以及向 `master` 提 Pull Request 时运行，环境是 Ubuntu：

- `test`：Python 3.9、3.10、3.11、3.12 各跑一遍 `python -m pytest tests -v --tb=short` 和 `bash tests/run_all_tests.sh`
- `lint`：`ruff check .` 和上面的 `compileall`

其他名字的分支推送后不会触发，提了 Pull Request 才会运行。

## Pull Request

1. 从 `master` 创建特性分支
2. 确保上面的测试和 lint 通过
3. 更新相关文档：用户能看到的行为变了，就改 `foreman/SKILL.md` 或对应的 reference、`foreman/README.md` 和根目录的 `README.md`
4. 提交 PR 并等待 review
