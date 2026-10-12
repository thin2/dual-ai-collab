#!/usr/bin/env python3
"""CLI 工具 - 用于命令行和脚本集成。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 添加 lib 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from lib import (
    TaskBoard,
    CheckpointManager,
    ExecutionConfig,
    TaskExecutor,
    ExecutionHistory,
    CliError,
)


def cmd_init(args):
    """初始化项目"""
    project_root = Path.cwd()
    
    # 创建目录
    (project_root / "planning" / "specs").mkdir(parents=True, exist_ok=True)
    (project_root / ".task-management").mkdir(parents=True, exist_ok=True)
    
    # 创建空任务板
    from lib import write_tasks_document
    write_tasks_document({"tasks": []}, project_root / "planning" / "codex-tasks.md")
    
    # 创建默认配置
    config = ExecutionConfig(project_root)
    config.save()
    
    print("项目初始化完成")
    print(f"任务板: {project_root / 'planning' / 'codex-tasks.md'}")
    print(f"配置: {project_root / '.task-management' / 'config.json'}")


def cmd_select(args):
    """选择下一个任务"""
    board = TaskBoard.load(Path.cwd())
    task = board.get_next_task()
    
    if not task:
        print("没有可执行的任务")
        return
    
    print(f"下一个任务: {task['id']} - {task.get('title', '未命名')}")
    print(f"类型: {task.get('type', 'feature')}")
    print(f"预估: {task.get('estimated_hours', 0)}小时")
    print(f"依赖: {task.get('dependencies', '无')}")


def cmd_status(args):
    """显示任务状态"""
    board = TaskBoard.load(Path.cwd())
    stats = board.get_statistics()
    
    print(f"总任务: {stats['total']}")
    print("\n按状态:")
    for status, count in stats['by_status'].items():
        print(f"  {status}: {count}")


def cmd_plan_execution(args):
    """规划任务执行"""
    executor = TaskExecutor(Path.cwd())
    
    try:
        info = executor.get_execution_info(args.task_id)
        print(info)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_update_status(args):
    """更新任务状态"""
    board = TaskBoard.load(Path.cwd())
    
    try:
        board.update_task_status(args.task_id, args.status)
        print(f"任务 {args.task_id} 状态已更新为 {args.status}")
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_checkpoint(args):
    """Checkpoint 管理"""
    checkpoint = CheckpointManager(Path.cwd())
    
    if args.action == "check":
        print(checkpoint.check())
    elif args.action == "save":
        data = {}
        if args.data:
            for item in args.data:
                key, value = item.split("=", 1)
                data[key] = value
        checkpoint.save(args.phase, **data)
        print(f"Checkpoint 已保存: phase={args.phase}")
    elif args.action == "clear":
        checkpoint.clear()
        print("Checkpoint 已清除")


def cmd_config(args):
    """配置管理"""
    config = ExecutionConfig(Path.cwd())
    
    if args.action == "show":
        print(json.dumps(config.get_all_settings(), indent=2, ensure_ascii=False))
    elif args.action == "set":
        key, value = args.key_value.split("=", 1)
        if key.startswith("execution."):
            complexity = key.split(".", 1)[1]
            config.set_droid_for_complexity(complexity, value)
            print(f"已设置 {complexity} → {value}")
        else:
            print(f"不支持的配置键: {key}", file=sys.stderr)
            sys.exit(1)


def cmd_history(args):
    """查看执行历史"""
    history = ExecutionHistory(Path.cwd())
    
    if args.task_id:
        records = history.get_task_history(args.task_id)
    else:
        records = history.get_all_history()
    
    if not records:
        print("没有执行记录")
        return
    
    for record in records[:args.limit]:
        status_symbol = "✓" if record.status == "success" else "✗"
        duration = f"{record.duration_seconds:.1f}s" if record.duration_seconds else "运行中"
        print(f"{status_symbol} {record.task_id} - {record.start_time} - {duration} - {record.droid}")


def cmd_acceptance(args):
    """提取验收命令"""
    board = TaskBoard.load(Path.cwd())
    commands = board.get_acceptance_commands(args.task_id)
    
    if not commands:
        print("没有找到验收命令")
        return
    
    for i, cmd in enumerate(commands, 1):
        print(f"{i}. {cmd}")


def main():
    parser = argparse.ArgumentParser(description="任务管理 CLI")
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # init
    subparsers.add_parser("init", help="初始化项目")
    
    # select
    subparsers.add_parser("select", help="选择下一个任务")
    
    # status
    subparsers.add_parser("status", help="显示任务统计")
    
    # plan-execution
    p = subparsers.add_parser("plan-execution", help="规划任务执行")
    p.add_argument("task_id", help="任务 ID")
    
    # update
    p = subparsers.add_parser("update", help="更新任务状态")
    p.add_argument("task_id", help="任务 ID")
    p.add_argument("status", help="新状态")
    
    # checkpoint
    p = subparsers.add_parser("checkpoint", help="Checkpoint 管理")
    p.add_argument("action", choices=["check", "save", "clear"], help="操作")
    p.add_argument("--phase", help="阶段名称（save 时必需）")
    p.add_argument("--data", nargs="+", help="数据 key=value（save 时可选）")
    
    # config
    p = subparsers.add_parser("config", help="配置管理")
    p.add_argument("action", choices=["show", "set"], help="操作")
    p.add_argument("key_value", nargs="?", help="配置项 key=value（set 时必需）")
    
    # history
    p = subparsers.add_parser("history", help="查看执行历史")
    p.add_argument("--task-id", help="任务 ID（可选）")
    p.add_argument("--limit", type=int, default=10, help="显示数量限制")
    
    # acceptance
    p = subparsers.add_parser("acceptance", help="提取验收命令")
    p.add_argument("task_id", help="任务 ID")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        cmd_func = {
            "init": cmd_init,
            "select": cmd_select,
            "status": cmd_status,
            "plan-execution": cmd_plan_execution,
            "update": cmd_update_status,
            "checkpoint": cmd_checkpoint,
            "config": cmd_config,
            "history": cmd_history,
            "acceptance": cmd_acceptance,
        }[args.command]
        
        cmd_func(args)
    except CliError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
