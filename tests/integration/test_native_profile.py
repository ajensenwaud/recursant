"""Operator-qualified native Hermes request profile through the actual C gateway.

Real Hermes sends stream:true + stream_options.include_usage + reasoning_effort
+ ~19 nested JSON-schema tools (>16 KB). These are now REQUIREMENTS a
destination must declare (capabilities stream_tools / nested_tool_schemas /
reasoning_effort tokens), not permanent pins. Scripted loopback providers
only: proves the mechanism, not model quality or savings. No live inference."""
import copy
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
import test_gateway_context as base

FIXTURE = pathlib.Path(__file__).resolve().parent / 'fixtures' / 'hermes_native_profile.json'
FULL_CAPS = {'tool_history': True, 'function_tools': True, 'parallel_tools': True,
             'stream_tools': True, 'nested_tool_schemas': True,
             'reasoning_effort': ['low', 'medium', 'high']}


def nested_tools(count=19, pad=1200):
    """Synthetic Hermes-like nested schemas, total well above 16 KB."""
    tools = []
    for i in range(count):
        tools.append({'type': 'function', 'function': {
            'name': 'tool_%d' % i, 'description': 'fixture tool %d ' % i + 'x' * pad,
            'parameters': {'type': 'object', 'properties': {
                'command': {'type': 'string', 'description': 'shell command'},
                'operations': {'type': 'array', 'maxItems': 8, 'items': {'type': 'object', 'properties': {
                    'mode': {'type': 'string', 'enum': ['read', 'write']},
                    'target': {'anyOf': [{'type': 'string'}, {'type': 'null'}]}},
                    'required': ['mode'], 'additionalProperties': False}},
                'timeout': {'type': 'integer', 'minimum': 1, 'default': 30}},
                'required': ['command']}}})
    return tools


def tool_sse(name, call_id='call-1', arguments='{"command":"ls"}'):
    events = [
        {'id': 'x', 'object': 'chat.completion.chunk', 'created': 1, 'model': 'fixture',
         'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': 'Scripted fixture step; no inference.',
            'tool_calls': [{'index': 0, 'id': call_id, 'type': 'function',
                            'function': {'name': name, 'arguments': arguments[:5]}}]}, 'finish_reason': None}]},
        {'id': 'x', 'object': 'chat.completion.chunk', 'created': 1, 'model': 'fixture',
         'choices': [{'index': 0, 'delta': {'tool_calls': [{'index': 0, 'function': {'arguments': arguments[5:]}}]},
                      'finish_reason': None}]},
        {'id': 'x', 'object': 'chat.completion.chunk', 'created': 1, 'model': 'fixture',
         'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls'}]},
        {'id': 'x', 'object': 'chat.completion.chunk', 'created': 1, 'model': 'fixture', 'choices': [],
         'usage': {'prompt_tokens': 9000, 'completion_tokens': 20, 'total_tokens': 9020}}]
    assistant = {'role': 'assistant', 'content': 'Scripted fixture step; no inference.',
                 'tool_calls': [{'id': call_id, 'type': 'function', 'function': {'name': name, 'arguments': arguments}}]}
    return base.GatewayContextTests.stream_bytes(events), assistant


