"""No dependencies, network, or Hermes installation needed for contract tests."""
import importlib
import unittest


class Context:
    def __init__(self):
        self.middleware = {}
        self.hooks = {}
    def register_middleware(self, name, fn):
        self.middleware[name] = fn
    def register_hook(self, name, fn):
        self.hooks[name] = fn


class AdapterTests(unittest.TestCase):
    def adapter(self, **kwargs):
        try:
            module = importlib.import_module('deploy.hermes.context_adapter')
        except ModuleNotFoundError:
            self.fail('context adapter not implemented')
        return module.install(**kwargs)

    def identity(self, **overrides):
        return dict(task_id='task', session_id='session', turn_id='turn',
                    api_request_id='opaque:not:parsed', api_call_count=1,
                    base_url='http://local/v1', finish_reason='stop', **overrides)

    def test_request_exact_endpoint_only_headers_unique_invocations(self):
        import copy
        ctx = Context()
        self.adapter(ctx=ctx, enabled=True, endpoint='http://local/v1')
        self.assertIn('llm_request', ctx.middleware)
        fn = ctx.middleware['llm_request']
        request = dict(model='fixed', messages=[{'role': 'user', 'content': 'unchanged'}],
                       tools=[{'name': 'terminal'}], max_tokens=23, extra_headers={'Keep': 'yes'})
        before = copy.deepcopy(request)
        result = fn(request=request, **self.identity())['request']
        self.assertEqual(request, before)
        self.assertEqual({k: v for k, v in result.items() if k != 'extra_headers'},
                         {k: v for k, v in before.items() if k != 'extra_headers'})
        headers = result['extra_headers']
        self.assertEqual(headers['Keep'], 'yes')
        for field in ('task_id', 'session_id', 'turn_id', 'api_request_id'):
            self.assertEqual(headers['X-Recursant-' + field.replace('_', '-')], self.identity()[field])
        second = fn(request=request, **self.identity())['request']['extra_headers']
        self.assertNotEqual(headers['X-Recursant-attempt'], second['X-Recursant-attempt'])
        for url in ('http://local/v1/', 'http://local/v10', 'http://other/v1'):
            ids = self.identity(); ids['base_url'] = url
            self.assertIsNone(fn(request=request, **ids))
        for bad in ('', 'a\r\nb', 'x' * 129, 'nonascii-\u2603'):
            ids = self.identity(); ids['session_id'] = bad
            self.assertIsNone(fn(request=request, **ids))

    def test_completed_response_opt_in_text_and_retry_ambiguity(self):
        from types import SimpleNamespace
        for content_enabled in (False, True):
            ctx = Context(); events = []
            adapter = self.adapter(ctx=ctx, enabled=True, endpoint='http://local/v1')
            adapter.emit = events.append
            adapter.content_enabled = content_enabled
            self.assertIn('post_api_request', ctx.hooks)
            ids = self.identity()
            headers = ctx.middleware['llm_request'](request={}, **ids)['request']['extra_headers']
            message = SimpleNamespace(content='plan', reasoning_content='reason',
                                      reasoning_details=[{'type': 'reasoning.encrypted', 'data': 'NEVER'}])
            ctx.hooks['post_api_request'](**ids, assistant_message=message, secret='NEVER')
            event = events[-1]
            self.assertEqual(event['attempt'], headers['X-Recursant-attempt'])
            self.assertEqual(event.get('association_scope'), 'middleware_invocation')
            self.assertIs(event.get('physical_routing_eligible'), False)
            self.assertTrue(event['routing_eligible'])
            self.assertEqual(event.get('text'), {'assistant_plan': 'plan', 'reasoning': 'reason'} if content_enabled else None)
            self.assertNotIn('NEVER', str(events))
            ctx.middleware['llm_request'](request={}, **ids)
            ctx.hooks['post_api_request'](**ids, assistant_message=message)
            self.assertEqual(events[-1]['association'], 'ambiguous')
            self.assertFalse(events[-1]['routing_eligible'])
            self.assertNotIn('text', events[-1])
            missing = dict(ids, api_request_id='unseen')
            ctx.hooks['post_api_request'](**missing, assistant_message=message)
            self.assertEqual(events[-1]['association'], 'missing')
            self.assertNotIn('text', events[-1])
            self.assertNotIn('on_llm_stream_delta', ctx.hooks)
            self.assertNotIn('pre_auxiliary_call', ctx.hooks)

    def test_tool_requires_completed_matching_response_not_arrival_order(self):
        from types import SimpleNamespace as NS
        ctx = Context(); events = []
        adapter = self.adapter(ctx=ctx, enabled=True, endpoint='http://local/v1')
        adapter.emit = events.append
        adapter.content_enabled = True
        self.assertIn('post_tool_call', ctx.hooks)
        req = ctx.middleware['llm_request']; post = ctx.hooks['post_api_request']; tool = ctx.hooks['post_tool_call']
        ids = self.identity(); other = dict(ids, session_id='parallel')
        for branch in (ids, other):
            req(request={}, **branch)
        tool(**ids, tool_call_id='call', status='success', result='early')
        self.assertFalse(events[-1]['routing_eligible'])
        post(**other, assistant_message=NS(content='', tool_calls=[NS(id='call')]))
        tool(**ids, tool_call_id='call', status='success', result='wrong branch')
        self.assertFalse(events[-1]['routing_eligible'])
        post(**ids, assistant_message=NS(content='', tool_calls=[NS(id='call')]))
        tool(**ids, tool_call_id='call', status='success', result='exit 0', args={'secret': 'NEVER'})
        self.assertTrue(events[-1]['routing_eligible'])
        self.assertEqual(events[-1]['text'], {'tool_result': 'exit 0'})
        self.assertEqual(events[-1]['status'], 'success')
        tool(**ids, tool_call_id='call', status='ok', result='exit 0')
        self.assertEqual(events[-1]['status'], 'ok')
        self.assertEqual(events[-1].get('association_scope'), 'middleware_invocation')
        self.assertIs(events[-1].get('physical_routing_eligible'), False)
        self.assertNotIn('NEVER', str(events))
        req(request={}, **ids)
        tool(**ids, tool_call_id='call', status='success', result='ambiguous')
        self.assertFalse(events[-1]['routing_eligible'])
        self.assertNotIn('text', events[-1])

    def test_bounded_datagrams_loss_and_state_capacity(self):
        import json
        import socket
        import tempfile
        from types import SimpleNamespace as NS
        with tempfile.TemporaryDirectory() as tmp:
            path = tmp + '/sink'
            receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            self.addCleanup(receiver.close)
            receiver.bind(path); receiver.settimeout(1)
            ctx = Context()
            adapter = self.adapter(ctx=ctx, enabled=True, endpoint='http://local/v1')
            self.assertTrue(hasattr(adapter, 'configure_sink'), 'nonblocking datagram sink missing')
            adapter.configure_sink(path)
            self.addCleanup(adapter.close)
            adapter.content_enabled = True
            req = ctx.middleware['llm_request']; post = ctx.hooks['post_api_request']
            ids = self.identity()
            req(request={}, **ids)
            post(**ids, assistant_message=NS(content='x' * 10000))
            event = json.loads(receiver.recv(32768))
            self.assertLessEqual(len(event['text']['assistant_plan']), 2048)
            self.assertEqual(event['sequence'], 1)
            self.assertEqual(event['upstream_gaps'], 'unknown')
            receiver.close()
            post(**ids, assistant_message=NS(content='lost'))
            self.assertEqual(adapter.dropped, 1)
            self.assertFalse(adapter.socket.getblocking())
            for i in range(300):
                req(request={}, **dict(ids, api_request_id=str(i)))
            self.assertLessEqual(len(adapter.attempts), 256)
            events = []; adapter.emit = events.append
            post(**dict(ids, api_request_id='299'), assistant_message=NS(content='not attributable'))
            self.assertFalse(events[-1]['routing_eligible'])
            self.assertNotIn('text', events[-1])

    def test_error_and_header_collision_cannot_claim_exact(self):
        from types import SimpleNamespace as NS
        ctx = Context(); events = []
        adapter = self.adapter(ctx=ctx, enabled=True, endpoint='http://local/v1')
        adapter.emit = events.append; adapter.content_enabled = True
        self.assertIn('api_request_error', ctx.hooks)
        ids = self.identity(); req = ctx.middleware['llm_request']
        result = req(request={}, **ids)
        self.assertEqual(result['request']['extra_headers']['X-Recursant-api-call-count'], '1')
        ctx.hooks['api_request_error'](**ids, retry_count=0)
        ctx.hooks['post_api_request'](**ids, assistant_message=NS(content='not exact'))
        self.assertFalse(events[-1]['routing_eligible'])
        self.assertNotIn('text', events[-1])
        self.assertIsNone(req(request={'extra_headers': {'x-recursant-attempt': 'spoof'}}, **ids))
        for count in (-1, True, '1', 10**12):
            self.assertIsNone(req(request={}, **dict(ids, api_call_count=count)))

    def test_incomplete_or_duplicate_response_is_not_eligible(self):
        from types import SimpleNamespace as NS
        for reason in ('length', 'incomplete', None, 'content_filter'):
            ctx = Context(); events = []
            adapter = self.adapter(ctx=ctx, enabled=True, endpoint='http://local/v1')
            adapter.emit = events.append; adapter.content_enabled = True
            ids = dict(self.identity(), finish_reason=reason)
            ctx.middleware['llm_request'](request={}, **ids)
            ctx.hooks['post_api_request'](**ids, assistant_message=NS(content='partial'))
            self.assertFalse(events[-1]['routing_eligible'])
            self.assertNotIn('text', events[-1])
        ids = self.identity()
        ctx.middleware['llm_request'](request={}, **dict(ids, api_request_id='duplicate'))
        ids['api_request_id'] = 'duplicate'
        ctx.hooks['post_api_request'](**ids, assistant_message=NS(content='first'))
        self.assertTrue(events[-1]['routing_eligible'])
        ctx.hooks['post_api_request'](**ids, assistant_message=NS(content='replay'))
        self.assertFalse(events[-1]['routing_eligible'])
        self.assertNotIn('text', events[-1])

    def test_disabled_registers_nothing(self):
        ctx = Context()
        self.assertIsNone(self.adapter(ctx=ctx, enabled=False, endpoint='http://local/v1'))
        self.assertEqual(ctx.middleware, {})
        self.assertEqual(ctx.hooks, {})


if __name__ == '__main__':
    unittest.main()
