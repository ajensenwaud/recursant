"""Offline stdlib tests; no provider calls."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest


class ObserverTest(unittest.TestCase):
    def test_observer_is_read_only_and_bounded(self):
        path = Path(__file__).parent / 'observer' / '__init__.py'
        self.assertTrue(path.exists(), 'observer not implemented')
        spec = importlib.util.spec_from_file_location('observer_test', path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as directory:
            os.environ['HERMES_OBSERVER_PATH'] = directory + '/events.jsonl'
            os.environ['HERMES_OBSERVER_MAX_BYTES'] = '2048'
            hooks = {}
            class Context:
                def register_hook(self, name, callback):
                    hooks[name] = callback
            mod.register(Context())
            self.assertNotIn('pre_llm_call', hooks)
            for _ in range(100):
                self.assertIsNone(hooks['on_stream_delta'](delta='synthetic', kind='reasoning'))
            records = [json.loads(line) for line in Path(os.environ['HERMES_OBSERVER_PATH']).read_text().splitlines()]
            self.assertGreater(len(records), 0)
            self.assertLessEqual(Path(os.environ['HERMES_OBSERVER_PATH']).stat().st_size, 2048)
            self.assertEqual(records[-1]['event'], 'observer_storage_limit')
            self.assertEqual(records[0]['payload']['delta'], 'synthetic')
            # pre_tool_call can veto a tool in Hermes; the observer records it for
            # lead-time analysis but must never return a decision.
            self.assertIsNone(hooks['pre_tool_call'](tool_name='terminal', args={'command': 'pwd'}))

if __name__ == '__main__':
    unittest.main()
