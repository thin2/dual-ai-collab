"""The task detail page renders task text as Markdown; these run that renderer under node."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "static" / "js" / "markdown.js"
NODE = shutil.which("node")
PROGRAM = """
const fs = require('fs');
const render = new Function(fs.readFileSync(process.argv[1], 'utf8') + '; return renderMarkdown;')();
process.stdout.write(JSON.stringify(JSON.parse(fs.readFileSync(0, 'utf8')).map(render)));
"""

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def render(source):
    done = subprocess.run(
        [NODE, "-e", PROGRAM, str(SCRIPT)],
        input=json.dumps([source]), capture_output=True, text=True, check=True, timeout=30,
    )
    return json.loads(done.stdout)[0]


def test_headings_inside_a_section_start_below_the_section_title():
    html = render("说明文字。\n\n# Web 界面适配 task-management\n\n## 固定接口约定\n####### 不是标题")
    assert html == (
        "<p>说明文字。</p>"
        '<h4 class="md-h1">Web 界面适配 task-management</h4>'
        '<h5 class="md-h2">固定接口约定</h5>'
        "<p>####### 不是标题</p>"
    )


def test_plain_text_keeps_its_line_breaks():
    assert render("第一行\n第二行\n\n第三行") == "<p>第一行<br>第二行</p><p>第三行</p>"
    assert render("") == ""
    assert render(None) == ""


def test_lists_nest_by_indent_and_keep_their_numbering():
    html = render("- 保留 /api/<resource>\n  - 子项\n  续行\n- [x] 已完成\n- [ ] 未完成\n\n3. 第三\n4. 第四")
    assert html == (
        "<ul>"
        "<li>保留 /api/&lt;resource&gt;<ul><li>子项<br>续行</li></ul></li>"
        '<li class="md-task"><input type="checkbox" disabled checked> 已完成</li>'
        '<li class="md-task"><input type="checkbox" disabled> 未完成</li>'
        "</ul>"
        '<ol start="3"><li>第三</li><li>第四</li></ol>'
    )


def test_code_is_shown_literally():
    assert render("运行 `python3 -m pytest -q **x**` 即可") == (
        "<p>运行 <code>python3 -m pytest -q **x**</code> 即可</p>"
    )
    assert render("```bash\nls <dir> && echo **ok**\n# 不是标题\n```\n后文") == (
        "<pre><code>ls &lt;dir&gt; &amp;&amp; echo **ok**\n# 不是标题</code></pre><p>后文</p>"
    )
    assert render("```\n没有结束标记") == "<pre><code>没有结束标记</code></pre>"


def test_bold_links_quotes_rules_and_tables():
    assert render("**重点** 见 [文档](https://example.com/a?b=1&c=2)") == (
        '<p><strong>重点</strong> 见 <a href="https://example.com/a?b=1&amp;c=2" target="_blank" '
        'rel="noopener noreferrer">文档</a></p>'
    )
    assert render("> 引用\n> - 项\n\n---") == "<blockquote><p>引用</p><ul><li>项</li></ul></blockquote><hr>"
    assert render("| 命令 | 说明 |\n|---|---|\n| `show` | 查看 |\n| 少一格 |") == (
        '<div class="md-table"><table><thead><tr><th>命令</th><th>说明</th></tr></thead><tbody>'
        "<tr><td><code>show</code></td><td>查看</td></tr><tr><td>少一格</td><td></td></tr>"
        "</tbody></table></div>"
    )
    assert render("| 只有一行 |") == "<p>| 只有一行 |</p>"


@pytest.mark.parametrize("source", [
    "<script>alert(1)</script>",
    "# <img src=x onerror=alert(1)>",
    "- <svg onload=alert(1)>",
    "> <b onclick=alert(1)>x</b>",
    "| <i>a</i> | b |\n|---|---|\n| <u>c</u> | d |",
    "`<script>alert(1)</script>`",
    "```\n</code></pre><script>alert(1)</script>\n```",
    "**<em>x</em>**",
    "[<b>x</b>](https://example.com/<b>)",
])
def test_markup_in_task_text_is_escaped(source):
    html = render(source)
    for tag in ("<script", "<img", "<svg", "<b ", "<b>", "<i>", "<u>", "<em"):
        assert tag not in html
    assert "&lt;" in html


@pytest.mark.parametrize("source", [
    "[点我](javascript:alert(1))",
    "[点我](data:text/html,<script>alert(1)</script>)",
    "[点我](/relative/path)",
])
def test_only_http_links_become_links(source):
    assert "<a " not in render(source)


def test_a_quote_in_a_link_cannot_end_the_attribute():
    html = render('[x](https://example.com/"onmouseover="alert(1))')
    assert html.count('"') == html.count('href="') * 2 + html.count('target="_blank"') * 2 + html.count('rel="noopener noreferrer"') * 2
    assert "&quot;onmouseover=&quot;" in html
