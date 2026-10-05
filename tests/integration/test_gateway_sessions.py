"""Request-stream sessions, subagent lineage, harness hints and M2 placement
through the actual C gateway.

Scripted loopback providers only: proves the mechanism (no registration, no
headers, per-conversation routing, delegated first turns, private placement
when M2 vetoes a public destination), not model quality or savings."""
import copy
import json
import os
import pathlib
import subprocess
import tempfile
import time
import unittest
import test_gateway_context as base
import test_gateway_signals as signals

CAPS = {'tool_history': True, 'function_tools': True, 'parallel_tools': True}
PUBLIC_PATH = '/v1/public/chat/completions'


def call(i, arguments='{}'):
    return {'id': 'call-%d' % i, 'type': 'function', 'function': {'name': 'f', 'arguments': arguments}}


class GatewaySessionTests(unittest.TestCase):
    router = base.GatewayContextTests.router
    request = base.GatewayContextTests.request
    tools = staticmethod(signals.GatewaySignalsTests.tools)

    @staticmethod
    def setup(c, s, sessions: 'str | None' = 'request', cheap_tasks=('tool_followup_ok',)):
        signals.GatewaySignalsTests.setup(c, s, cheap_tasks=cheap_tasks)
        if sessions is not None: c['context']['sessions'] = sessions

    def body(self, history, **extra):
        return {'model': 'auto', 'messages': history, 'max_tokens': 128,
                'tools': self.tools(), 'tool_choice': 'auto', 'parallel_tool_calls': False, **extra}

    def step(self, p, sink, history, expect_status=200, headers=None, **extra):
        """One physical turn with NO scope headers; returns the model sent upstream."""
        before = len(sink.seen)
        code, raw, _ = self.request(p, headers=headers, body=self.body(history, **extra))
        self.assertEqual(code, expect_status, raw)
        if code != 200:
            self.assertEqual(len(sink.seen), before)
            return None
        history.append(json.loads(raw)['choices'][0]['message'])
        return sink.seen[-1][2]['model']

    def loop(self, p, sink, opening, results, headers=None):
        history = [{'role': 'user', 'content': opening}]
        sink.envelope = {'message': {'tool_calls': [call(1)]}}
        models = [self.step(p, sink, history, headers=headers)]
        for i, text in enumerate(results, start=1):
            history.append({'role': 'tool', 'tool_call_id': 'call-%d' % i, 'content': text})
            sink.envelope = {'message': {'tool_calls': [call(i + 1)]}}
            models.append(self.step(p, sink, history, headers=headers))
        return history, models

    @staticmethod
    def lines(sink, prefix):
        return [l for l in sink.router_stderr.decode().splitlines() if l.startswith(prefix)]

    def test_a_unregistered_conversation_is_routed_per_turn(self):
        with self.router(self.setup) as (p, sink):
            _, models = self.loop(p, sink, 'start the first job', ['wrote 3 files', 'ok'])
            self.assertEqual(models, ['frontier', 'physical', 'physical'])
        self.assertEqual(len(self.lines(sink, 'session ')), 1)
        self.assertIn(' kind=request start=1 delegated=0', self.lines(sink, 'session ')[0])
        decisions = self.lines(sink, 'route_decision ')
        self.assertIn(' class=none reason=baseline', decisions[0])
        self.assertIn(' class=tool_followup_ok reason=cheapest', decisions[1])
        self.assertNotIn(b'start the first job', sink.router_stderr)

    def test_a2_text_part_content_is_plain_text(self):
        # pi (OpenAI SDK) sends the user turn as text parts, store:false and
        # strict:false on every function. Text-only parts are plain text; any other
        # part, an extra key, no parts, or strict:true still pins.
        def parts(*texts):
            return [{'type': 'text', 'text': t} for t in texts]
        def tools(strict):
            return [{**t, 'function': {**t['function'], 'strict': strict}} for t in self.tools()]
        with self.router(self.setup) as (p, sink):
            history = [{'role': 'system', 'content': 'You are a coding agent.'},
                       {'role': 'user', 'content': parts('start the first job', 'then report')}]
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            models = [self.step(p, sink, history, store=False, tools=tools(False))]
            for i, text in enumerate(['wrote 3 files', 'ok'], start=1):
                history.append({'role': 'tool', 'tool_call_id': 'call-%d' % i, 'content': text})
                sink.envelope = {'message': {'tool_calls': [call(i + 1)]}}
                models.append(self.step(p, sink, history, store=False, tools=tools(False)))
            self.assertEqual(models, ['frontier', 'physical', 'physical'])
        with self.router(self.setup) as (p, sink):
            history = [{'role': 'user', 'content': 'start'}]
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            models = [self.step(p, sink, history, tools=tools(True))]
            history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'wrote 3 files'})
            models.append(self.step(p, sink, history, tools=tools(True)))
            self.assertNotIn('physical', models)
        image = {'type': 'image_url', 'image_url': {'url': 'https://example.test/a.png'}}
        for opening in (parts('start') + [image], [{'type': 'text', 'text': 'start', 'cache_control': {'type': 'ephemeral'}}], []):
            with self.subTest(opening=opening), self.router(self.setup) as (p, sink):
                _, models = self.loop(p, sink, opening, ['wrote 3 files', 'ok'])
                self.assertNotIn('physical', models)

    def test_b_default_and_headers_mode_leave_unregistered_requests_at_baseline(self):
        for sessions in (None, 'headers'):
            with self.subTest(sessions=sessions):
                with self.router(lambda c, s: self.setup(c, s, sessions=sessions)) as (p, sink):
                    _, models = self.loop(p, sink, 'start the first job', ['wrote 3 files'])
                    self.assertEqual(models, ['frontier', 'frontier'])
                self.assertEqual(self.lines(sink, 'session '), [])

    def test_c_interleaved_conversations_keep_separate_state(self):
        with self.router(self.setup) as (p, sink):
            one = [{'role': 'user', 'content': 'conversation one'}]
            two = [{'role': 'user', 'content': 'conversation two'}]
            same = [{'role': 'user', 'content': 'conversation one'}]  # identical opening, separate run
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            self.assertEqual(self.step(p, sink, one), 'frontier')
            self.assertEqual(self.step(p, sink, two), 'frontier')
            self.assertEqual(self.step(p, sink, same), 'frontier')
            one.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'fine'})
            two.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'Traceback: boom'})
            same.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'fine too'})
            sink.envelope = {'message': {'tool_calls': [call(2)]}}
            self.assertEqual(self.step(p, sink, two), 'frontier')   # a failure keeps the baseline
            self.assertEqual(self.step(p, sink, one), 'physical')
            self.assertEqual(self.step(p, sink, same), 'physical')
            one.append({'role': 'tool', 'tool_call_id': 'call-2', 'content': 'still fine'})
            self.assertEqual(self.step(p, sink, one), 'physical')
        self.assertEqual(len(self.lines(sink, 'session ')), 3)

    def test_d_unknown_mid_conversation_request_pins_to_baseline(self):
        with self.router(self.setup) as (p, sink):
            history = [{'role': 'user', 'content': 'resumed elsewhere'},
                       {'role': 'assistant', 'content': None, 'tool_calls': [call(1)]},
                       {'role': 'tool', 'tool_call_id': 'call-1', 'content': 'ok'}]
            sink.envelope = {'message': {'tool_calls': [call(2)]}}
            self.assertEqual(self.step(p, sink, history), 'frontier')
            history.append({'role': 'tool', 'tool_call_id': 'call-2', 'content': 'ok'})
            self.assertEqual(self.step(p, sink, history), 'frontier')
        # One adopted session, reused: not one new session per request.
        self.assertEqual(len(self.lines(sink, 'session ')), 1)
        self.assertIn(' start=0 ', self.lines(sink, 'session ')[0])

    def test_e_modified_history_never_downshifts(self):
        with self.router(self.setup) as (p, sink):
            history, models = self.loop(p, sink, 'start the first job', ['ok'])
            self.assertEqual(models, ['frontier', 'physical'])
            history[0]['content'] = 'start the first job'  # unchanged opening, edited middle
            history[2]['content'] = 'edited tool result'
            history.append({'role': 'tool', 'tool_call_id': 'call-2', 'content': 'ok'})
            sink.envelope = {'message': {'tool_calls': [call(3)]}}
            # No session continues this history: it is adopted pinned at the baseline.
            self.assertEqual(self.step(p, sink, history), 'frontier')

    def delegated(self, goal_sent, goal_asked, cheap_tasks=('tool_followup_ok', 'delegated_start')):
        with self.router(lambda c, s: self.setup(c, s, cheap_tasks=cheap_tasks)) as (p, sink):
            parent = [{'role': 'user', 'content': 'build three modules, delegate each'}]
            sink.envelope = {'message': {'tool_calls': [call(1, json.dumps({'tasks': [{'goal': goal_asked, 'context': 'x'}]}))]}}
            self.assertEqual(self.step(p, sink, parent), 'frontier')
            child = [{'role': 'system', 'content': 'You are a subagent.'}, {'role': 'user', 'content': goal_sent}]
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            first = self.step(p, sink, child)
            child.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'ok'})
            second = self.step(p, sink, child)
            # The parent continues normally once its delegate call returns.
            parent.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'child finished'})
            sink.envelope = {'message': {'tool_calls': [call(2)]}}
            after = self.step(p, sink, parent)
        return first, second, after, sink

    def test_f_subagent_is_recognised_from_the_request_stream(self):
        goal = 'Implement textkit/slug.py with slugify(text, max_len=50).'
        first, second, after, sink = self.delegated(goal, goal)
        # The orchestrator's step after its delegate call returns integrates and
        # reviews the subagent's work: it stays on the baseline.
        self.assertEqual((first, second, after), ('physical', 'physical', 'frontier'))
        self.assertEqual(len(self.lines(sink, 'route_hold ')), 1)
        self.assertIn(' delegated=1 lineage=request', self.lines(sink, 'session ')[1])
        self.assertIn(' class=delegated_start reason=cheapest', self.lines(sink, 'route_decision ')[1])
        self.assertNotIn(b'slugify', sink.router_stderr)

    def test_f_unrelated_or_unqualified_first_turn_stays_baseline(self):
        goal = 'Implement textkit/slug.py with slugify(text, max_len=50).'
        first, second, _, sink = self.delegated(goal + ' extra', goal)
        self.assertEqual((first, second), ('frontier', 'physical'))
        self.assertIn(' delegated=0 lineage=none', self.lines(sink, 'session ')[1])
        first, _, _, sink = self.delegated('short', 'short')   # trivial strings never match
        self.assertEqual(first, 'frontier')
        first, second, _, sink = self.delegated(goal, goal, cheap_tasks=('tool_followup_ok',))
        self.assertEqual((first, second), ('frontier', 'physical'))  # recognised, but not qualified
        self.assertIn(' delegated=1 ', self.lines(sink, 'session ')[1])

    def hint(self, p, body, source=True):
        return self.request(p, path='/v1/context/hint', source=source, body=body)[0]

    def test_g_harness_hint_marks_a_delegated_session(self):
        with self.router(lambda c, s: self.setup(c, s, cheap_tasks=('tool_followup_ok', 'delegated_start'))) as (p, sink):
            self.assertEqual(self.hint(p, {'session_id': 'child-1', 'role': 'leaf'}, source=False), 401)
            self.assertEqual(self.hint(p, {'session_id': 'child-1', 'role': 'root'}), 400)
            self.assertEqual(self.hint(p, {'session_id': 'child 1', 'role': 'leaf'}), 400)
            self.assertEqual(self.hint(p, {'session_id': 'child-1', 'role': 'leaf', 'extra': 1}), 400)
            self.assertEqual(self.hint(p, {'session_id': 'child-1', 'role': 'leaf', 'parent_session_id': 'parent-1'}), 202)
            self.assertEqual(self.hint(p, {'session_id': 'parent-1', 'role': 'orchestrator'}), 202)
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            child = [{'role': 'user', 'content': 'a delegated goal nobody announced in a tool call'}]
            self.assertEqual(self.step(p, sink, child, headers={'X-Recursant-session-id': 'child-1'}), 'physical')
            parent = [{'role': 'user', 'content': 'the orchestrating conversation'}]
            self.assertEqual(self.step(p, sink, parent, headers={'X-Recursant-session-id': 'parent-1'}), 'frontier')
            other = [{'role': 'user', 'content': 'a session with no hint at all'}]
            self.assertEqual(self.step(p, sink, other, headers={'X-Recursant-session-id': 'other-1'}), 'frontier')
            # Same opening under two session ids: two sessions, not one.
            twin = [{'role': 'user', 'content': 'a session with no hint at all'}]
            self.assertEqual(self.step(p, sink, twin, headers={'X-Recursant-session-id': 'other-2'}), 'frontier')
            other.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'ok'})
            self.assertEqual(self.step(p, sink, other, headers={'X-Recursant-session-id': 'other-1'}), 'physical')
        sessions = self.lines(sink, 'session ')
        self.assertEqual(len(sessions), 4)
        self.assertIn(' delegated=1 lineage=hint', sessions[0])
        self.assertEqual(len(self.lines(sink, 'session_hint ')), 2)
        with self.router(lambda c, s: self.setup(c, s, sessions='headers')) as (p, sink):
            self.assertEqual(self.hint(p, {'session_id': 'child-1', 'role': 'leaf'}), 404)

    @staticmethod
    def compliant(c, s, private_candidate=True):
        GatewaySessionTests.setup(c, s)
        c['compliance'] = {'enabled': True, 'public_allowed': True}
        c['aliases'].append({'from': 'cheap', 'endpoint': 'public', 'model': 'cheap-physical'})
        c['context']['candidates'][1].update(alias='cheap')
        if private_candidate:
            c['context']['candidates'].append({'alias': 'alias', 'quality_evidence': 'operator-fixture-private',
                'qualified_tasks': [], 'context_limit': 100000, 'expected_task_cost': 50.0, 'capabilities': dict(CAPS)})

    def test_h_pii_mid_session_moves_to_the_private_candidate(self):
        with self.router(self.compliant) as (p, sink):
            history, models = self.loop(p, sink, 'summarise the customer file', ['read 3 rows', 'row: alice@example.com'])
            # Turn 3 carries PII: the private model continues the session.
            self.assertEqual(models, ['frontier', 'cheap-physical', 'physical'])
            history.append({'role': 'tool', 'tool_call_id': 'call-3', 'content': 'done'})
            sink.envelope = {'message': {'tool_calls': [call(4)]}}
            self.assertEqual(self.step(p, sink, history), 'physical')   # PII is still in the history
            public = [x for x in sink.seen if x[0] == PUBLIC_PATH]
            self.assertEqual([x[2]['model'] for x in public], ['frontier', 'cheap-physical'])
            self.assertFalse([x for x in public if 'alice@example.com' in json.dumps(x[2])])
        decisions = self.lines(sink, 'route_decision ')
        self.assertIn(' reason=compliance chosen=alias', decisions[2])
        self.assertIn(' reason=compliance chosen=alias', decisions[3])
        self.assertNotIn(b'alice', sink.router_stderr)

    def test_h_pii_in_the_first_request_starts_private(self):
        with self.router(self.compliant) as (p, sink):
            _, models = self.loop(p, sink, 'email alice@example.com about it', ['ok'])
            self.assertEqual(models, ['physical', 'physical'])
            self.assertFalse([x for x in sink.seen if x[0] == PUBLIC_PATH])

    def test_h_without_a_capable_private_candidate_m2_still_rejects(self):
        with self.router(lambda c, s: self.compliant(c, s, private_candidate=False)) as (p, sink):
            history = [{'role': 'user', 'content': 'summarise the customer file'}]
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            self.assertEqual(self.step(p, sink, history), 'frontier')
            history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'row: alice@example.com'})
            self.assertIsNone(self.step(p, sink, history, expect_status=403))
            self.assertFalse([x for x in sink.seen if 'alice@example.com' in json.dumps(x[2])])

    def test_h_pinned_public_session_is_rejected_not_moved(self):
        with self.router(self.compliant) as (p, sink):
            history = [{'role': 'user', 'content': 'resumed elsewhere'},
                       {'role': 'assistant', 'content': None, 'tool_calls': [call(1)]},
                       {'role': 'tool', 'tool_call_id': 'call-1', 'content': 'ok'}]
            sink.envelope = {'message': {'tool_calls': [call(2)]}}
            self.assertEqual(self.step(p, sink, history), 'frontier')   # adopted, pinned
            # Continuity of a pinned session is unknown: M2 rejects rather than
            # letting another model continue it (same rule as registered scopes).
            history.append({'role': 'tool', 'tool_call_id': 'call-2', 'content': 'row: alice@example.com'})
            self.assertIsNone(self.step(p, sink, history, expect_status=403))
            self.assertFalse([x for x in sink.seen if 'alice@example.com' in json.dumps(x[2])])
        self.assertFalse([l for l in self.lines(sink, 'route_decision ') if 'reason=compliance' in l])

    def test_i_many_sessions_never_reject_and_old_idle_ones_are_reused(self):
        def edit(c, s):
            self.setup(c, s); c['context']['ttl_ms'] = 200
        with self.router(edit) as (p, sink):
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            first = [{'role': 'user', 'content': 'conversation number 0'}]
            self.assertEqual(self.step(p, sink, first), 'frontier')
            for i in range(1, 128):   # fills the request-session table
                self.assertEqual(self.step(p, sink, [{'role': 'user', 'content': 'conversation number %d' % i}]), 'frontier')
            time.sleep(0.5)           # every session is now idle past the TTL
            for i in range(128, 134): # each new one reuses the oldest idle session
                self.assertEqual(self.step(p, sink, [{'role': 'user', 'content': 'conversation number %d' % i}]), 'frontier')
            # The first session was reclaimed while idle: it resumes pinned at baseline.
            first.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'ok'})
            self.assertEqual(self.step(p, sink, first), 'frontier')

    def test_j_streamed_reasoning_text_does_not_freeze_the_session(self):
        """vLLM-served models stream readable reasoning beside the tool call; the
        harness does not replay it, so the session stays routable."""
        def edit(c, s, drop=True):
            self.setup(c, s)
            c['context']['candidates'][1]['capabilities']['stream_tools'] = True
            if drop: c['context']['reasoning_text'] = 'drop'
        events = [{'choices': [{'index': 0, 'delta': {'role': 'assistant', 'reasoning': 'Read the file first.', 'content': ''}, 'finish_reason': None}]},
                  {'choices': [{'index': 0, 'delta': {'tool_calls': [{'index': 0, 'id': 'call-1', 'type': 'function',
                                'function': {'name': 'f', 'arguments': '{}'}}]}, 'finish_reason': None}]},
                  {'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls'}]}]
        with self.router(edit) as (p, sink):
            sink.stream_wire = b''.join(b'data: ' + json.dumps(e).encode() + b'\n\n' for e in events) + b'data: [DONE]\n\n'
            history = [{'role': 'user', 'content': 'stream a tool call with reasoning'}]
            code, _, _ = self.request(p, body=self.body(history, stream=True))
            self.assertEqual(code, 200)
            history.append({'role': 'assistant', 'content': '', 'tool_calls': [call(1)]})
            history.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'ok'})
            sink.stream_wire = None; sink.envelope = {'message': {'tool_calls': [call(2)]}}
            self.assertEqual(self.step(p, sink, history), 'physical')
        self.assertFalse([l for l in self.lines(sink, 'route_decision ') if 'reason=pin' in l])
        # Default ("pin"): the same stream pins the session, as before.
        with self.router(lambda c, s: edit(c, s, drop=False)) as (p, sink):
            sink.stream_wire = b''.join(b'data: ' + json.dumps(e).encode() + b'\n\n' for e in events) + b'data: [DONE]\n\n'
            history = [{'role': 'user', 'content': 'stream a tool call with reasoning'}]
            self.assertEqual(self.request(p, body=self.body(history, stream=True))[0], 200)
            history += [{'role': 'assistant', 'content': '', 'tool_calls': [call(1)]},
                        {'role': 'tool', 'tool_call_id': 'call-1', 'content': 'ok'}]
            sink.stream_wire = None; sink.envelope = {'message': {'tool_calls': [call(2)]}}
            self.assertEqual(self.step(p, sink, history), 'frontier')

    def test_k_harness_label_keeps_a_session_private(self):
        """A harness data label only ever restricts: once a session is labelled
        restricted, every later request in it goes to private inference."""
        PRIVATE_PATH = '/v1/chat/completions'
        with self.router(self.setup) as (p, sink):
            for bad in ({'session_id': 's1', 'data': 'secret'}, {'session_id': 's1'},
                        {'session_id': 's1', 'data': True}, {'session_id': 's1', 'data': None}):
                self.assertEqual(self.hint(p, bad), 400, bad)
            self.assertEqual(self.hint(p, {'session_id': 's1', 'data': 'restricted'}, source=False), 401)
            # Labelled before its first request.
            self.assertEqual(self.hint(p, {'session_id': 'early', 'data': 'restricted'}), 202)
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            early = [{'role': 'user', 'content': 'a labelled conversation from the start'}]
            self.assertEqual(self.step(p, sink, early, headers={'X-Recursant-session-id': 'early'}), 'physical')
            self.assertEqual(sink.seen[-1][0], PRIVATE_PATH)
            # Labelled mid-session: public before, private after, for good.
            late = [{'role': 'user', 'content': 'a conversation labelled later'}]
            hs = {'X-Recursant-session-id': 'late'}
            self.assertEqual(self.step(p, sink, late, headers=hs), 'frontier')
            self.assertEqual(sink.seen[-1][0], PUBLIC_PATH)
            self.assertEqual(self.hint(p, {'session_id': 'late', 'data': 'restricted', 'role': 'orchestrator'}), 202)
            for i in (1, 2):
                late.append({'role': 'tool', 'tool_call_id': 'call-%d' % i, 'content': 'ok'})
                sink.envelope = {'message': {'tool_calls': [call(i + 1)]}}
                self.assertEqual(self.step(p, sink, late, headers=hs), 'physical')
                self.assertEqual(sink.seen[-1][0], PRIVATE_PATH)
            # Unlabelled sessions are unaffected.
            other = [{'role': 'user', 'content': 'an unlabelled conversation'}]
            self.assertEqual(self.step(p, sink, other, headers={'X-Recursant-session-id': 'other'}), 'frontier')
        self.assertIn(' data=restricted', self.lines(sink, 'session ')[0])
        self.assertTrue([l for l in self.lines(sink, 'session_hint ') if 'data=restricted' in l])

    def test_k_label_table_refuses_rather_than_forgets(self):
        with self.router(self.setup) as (p, sink):
            for i in range(256):
                self.assertEqual(self.hint(p, {'session_id': 'label-%d' % i, 'data': 'restricted'}), 202)
            self.assertEqual(self.hint(p, {'session_id': 'label-0', 'data': 'restricted'}), 202)  # already held
            self.assertEqual(self.hint(p, {'session_id': 'one-too-many', 'data': 'restricted'}), 503)
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            first = [{'role': 'user', 'content': 'the first labelled conversation'}]
            self.assertEqual(self.step(p, sink, first, headers={'X-Recursant-session-id': 'label-0'}), 'physical')

    def test_l_full_capacity_candidate_is_not_offered(self):
        """max_inflight: a slow private destination takes routine steps only while
        it has free capacity; otherwise the step uses the next cheapest option."""
        import threading
        def edit(c, s):
            self.setup(c, s)
            c['context']['candidates'][1]['max_inflight'] = 1   # 'alias' -> private 'physical'
        with self.router(edit) as (p, sink):
            sink.envelope = {'message': {'tool_calls': [call(1)]}}
            a = [{'role': 'user', 'content': 'conversation A'}]
            b = [{'role': 'user', 'content': 'conversation B'}]
            self.assertEqual(self.step(p, sink, a), 'frontier')
            self.assertEqual(self.step(p, sink, b), 'frontier')
            a.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'ok'})
            b.append({'role': 'tool', 'tool_call_id': 'call-1', 'content': 'ok'})
            sink.envelope = {'message': {'tool_calls': [call(2)]}}
            sink.chat_delay = 1.0
            results = []
            worker = threading.Thread(target=lambda: results.append(self.request(p, body=self.body(a))))
            worker.start()
            for _ in range(100):   # wait until A is running on the capacity-limited model
                if any(x[2]['model'] == 'physical' for x in sink.seen): break
                time.sleep(0.01)
            sink.chat_delay = 0
            self.assertEqual(self.step(p, sink, b), 'frontier')   # 'physical' is full
            worker.join()
            self.assertEqual(results[0][0], 200)
            a.append(json.loads(results[0][1])['choices'][0]['message'])
            b.append({'role': 'tool', 'tool_call_id': 'call-2', 'content': 'ok'})
            sink.envelope = {'message': {'tool_calls': [call(3)]}}
            self.assertEqual(self.step(p, sink, b), 'physical')   # capacity released
        busy = [l for l in self.lines(sink, 'route_decision ') if 'alias:' in l and '(denied)' in l]
        self.assertEqual(len(busy), 1)

    def test_strict_session_configuration(self):
        import test_router
        cfg0 = {'listen': {'host': '127.0.0.1', 'port': 12345},
                'private': {'url': 'http://127.0.0.1:1/v1', 'model': 'physical'},
                'auth': {'api_key_env': 'RC_TEST_AUTH'},
                'aliases': [{'from': 'alias', 'endpoint': 'private', 'model': 'physical'}]}
        class S: pass
        self.setup(cfg0, S())
        cheap = lambda c: c['context']['candidates'][1]
        bad = [lambda c: c['context'].update(sessions='on'),
               lambda c: c['context'].update(reasoning_text='keep'),
               lambda c: cheap(c).update(max_inflight=0),
               lambda c: cheap(c).update(max_inflight='1'),
               lambda c: cheap(c).update(max_inflight=5000),
               lambda c: c['context'].update(reasoning_text=True),
               lambda c: c['context'].update(sessions=True),
               lambda c: c['context'].update(sessions='Request'),
               lambda c: cheap(c).update(qualified_tasks=['delegated_start', 'delegated_start']),
               lambda c: cheap(c).update(qualified_tasks=['format_simple', 'tool_followup_ok', 'final_answer', 'delegated_start', 'final_answer'])]
        good = [lambda c: None,
                lambda c: c['context'].update(sessions='headers'),
                lambda c: c['context'].update(reasoning_text='drop'),
                lambda c: c['context'].update(reasoning_text='pin'),
                lambda c: cheap(c).update(max_inflight=1),
                lambda c: c['context'].pop('sessions'),
                lambda c: cheap(c).update(qualified_tasks=['format_simple', 'tool_followup_ok', 'final_answer', 'delegated_start'])]
        env = {**os.environ, 'RC_TEST_AUTH': 'local-test-key', 'RC_TEST_SOURCE': 'source-only-test-key'}
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'cfg.json'
            for expect, mutations in ((False, bad), (True, good)):
                for mutate in mutations:
                    cfg = copy.deepcopy(cfg0); mutate(cfg); path.write_text(json.dumps(cfg))
                    result = subprocess.run([str(test_router.BIN), 'validate', str(path), '--test-mode'], env=env, capture_output=True)
                    self.assertEqual(result.returncode == 0, expect, (cfg['context'], result.stderr))
                    self.assertNotIn(b'AddressSanitizer', result.stderr)


if __name__ == '__main__':
    unittest.main()
