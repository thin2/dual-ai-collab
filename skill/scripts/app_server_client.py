"""Bounded JSONL/stdio client for the stable Codex app-server protocol.

Checked against codex-cli 0.160.1. No network listener or automatic approval.
"""
from __future__ import annotations

from collections import deque
import json
import queue
import subprocess
import threading
import time

from tasks_store import CliError
from platform_utils import terminate_process_tree


class AppServerClient:
    def __init__(self, command, *, cwd, stderr, on_message=None, timeout=30):
        self.timeout = timeout
        self.on_message = on_message or (lambda message: None)
        self.incoming = queue.Queue()
        self.notifications = deque()
        self.responses = {}
        self.attention_required = []
        self.sequence = 0
        self.process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=stderr,
                                        text=True, encoding='utf-8', bufsize=1)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in self.process.stdout:
                try:
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ValueError('expected JSON object')
                    self.incoming.put(value)
                except ValueError as exc:
                    self.incoming.put(CliError(f'app-server 协议输出无效: {exc}'))
                    return
        except (OSError, UnicodeError) as exc:
            self.incoming.put(CliError(f'app-server 输出读取失败: {exc}'))
        finally:
            self.incoming.put(CliError('app-server 连接已关闭'))

    def send(self, message):
        try:
            self.process.stdin.write(json.dumps(message, ensure_ascii=False) + '\n')
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise CliError(f'app-server 连接写入失败: {exc}') from exc

    def request(self, method, params):
        self.sequence += 1
        request_id = self.sequence
        self.send({'id': request_id, 'method': method, 'params': params})
        return request_id

    def _server_request(self, message):
        method = message['method']
        self.attention_required.append({'method': method, 'params': message.get('params', {})})
        if method in ('item/commandExecution/requestApproval', 'item/fileChange/requestApproval'):
            response = {'result': {'decision': 'decline'}}
        elif method == 'item/tool/requestUserInput':
            response = {'result': {'answers': {}}}
        elif method == 'mcpServer/elicitation/request':
            response = {'result': {'action': 'decline', 'content': None}}
        else:
            response = {'error': {'code': -32601, 'message': 'Client does not support this request'}}
        self.send({'id': message['id'], **response})

    def pump(self, timeout=0.1):
        try:
            message = self.incoming.get(timeout=timeout)
        except queue.Empty:
            return
        if isinstance(message, Exception):
            raise message
        self.on_message(message)
        if 'method' in message:
            if 'id' in message:
                self._server_request(message)
            else:
                self.notifications.append(message)
        elif 'id' in message:
            self.responses[message['id']] = message
        else:
            raise CliError('app-server 消息缺少 method/id')

    def call(self, method, params, timeout=None):
        request_id = self.request(method, params)
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while request_id not in self.responses:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CliError(f'app-server 请求超时: {method}')
            self.pump(min(0.1, remaining))
        response = self.responses.pop(request_id)
        if 'error' in response:
            raise CliError(f"app-server {method}: {response['error']}")
        if 'result' not in response:
            raise CliError(f'app-server {method}: 缺少 result')
        return response['result']

    def initialize(self):
        result = self.call('initialize', {'clientInfo': {
            'name': 'dual_ai_collab', 'title': 'Dual AI Collaboration', 'version': '0.1.0'}})
        self.send({'method': 'initialized', 'params': {}})
        return result

    def close(self):
        if self.process.poll() is None:
            try:
                self.process.stdin.close()
                self.process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                terminate_process_tree(self.process.pid, force=False)
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    terminate_process_tree(self.process.pid, force=True)
                    self.process.wait(timeout=3)
        for stream in (self.process.stdin, self.process.stdout):
            if stream and not stream.closed:
                stream.close()
        self.reader.join(timeout=1)
