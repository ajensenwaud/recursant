"""Regression: a subagent delegated by Hermes must finish and return inside the one-shot
runner (previously background children were killed when the parent's turn ended).
Scripted, no inference: the meter answers parent and child requests by inspecting each request."""
import json
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from bench.evaluation import run as base
from bench.evaluation.meter import Meter

PARENT_PROMPT = 'Delegate writing child.txt to a subagent, then check it.'


class DelegatingMeter(Meter):
    def dispatch(self, body, task_id, arm):
        with self.lock:
            if len(self.calls) >= self.request_cap:
                return 429, b'{"error":"request_cap"}', 'application/json'
            call = dict(dispatch_id=uuid.uuid4().hex, task_id=task_id, arm=arm, attempt=len(self.calls) + 1,
                        role='main', evidence_kind='fixture', cost_usd=None, started_at=time.time())
            self.calls.append(call)
            self.traces.append({'dispatch_id': call['dispatch_id'], 'request': body})
        msgs = body.get('messages') or []
        users = [m for m in msgs if m.get('role') == 'user']
        is_parent = bool(users) and PARENT_PROMPT in str(users[0].get('content'))
        step = sum(1 for m in msgs if m.get('role') == 'assistant')
        call['who'] = 'parent' if is_parent else 'child'
        if is_parent:
            script = [('delegate_task', {'goal': 'Create the file /workspace/child.txt containing the word ok.'}),
                      ('terminal', {'command': 'cat /workspace/child.txt'})]
        else:
            script = [('terminal', {'command': 'echo ok > /workspace/child.txt'})]
        message = {'role': 'assistant', 'content': 'scripted'}
        finish = 'stop'
        if step < len(script):
            name, args = script[step]
            message['tool_calls'] = [dict(index=0, id='d%d_%s' % (step, call['who']), type='function',
                                          function=dict(name=name, arguments=json.dumps(args)))]
            finish = 'tool_calls'
        else:
            message['content'] = 'child done: wrote child.txt' if not is_parent else 'parent done'
        chunks = [dict(id=call['dispatch_id'], object='chat.completion.chunk', created=1, model='fixture',
                       choices=[dict(index=0, delta=message, finish_reason=None)]),
                  dict(id=call['dispatch_id'], object='chat.completion.chunk', created=1, model='fixture',
                       choices=[dict(index=0, delta={}, finish_reason=finish)])]
        if body.get('stream'):
            raw = (''.join('data: ' + json.dumps(c) + '\n\n' for c in chunks) + 'data: [DONE]\n\n').encode()
            mime = 'text/event-stream'
        else:
            raw = json.dumps(dict(id=call['dispatch_id'], object='chat.completion', created=1, model='fixture',
                                  choices=[dict(index=0, message=message, finish_reason=finish)])).encode()
            mime = 'application/json'
        call['finished_at'] = time.time(); call['status'] = 200
        return 200, raw, mime


class SubagentCompletionTest(unittest.TestCase):
    def test_delegated_child_finishes_and_result_returns_to_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            meters = []

            def fixture_meter():
                m = DelegatingMeter(mode='fixture', request_cap=20); meters.append(m); return m

            def verifier(workspace, out):
                f = workspace / 'child.txt'
                ok = f.exists() and f.read_text().strip() == 'ok'
                return dict(success=ok, passed=int(ok), total=1)

            task = dict(id='delegate-regression', prompt=PARENT_PROMPT)
            settings = dict(base.SETTINGS, turns=10, deadline_s=240)
            row = base.run_episode(task, 'baseline-direct', Path(tmp) / 'ep', settings,
                                   fixture_meter=fixture_meter, verifier=verifier)
            who = [c.get('who') for c in meters[0].calls]
            self.assertIn('child', who, who)
            self.assertTrue(row['success'], row.get('verifier'))
            # Parent must get a turn AFTER the child finished (its cat command), then finish.
            last_child = max(i for i, w in enumerate(who) if w == 'child')
            self.assertTrue(any(w == 'parent' for w in who[last_child + 1:]), who)
            self.assertEqual(row['hook_counts'].get('subagent_stop'), 1, row['hook_counts'])
            self.assertTrue(row.get('harness_completed'))


if __name__ == '__main__':
    unittest.main()
