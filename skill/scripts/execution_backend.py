"""Common capability-based facade for CLI and session execution backends."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from tasks_store import CliError


@dataclass
class ExecutionBackend:
    name: str
    operations: dict[str, Callable]

    def capabilities(self) -> dict[str, bool]:
        return {name: name in self.operations for name in
                ('start', 'status', 'stop', 'continue', 'steer', 'events', 'complete')}

    def call(self, operation: str, *args, **kwargs):
        handler = self.operations.get(operation)
        if handler is None:
            raise CliError(f'{self.name} 后端不支持 {operation}；请查看 run capabilities')
        return handler(*args, **kwargs)
