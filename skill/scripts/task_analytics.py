#!/usr/bin/env python3
"""任务分析和可视化命令。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tasks_store import CliError, DEFAULT_TASKS_MD
from task_history import generate_report as generate_history_report
from task_visualization import (
    generate_dependency_graph,
    generate_analysis_report as generate_dep_report,
)
from task_templates import (
    list_templates,
    create_task_from_template,
    generate_task_board_from_spec,
    TASK_TEMPLATES,
    add_task_to_board,
)


def cmd_history() -> int:
    """显示任务执行历史报告。"""
    report = generate_history_report()
    print(report)
    return 0


def cmd_visualize(output_format: str = "mermaid", output_file: str | None = None) -> int:
    """生成任务依赖可视化图。"""
    try:
        graph = generate_dependency_graph(output_format)

        if output_file:
            Path(output_file).write_text(graph, encoding="utf-8")
            print(f"依赖图已保存到: {output_file}")
        else:
            print(graph)

        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def cmd_analyze() -> int:
    """生成依赖分析报告。"""
    report = generate_dep_report()
    print(report)
    return 0


def cmd_schedule() -> int:
    """生成智能调度报告。"""
    try:
        from task_scheduler import generate_schedule_report
        report = generate_schedule_report()
        print(report)
        return 0
    except Exception as e:
        print(f"ERROR: 无法生成调度报告: {e}", file=sys.stderr)
        return 1


def cmd_templates_list() -> int:
    """列出所有可用模板。"""
    templates = list_templates()

    print("## 内置模板")
    for name in templates["builtin"]:
        template = TASK_TEMPLATES[name]
        print(f"- {name}: {template['title']}")

    if templates["custom"]:
        print("\n## 自定义模板")
        for name in templates["custom"]:
            print(f"- {name}")

    return 0


def cmd_templates_create(
    template_name: str,
    task_num: str,
    output_file: str | None = None,
    *, add: bool = False, task_file: str = DEFAULT_TASKS_MD, dependencies=None,
    **kwargs: str
) -> int:
    """从模板创建任务。"""
    try:
        if add and output_file:
            raise CliError("--add 与 --output 不能同时使用")
        task = create_task_from_template(template_name, task_num, **kwargs)
        if add:
            task = add_task_to_board(task, task_file, dependencies)
        elif dependencies:
            from tasks_store import format_dependencies
            task["dependencies"] = format_dependencies(dependencies)

        import json
        task_json = json.dumps(task, ensure_ascii=False, indent=2)

        if output_file:
            Path(output_file).write_text(task_json, encoding="utf-8")
            print(f"任务已保存到: {output_file}")
        else:
            print(task_json)

        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def cmd_generate_from_spec(spec_file: str, output_file: str | None = None) -> int:
    """从需求文档生成任务板。"""
    try:
        spec_text = Path(spec_file).read_text(encoding="utf-8")
        tasks = generate_task_board_from_spec(spec_text)

        import json
        tasks_json = json.dumps(tasks, ensure_ascii=False, indent=2)

        if output_file:
            Path(output_file).write_text(tasks_json, encoding="utf-8")
            print(f"任务板已保存到: {output_file}")
        else:
            print(tasks_json)

        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


def register_subparsers(subparsers, *, nested: bool = False) -> None:
    """注册子命令。"""
    # 历史报告
    parser_history = subparsers.add_parser(
        "history",
        help="显示任务执行历史报告"
    )
    parser_history.set_defaults(func=lambda args: cmd_history())

    # 依赖可视化
    parser_viz = subparsers.add_parser(
        "visualize",
        help="生成任务依赖可视化图"
    )
    parser_viz.add_argument(
        "--format",
        choices=["mermaid", "dot"],
        default="mermaid",
        help="输出格式 (默认: mermaid)"
    )
    parser_viz.add_argument(
        "-o", "--output",
        help="输出文件路径"
    )
    parser_viz.set_defaults(func=lambda args: cmd_visualize(args.format, args.output))

    # 依赖分析
    parser_analyze = subparsers.add_parser(
        "analyze",
        help="生成依赖分析报告"
    )
    parser_analyze.set_defaults(func=lambda args: cmd_analyze())

    # 调度建议
    parser_schedule = subparsers.add_parser(
        "schedule",
        help="生成智能调度报告"
    )
    parser_schedule.set_defaults(func=lambda args: cmd_schedule())

    # 模板管理
    parser_templates = subparsers.add_parser(
        "templates",
        help="任务模板管理"
    )
    templates_sub = parser_templates.add_subparsers(dest="templates_command")

    # 列出模板
    templates_list = templates_sub.add_parser("list", help="列出所有模板")
    templates_list.set_defaults(func=lambda args: cmd_templates_list())

    # 从模板创建
    templates_create = templates_sub.add_parser("create", help="从模板创建任务")
    templates_create.add_argument("template", help="模板名称")
    templates_create.add_argument("task_num", help="任务编号")
    templates_create.add_argument("-o", "--output", help="输出文件")
    templates_create.add_argument("--add", action="store_true", help="校验后写入任务板")
    templates_create.add_argument("--task-file", default=DEFAULT_TASKS_MD)
    templates_create.add_argument("--depends-on", action="append", default=[])
    templates_create.add_argument(
        "--var",
        action="append",
        help="模板变量 (格式: key=value)",
        default=[]
    )
    templates_create.set_defaults(func=lambda args: cmd_templates_create(
        args.template,
        args.task_num,
        args.output,
        add=args.add, task_file=args.task_file, dependencies=args.depends_on,
        **parse_variables(args.var)
    ))

    # 从需求生成
    parser_generate = subparsers.add_parser(
        "generate",
        help="从需求文档生成任务板"
    )
    parser_generate.add_argument("spec_file", help="需求文档路径")
    parser_generate.add_argument("-o", "--output", help="输出文件")
    parser_generate.set_defaults(func=lambda args: cmd_generate_from_spec(args.spec_file, args.output))


def parse_variables(values):
    result = {}
    for value in values:
        if "=" not in value or not value.split("=", 1)[0]:
            raise CliError("模板变量格式应为 key=value")
        key, content = value.split("=", 1)
        if key in {"add", "task_file", "dependencies", "output_file", "template_name", "task_num"}:
            raise CliError(f"模板变量名已保留: {key}")
        result[key] = content
    return result


def dispatch(args) -> int:
    """分发命令。"""
    if hasattr(args, "func"):
        return args.func(args)
    return 1


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。"""
    parser = argparse.ArgumentParser(description="任务分析和可视化工具")
    subparsers = parser.add_subparsers(dest="command")
    register_subparsers(subparsers)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        sys.exit(dispatch(args))
    except CliError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
