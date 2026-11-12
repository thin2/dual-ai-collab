# 贡献指南

## 开发环境

```bash
# 克隆仓库
git clone <repo-url>
cd dual-ai-collab

# 安装依赖
pip install -e ".[test,analytics]"
```

## 测试

```bash
# 运行 Python 测试
python -m pytest tests -v

# 运行 shell 测试套件
bash tests/run_all_tests.sh

# 运行所有测试
python -m pytest tests -v && bash tests/run_all_tests.sh
```

## 代码质量

```bash
# Lint 检查
ruff check .

# 修复可自动修复的问题
ruff check --fix .

# 检查 Python 语法
python -m compileall -q skill/scripts foreman web_server.py web_projects.py install.py
```

## 提交规范

使用 Conventional Commits 格式：

- `feat:` 新功能
- `fix:` Bug 修复
- `docs:` 文档更新
- `test:` 测试相关
- `refactor:` 重构
- `ci:` CI/CD 相关

每个提交结尾添加：

```
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

## CI

GitHub Actions 自动运行：
- Python 3.9-3.12 的测试矩阵
- pytest 和 shell 测试套件
- ruff lint 检查
- Python 语法检查

## Pull Request

1. 从 `master` 创建特性分支
2. 确保所有测试通过
3. 更新相关文档
4. 提交 PR 并等待 review
