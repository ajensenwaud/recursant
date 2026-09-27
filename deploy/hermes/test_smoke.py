"""Offline smoke acceptance checks; no inference."""
import importlib.util
from pathlib import Path
import unittest

class AcceptanceTest(unittest.TestCase):
    def test_loopback_requires_container_network(self):
        path = Path(__file__).resolve().parents[2] / 'bench' / 'hermes_smoke.py'
        spec = importlib.util.spec_from_file_location('smoke', path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertTrue(hasattr(mod, 'endpoint_address'), 'network validation missing')
        with self.assertRaises(ValueError):
            mod.endpoint_address('http://127.0.0.1:8080/v1', None)
        self.assertEqual(mod.endpoint_address('http://127.0.0.1:8080/v1', 'container:router'), '127.0.0.1')
        with self.assertRaises(ValueError):
            mod.endpoint_address('http://8.8.8.8/v1', 'container:router')

    def test_acceptance_requires_exact_final_response(self):
        path = Path(__file__).resolve().parents[2] / 'bench' / 'hermes_smoke.py'
        spec = importlib.util.spec_from_file_location('smoke', path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertTrue(hasattr(mod, 'task_completed'), 'final-response acceptance missing')
        good = {'completed': True, 'final_response': 'ROUTING_OK'}
        self.assertTrue(mod.task_completed(good))
        for change in ({'completed': False}, {'final_response': 'wrong'},
                       {'final_response': None}, {'failed': True},
                       {'partial': True}, {'interrupted': True}):
            self.assertFalse(mod.task_completed({**good, **change}))

    def test_acceptance_requires_real_successful_tool(self):
        path = Path(__file__).resolve().parents[2] / 'bench' / 'hermes_smoke.py'
        self.assertTrue(path.exists(), 'smoke not implemented')
        spec = importlib.util.spec_from_file_location('smoke', path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        events = [{'event': 'post_tool_call', 'payload': {'tool_name': 'terminal', 'status': 'ok', 'result': {'output': 'ROUTING_OK', 'exit_code': 0}}}]
        self.assertTrue(mod.terminal_executed(events))
        self.assertFalse(mod.terminal_executed([]))
        events[0]['payload']['status'] = 'error'
        self.assertFalse(mod.terminal_executed(events))
        events[0]['payload']['status'] = 'ok'
        events[0]['payload']['result']['exit_code'] = 1
        self.assertFalse(mod.terminal_executed(events))

if __name__ == '__main__':
    unittest.main()
