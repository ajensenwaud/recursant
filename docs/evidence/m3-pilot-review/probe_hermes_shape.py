"""Loopback-only probe: does a Hermes-shaped request ever switch models on aceb40d?"""
import json, unittest
import test_gateway_signals as sig
import test_gateway_context as base

def call(i):
    return {'id': 'call-%d' % i, 'type': 'function', 'function': {'name': 'f', 'arguments': '{}'}}

class Probe(sig.GatewaySignalTests if hasattr(sig, 'GatewaySignalTests') else object):
    pass

T = [c for c in vars(sig).values() if isinstance(c, type) and issubclass(c, unittest.TestCase)][0]

class HermesShape(T):
    def run_shape(self, label, **extra):
        with self.router(self.setup) as (p, sink):
            _, _, models = self.tool_loop(p, sink, ['wrote 3 files', 'tests passed'], **extra)
        print(f'{label:<46} models={models} decisions={[l.split(" class=")[1][:40] for l in self.decisions(sink)]}')
        return models

    def test_shapes(self):
        big = [{'type': 'function', 'function': {'name': 'f', 'description': 'x' * 4000,
                'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}}}] + \
              [{'type': 'function', 'function': {'name': f'g{i}', 'description': 'x' * 1800,
                'parameters': {'type': 'object', 'properties': {}}}} for i in range(18)]
        r = {}
        r['control'] = self.run_shape('control (nonstream, 1 tool)')
        r['stream'] = self.run_shape('stream=true', stream=True)
        r['reasoning'] = self.run_shape('reasoning_effort=medium', reasoning_effort='medium')
        r['bigtools'] = self.run_shape('19 tools / 36KB', tools=big)
        r['hermes'] = self.run_shape('Hermes: stream+include_usage+reasoning+19 tools', stream=True,
                                     stream_options={'include_usage': True}, reasoning_effort='medium', tools=big)
        print('RESULT', json.dumps(r))

if __name__ == '__main__':
    unittest.main(argv=['x', 'HermesShape.test_shapes'], verbosity=1)
