#!/usr/bin/env python3
"""Deterministic protocol peer; no model/network access."""
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

thread_id, turn_id, prompt = None, None, ''
initialized = False
ready = False
sessions = Path('.fake-sessions.json')


def send(data):
    print(json.dumps(data), flush=True)


def reply(message, data):
    send({'id': message['id'], 'result': data})


def event(method, params):
    send({'method': method, 'params': params})


def finish(status='completed'):
    result = {'result': 'DONE', 'summary': 'fixture done', 'files_changed': ['artifact.txt'],
              'acceptance': [], 'verification': [], 'notes': []}
    event('item/completed', {'threadId': thread_id, 'turnId': turn_id,
                            'item': {'id': 'final', 'type': 'agentMessage', 'text': json.dumps(result)}})
    event('turn/completed', {'threadId': thread_id, 'turn': {'id': turn_id, 'status': status, 'error': None}})


for line in sys.stdin:
    message = json.loads(line)
    method, params = message.get('method'), message.get('params', {})
    if method == 'initialize':
        initialized = True
        reply(message, {'userAgent': 'fixture/1'})
    elif method == 'initialized':
        ready = True
    elif method in ('thread/start', 'thread/resume'):
        assert initialized and ready
        assert params['approvalPolicy'] == 'never'
        assert params['sandbox'] in ('read-only', 'workspace-write', 'danger-full-access')
        ids = json.loads(sessions.read_text()) if sessions.exists() else []
        if method == 'thread/resume':
            thread_id = params['threadId']
            if thread_id not in ids:
                send({'id': message['id'], 'error': {'code': -32000, 'message': 'unknown thread'}})
                continue
        else:
            thread_id = 'thread-' + uuid4().hex
            ids.append(thread_id)
            sessions.write_text(json.dumps(ids))
        event('thread/started', {'thread': {'id': thread_id}})
        reply(message, {'thread': {'id': thread_id}})
    elif method == 'turn/start':
        assert params['threadId'] == thread_id
        turn_id = 'turn-' + uuid4().hex
        prompt = params['input'][0]['text']
        event('item/agentMessage/delta', {'threadId': thread_id, 'turnId': turn_id, 'delta': 'working'})
        reply(message, {'turn': {'id': turn_id, 'status': 'inProgress'}})
        if prompt == 'DISCONNECT':
            raise SystemExit(1)
        if prompt == 'WAIT':
            continue
        if prompt == 'APPROVAL':
            send({'id': 'approval-1', 'method': 'item/commandExecution/requestApproval',
                  'params': {'threadId': thread_id, 'turnId': turn_id, 'command': 'unsafe'}})
            continue
        Path('artifact.txt').write_text('good' if '修复' in prompt else 'bad')
        finish()
    elif method == 'turn/steer':
        assert params['expectedTurnId'] == turn_id
        reply(message, {'turnId': turn_id})
        Path('steered.txt').write_text(params['input'][0]['text'])
        # Remain running to exercise subsequent interruption.
    elif method == 'turn/interrupt':
        assert params['turnId'] == turn_id
        reply(message, {})
        finish('interrupted')
    elif method is None and message.get('id') == 'approval-1':
        assert message['result']['decision'] == 'decline'
        finish()
    else:
        send({'id': message.get('id'), 'error': {'code': -32601, 'message': 'unknown method'}})
