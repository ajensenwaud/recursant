"""Prompt classifier (context.prompt) through the actual C gateway: single-query and chat
traffic, and optionally an agent's opening instruction. Scripted loopback providers only.
Weights are fixtures (vocabulary 'capital' +6 -> p 0.998, 'prove' -6 -> p 0.002): this
proves the decision wiring, not the model (bench/prompt/parity.py proves the C features
equal the trained ones).

Proves: a fresh user question the classifier calls simple goes to a candidate qualified
for simple_prompt, with and without harness headers; a hard one stays on the baseline;
tool-offering requests are only scored with agent_turns; tool results are never scored
(signals decide); unqualified candidates are never used; final M2 wins; multi-turn chat is
scored per question; the log line carries no content; config is strict."""
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
import test_gateway_context as base
import test_gateway_signals as sig
import test_gateway_sessions as sess

SECTION = {'weights': {'bias': 0.0}, 'vocab': {'capital': 6.0, 'prove': -6.0}, 'simple_min': 0.8}


class GatewayPromptTests(unittest.TestCase):
    router = base.GatewayContextTests.router
    request = base.GatewayContextTests.request
    headers = staticmethod(sig.GatewaySignalsTests.headers)
    open_scope = sig.GatewaySignalsTests.open_scope
    tool_loop = sig.GatewaySignalsTests.tool_loop
    step = sig.GatewaySignalsTests.step
    body = sig.GatewaySignalsTests.body
    tools = staticmethod(sig.GatewaySignalsTests.tools)
    decisions = staticmethod(sig.GatewaySignalsTests.decisions)

    @staticmethod
    def psetup(c, s, prompt=True, tasks=('tool_followup_ok', 'simple_prompt'), sessions='request', **section):
        sess.GatewaySessionTests.setup(c, s, sessions=sessions, cheap_tasks=tasks)
        if prompt: c['context']['prompt'] = {**json.loads(json.dumps(SECTION)), **section}

    @staticmethod
    def lines(sink):
        return [l for l in sink.router_stderr.decode().splitlines() if l.startswith('prompt ')]

    def ask(self, p, sink, history, headers=None, **extra):
        """A chat request (no tools unless given); returns the model sent upstream."""
        sink.envelope = {}; sink.tool_response = False   # a plain text answer
        body = {'model': 'auto', 'messages': history, 'max_tokens': 128, **extra}
        code, raw, _ = self.request(p, headers=headers, body=body)
        self.assertEqual(code, 200, raw)
        history.append(json.loads(raw)['choices'][0]['message'])
        return sink.seen[-1][2]['model']

    def test_p1_a_simple_single_query_goes_to_the_economy_candidate(self):
        with self.router(self.psetup) as (p, sink):
            model = self.ask(p, sink, [{'role': 'system', 'content': 'be brief'},
                                       {'role': 'user', 'content': 'What is the capital of France?'}])
        self.assertEqual(model, 'physical')
        self.assertIn(' p=0.998 action=add', self.lines(sink)[0])
        self.assertIn(' class=simple_prompt reason=cheapest', self.decisions(sink)[0])
        self.assertNotIn(b'France', sink.router_stderr)

    def test_p2_a_hard_question_stays_on_the_baseline(self):
        with self.router(self.psetup) as (p, sink):
            model = self.ask(p, sink, [{'role': 'user', 'content': 'Prove the Riemann hypothesis.'}])
        self.assertEqual(model, 'frontier')
        self.assertIn(' p=0.002 action=keep', self.lines(sink)[0])
        self.assertIn(' class=none reason=baseline', self.decisions(sink)[0])

    def test_p3_off_without_the_section_and_never_to_an_unqualified_candidate(self):
        for kw in ({'prompt': False}, {'tasks': ('tool_followup_ok',)}):
            with self.subTest(**{k: str(v) for k, v in kw.items()}):
                with self.router(lambda c, s, kw=kw: self.psetup(c, s, **kw)) as (p, sink):
                    model = self.ask(p, sink, [{'role': 'user', 'content': 'capital of France?'}])
                self.assertEqual(model, 'frontier')
                if 'prompt' in kw: self.assertEqual(self.lines(sink), [])

    def test_p4_harness_headers_work_too(self):
        with self.router(lambda c, s: self.psetup(c, s, sessions=None)) as (p, sink):
            scope = self.open_scope(p)
            model = self.ask(p, sink, [{'role': 'user', 'content': 'capital of Peru?'}], headers=self.headers(scope, 1))
        self.assertEqual(model, 'physical')

    def test_p5_agent_instructions_only_with_agent_turns(self):
        for agent_turns, expect, action in ((False, 'frontier', 'p=-1.000 action=none'), (True, 'physical', 'action=add')):
            with self.subTest(agent_turns=agent_turns):
                with self.router(lambda c, s, a=agent_turns: self.psetup(c, s, agent_turns=a)) as (p, sink):
                    model = self.ask(p, sink, [{'role': 'user', 'content': 'find the capital in the config'}],
                                     tools=self.tools(), tool_choice='auto')
                self.assertEqual(model, expect)
                self.assertIn(action, self.lines(sink)[0])

    def test_p6_tool_results_are_never_scored_signals_decide(self):
        with self.router(lambda c, s: self.psetup(c, s, sessions=None, agent_turns=True, vocab={'start': -6.0, 'capital': 6.0})) as (p, sink):
            _, _, models = self.tool_loop(p, sink, ['capital capital', 'Traceback (most recent call last): boom'])
        # Turn 1 'start' is hard; turn 2 is a clean tool result (signals downshift);
        # turn 3 is one failure (no class): the classifier never reads the tool text.
        self.assertEqual(models, ['frontier', 'physical', 'frontier'])
        lines = self.lines(sink)
        self.assertIn('action=keep', lines[0])
        self.assertTrue(all('p=-1.000 action=none' in l for l in lines[2:]), lines)
        self.assertIn(' class=tool_followup_ok ', self.decisions(sink)[1])

    def test_p7_final_m2_wins(self):
        def setup(c, s):
            self.psetup(c, s, tasks=('tool_followup_ok',)); c['compliance'] = {'enabled': True, 'public_allowed': True}
        with self.router(setup) as (p, sink):
            model = self.ask(p, sink, [{'role': 'user', 'content': 'capital of France? mail alice@example.com'}])
        self.assertEqual(model, 'physical')
        self.assertFalse([x for x in sink.seen if 'alice@example.com' in json.dumps(x[2]) and x[2]['model'] != 'physical'])

    def test_p8_multi_turn_chat_is_scored_per_question(self):
        with self.router(self.psetup) as (p, sink):
            history = [{'role': 'user', 'content': 'prove that sqrt 2 is irrational'}]
            first = self.ask(p, sink, history)
            history.append({'role': 'user', 'content': 'and the capital of Chile?'})
            second = self.ask(p, sink, history)
        self.assertEqual((first, second), ('frontier', 'physical'))
        self.assertEqual(len(self.lines(sink)), 2)

    def test_p9_config_is_strict_and_requires_signals(self):
        bad = [lambda c: c['context']['prompt'].update(simple_min=0.3),
               lambda c: c['context']['prompt'].update(extra=1),
               lambda c: c['context']['prompt'].update(agent_turns='yes'),
               lambda c: c['context']['prompt']['weights'].update(mystery=1.0),
               lambda c: c['context']['prompt'].update(weights={'question': 1.0}),
               lambda c: c['context']['prompt']['vocab'].update(Capital=1.0),
               lambda c: c['context']['prompt']['vocab'].update(x=1000.0),
               lambda c: c['context']['prompt'].pop('vocab'),
               lambda c: c['context'].update(signals='off')]
        for i, change in enumerate(bad):
            with self.subTest(i=i):
                def setup(c, s, change=change):
                    self.psetup(c, s); change(c)
                with self.assertRaises(Exception):
                    with self.router(setup) as (p, sink): pass


if __name__ == '__main__':
    unittest.main()