class NativeProfileTests(unittest.TestCase):
    router = base.GatewayContextTests.router
    request = base.GatewayContextTests.request
    configure = staticmethod(base.GatewayContextTests.configure)
    open_scope = base.GatewayContextTests.open_scope
    headers = staticmethod(base.GatewayContextTests.headers)

    @staticmethod
    def setup(c, s, caps=None, compliance=False):
        base.GatewayContextTests.configure(c, s)
        s.RequestHandlerClass = base.ContextSink
        c['context']['signals'] = 'on'
        cheap = c['context']['candidates'][1]
        cheap.update(qualified_tasks=['tool_followup_ok'], capabilities=copy.deepcopy(FULL_CAPS if caps is None else caps))
        if compliance:
            c['compliance'] = {'enabled': True, 'public_allowed': True}

    @staticmethod
    def hermes_body(history, tools, extra=None):
        """Exact real Hermes top-level shape (no tool_choice, no parallel flag)."""
        body = {'model': 'auto', 'messages': history, 'max_tokens': 4096, 'stream': True,
                'stream_options': {'include_usage': True}, 'reasoning_effort': 'medium', 'tools': tools}
        body.update(extra or {})
        return body

    def loop(self, p, sink, tools, name, results, extra_first=None, extra_next=None, first_user='start'):
        """Turn 1 asks for a streamed tool; each clean result is sent as the next
        streamed turn. Returns models sent upstream per turn (None if rejected)."""
        scope = self.open_scope(p)
        history = [{'role': 'system', 'content': 'You are a coding agent.'}, {'role': 'user', 'content': first_user}]
        models = []
        for i in range(len(results) + 1):
            if i:
                history.append({'role': 'tool', 'tool_call_id': 'call-%d' % i, 'content': results[i - 1]})
            wire, assistant = tool_sse(name, 'call-%d' % (i + 1))
            sink.stream_wire = wire; sink.wire_step = 97
            extra = (extra_first if i == 0 else extra_next) or {}
            if callable(extra): extra = extra(i)
            before = len(sink.seen)
            code, raw, _ = self.request(p, headers=self.headers(scope, i + 1), body=self.hermes_body(history, tools, extra))
            if code != 200:
                self.assertEqual(len(sink.seen), before); models.append(None); break
            self.assertEqual(raw, wire)  # SSE bytes relayed verbatim
            sent = sink.seen[-1][2]
            # Nothing is stripped or rewritten except the model name (+ adapter egress control).
            expected = {**self.hermes_body(history, tools, extra), 'model': sent['model']}
            if 'provider' in sent: expected['provider'] = sent['provider']
            self.assertEqual(sent, expected)
            models.append(sent['model'])
            history.append(assistant)
        return scope, history, models

    @staticmethod
    def decisions(sink):
        return [l for l in sink.router_stderr.decode().splitlines() if l.startswith('route_decision ')]

    # (a) declared cheap candidate receives the clean streamed tool follow-up.
    def test_a_hermes_shape_switches_to_declared_candidate(self):
        tools = nested_tools()
        self.assertGreater(len(json.dumps(tools, separators=(',', ':'))), 16384)
        with self.router(self.setup) as (p, sink):
            _, _, models = self.loop(p, sink, tools, 'tool_3', ['wrote 3 files', 'ok'])
            self.assertEqual(models, ['frontier', 'physical', 'physical'])
        lines = self.decisions(sink)
        self.assertIn(' class=tool_followup_ok reason=cheapest', lines[1])
        self.assertNotIn('reason=pin', ''.join(lines))

    # (b) destination lacking any one declaration never receives it.
    def test_b_missing_declaration_stays_baseline(self):
        tools = nested_tools()
        cases = {'no_stream_tools': dict(FULL_CAPS, stream_tools=False),
                 'stream_tools_absent': {k: v for k, v in FULL_CAPS.items() if k != 'stream_tools'},
                 'no_medium_token': dict(FULL_CAPS, reasoning_effort=['low', 'high']),
                 'effort_absent': {k: v for k, v in FULL_CAPS.items() if k != 'reasoning_effort'},
                 'no_nested': dict(FULL_CAPS, nested_tool_schemas=False),
                 'legacy_caps_only': {'tool_history': True, 'function_tools': True, 'parallel_tools': True}}
        for name, caps in cases.items():
            with self.subTest(case=name), self.router(lambda c, s: self.setup(c, s, caps=caps)) as (p, sink):
                _, _, models = self.loop(p, sink, tools, 'tool_3', ['wrote 3 files', 'ok'])
                self.assertEqual(models, ['frontier', 'frontier', 'frontier'])
                self.assertFalse([x for x in sink.seen if x[2].get('model') == 'physical'])
            # Baseline stays usable as the (undeclared) owner: served, not pinned.
            self.assertIn(' class=tool_followup_ok reason=baseline', self.decisions(sink)[1])

    # (c) sticky contract: any change of the projection pins permanently.
    def test_c_changed_contract_mid_scope_pins_permanently(self):
        tools = nested_tools()
        changed = copy.deepcopy(tools); changed[0]['function']['description'] += '!'
        cases = {'tools': {'tools': changed}, 'effort': {'reasoning_effort': 'high'},
                 'usage_option': {'stream_options': {'include_usage': False}},
                 'tool_choice': {'tool_choice': 'auto'}, 'parallel': {'parallel_tool_calls': True}}
        for name, extra in cases.items():
            with self.subTest(case=name), self.router(self.setup) as (p, sink):
                # Turn 2 changes the projection; turn 3 restores the original.
                _, _, models = self.loop(p, sink, tools, 'tool_3', ['ok one', 'ok two'],
                                         extra_next=lambda i: extra if i == 1 else {})
                self.assertEqual(models, ['frontier', 'frontier', 'frontier'])
            self.assertIn('reason=pin', self.decisions(sink)[-1])

    # (d) unknown top-level keys and malformed values still pin (unchanged).
    def test_d_unknown_or_malformed_options_still_pin(self):
        tools = nested_tools()
        cases = {'unknown': {'future': None}, 'reasoning_object': {'reasoning': {'effort': 'high'}},
                 'effort_space': {'reasoning_effort': 'me dium'}, 'effort_long': {'reasoning_effort': 'x' * 65},
                 'effort_type': {'reasoning_effort': 1}, 'effort_empty': {'reasoning_effort': ''}}
        for name, extra in cases.items():
            with self.subTest(case=name), self.router(self.setup) as (p, sink):
                _, _, models = self.loop(p, sink, tools, 'tool_3', ['ok'], extra_first=extra, extra_next=extra)
                self.assertEqual(models, ['frontier', 'frontier'])
            self.assertIn('reason=pin', self.decisions(sink)[-1])

    def test_d_tool_bounds_are_enforced(self):
        deep = {'type': 'object', 'properties': {}}
        node = deep
        for _ in range(30):
            child = {'type': 'object', 'properties': {}}
            node['properties']['n'] = child; node = child
        cases = {'too_deep': [{'type': 'function', 'function': {'name': 'tool_3', 'description': 'd', 'parameters': deep}}],
                 'too_many': nested_tools(count=65, pad=10),
                 'too_large': nested_tools(count=40, pad=1700),
                 'duplicate': nested_tools(count=2, pad=1) + nested_tools(count=1, pad=1),
                 'bad_name': [{'type': 'function', 'function': {'name': 'a b', 'parameters': {'type': 'object'}}}],
                 'strict_flag': [{'type': 'function', 'function': {'name': 'tool_3', 'strict': True, 'parameters': {'type': 'object'}}}],
                 'params_array': [{'type': 'function', 'function': {'name': 'tool_3', 'parameters': []}}]}
        self.assertGreater(len(json.dumps(cases['too_large'], separators=(',', ':'))), 65536)
        for name, tools in cases.items():
            with self.subTest(case=name), self.router(self.setup) as (p, sink):
                _, _, models = self.loop(p, sink, tools, 'tool_0' if name != 'too_deep' else 'tool_3', ['ok'])
                self.assertEqual(models, ['frontier', 'frontier'])

    # (e) M2 is unchanged: PII goes private / never reaches a public model.
    def test_e_pii_is_private_and_never_public(self):
        tools = nested_tools()
        with self.router(lambda c, s: self.setup(c, s, compliance=True)) as (p, sink):
            _, _, models = self.loop(p, sink, tools, 'tool_3', ['ok'], first_user='mail alice@example.com')
            # Turn 1: final M2 places PII privately. Turn 2: existing M2
            # owner-conflict rule (automatic baseline vetoed, tool scope may
            # not be silently retargeted) rejects before egress. Unchanged.
            self.assertEqual(models, ['physical', None])
        with self.router(lambda c, s: self.setup(c, s, compliance=True)) as (p, sink):
            _, _, models = self.loop(p, sink, tools, 'tool_3', ['contact alice@example.com'])
            self.assertEqual(models[0], 'frontier')
            self.assertEqual(models[1], None)  # public owner conflict: rejected before egress
        self.assertFalse([x for x in sink.seen if 'alice@example.com' in json.dumps(x[2]) and x[2]['model'] == 'frontier'])

    # Regression: the ACTUAL sanitized Hermes profile (19 tools, ~36.6 KB).
    def test_actual_extracted_hermes_profile_switches_when_declared(self):
        fixture = json.loads(FIXTURE.read_text())
        tools = fixture['tools']
        self.assertEqual(len(tools), 19)
        self.assertGreater(len(json.dumps(tools, separators=(',', ':'))), 36000)
        self.assertEqual(fixture['request_options']['reasoning_effort'], 'medium')
        for caps, expect in ((FULL_CAPS, 'physical'), (dict(FULL_CAPS, stream_tools=False), 'frontier')):
            with self.subTest(declared=caps['stream_tools']), self.router(lambda c, s: self.setup(c, s, caps=caps)) as (p, sink):
                _, _, models = self.loop(p, sink, tools, 'terminal', ['/workspace\nTASK.md contents'])
                self.assertEqual(models, ['frontier', expect])

    def test_strict_capability_configuration(self):
        import test_router
        cfg0 = {'listen': {'host': '127.0.0.1', 'port': 12345},
                'private': {'url': 'http://127.0.0.1:1/v1', 'model': 'physical'},
                'auth': {'api_key_env': 'RC_TEST_AUTH'},
                'aliases': [{'from': 'alias', 'endpoint': 'private', 'model': 'physical'}]}
        class S: pass
        self.setup(cfg0, S())
        caps = lambda c: c['context']['candidates'][1]['capabilities']
        bad = [lambda c: caps(c).update(stream_tools='true'), lambda c: caps(c).update(stream_tools=1),
               lambda c: caps(c).update(nested_tool_schemas=None),
               lambda c: caps(c).update(reasoning_effort='medium'), lambda c: caps(c).update(reasoning_effort=[]),
               lambda c: caps(c).update(reasoning_effort=['low', 'low']), lambda c: caps(c).update(reasoning_effort=['a b']),
               lambda c: caps(c).update(reasoning_effort=['x' * 65]), lambda c: caps(c).update(reasoning_effort=[1]),
               lambda c: caps(c).update(reasoning_effort=['t%d' % i for i in range(9)]),
               lambda c: caps(c).update(future=True)]
        good = [lambda c: None, lambda c: caps(c).update(stream_tools=False, nested_tool_schemas=False),
                lambda c: caps(c).pop('reasoning_effort'), lambda c: caps(c).update(reasoning_effort=['x' * 64]),
                lambda c: caps(c).update(reasoning_effort=['t%d' % i for i in range(8)])]
        env = {**os.environ, 'RC_TEST_AUTH': 'local-test-key', 'RC_TEST_SOURCE': 'source-only-test-key'}
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'cfg.json'
            for expect, mutations in ((False, bad), (True, good)):
                for mutate in mutations:
                    cfg = copy.deepcopy(cfg0); mutate(cfg); path.write_text(json.dumps(cfg))
                    result = subprocess.run([str(test_router.BIN), 'validate', str(path), '--test-mode'], env=env, capture_output=True)
                    self.assertEqual(result.returncode == 0, expect, (cfg['context']['candidates'][1], result.stderr))
                    self.assertNotIn(b'AddressSanitizer', result.stderr)

    def test_example_configs_validate(self):
        import test_router
        root = pathlib.Path(__file__).resolve().parents[2] / 'config'
        env = {**os.environ, 'RC_FIXTURE_INFERENCE_KEY': 'fixture-inference', 'RC_FIXTURE_SOURCE_KEY': 'fixture-source'}
        cfg = json.loads((root / 'recursant.context.fixture.example.json').read_text())
        names = {c['alias']: c for c in cfg['context']['candidates']}
        for alias in ('gpt-4.1', 'gpt-4.1-mini'):
            self.assertEqual(names[alias]['capabilities']['reasoning_effort'], ['low', 'medium', 'high'])
            self.assertTrue(names[alias]['capabilities']['stream_tools'])
            self.assertTrue(names[alias]['capabilities']['nested_tool_schemas'])
        result = subprocess.run([str(test_router.BIN), 'validate', str(root / 'recursant.context.fixture.example.json'), '--test-mode'],
                                env=env, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
