"""No inference: deterministic graders and real loopback orchestration."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


class TaskTests(unittest.TestCase):
    def test_frozen_tasks_have_independent_negative_and_positive_cases(self):
        self.assertIsNotNone(importlib.util.find_spec('bench.evaluation.tasks'), 'task pack absent')
        from bench.evaluation.tasks import TASKS, grade, FIXTURE_SOLUTIONS, fingerprint
        self.assertEqual(len(TASKS), 3)
        self.assertEqual(len(fingerprint()), 64)
        for task in TASKS:
            with self.subTest(task=task['id']):
                self.assertNotIn('expected', task)
                self.assertFalse(grade(task['id'], lambda value: None)['success'])
                namespace = {}
                exec(FIXTURE_SOLUTIONS[task['id']], namespace)
                self.assertTrue(grade(task['id'], namespace['solve'])['success'])


class LiveProtocolTests(unittest.TestCase):
    def test_dedicated_route_session_uses_real_loopback_egress(self):
        from bench.evaluation import live
        self.assertTrue(hasattr(live,'RouteSession'), 'route lifecycle absent')
        from bench.evaluation.meter import Meter, serve
        with tempfile.TemporaryDirectory() as temp:
            upstream=Meter(mode='fixture',request_cap=8)
            with serve(upstream,task_id='dag-v1',arm='baseline') as url:
                config={'request_cap':8,'liability_usd_per_dispatch':0.1,'paid_cap_usd':1,
                        'baseline_endpoint':'private','baseline_model':'fixture',
                        'upstreams':{'private':{'url':url,'reasoning_semantics':'unknown','tokenizer':'fixture'}}}
                with live.RouteSession(config,Path(temp),'dag-v1','baseline',fixture=True) as route:
                    status,raw,mime=route.handle('/v1/chat/completions',
                        {'model':'fixture','max_tokens':256,'messages':[]},{})
                    self.assertEqual(status,200)
                    self.assertIn(b'tool_calls',raw)
                    status,raw,mime=route.handle('/v1/context/open',
                        {'task_id':'dag-v1','session_id':'s','branch':'main'},{})
                    self.assertEqual(status,201)
                    self.assertEqual(len(json.loads(raw)['generation']),32)
                self.assertEqual(len(route.calls),1)
                self.assertEqual(route.calls[0]['evidence_kind'],'fixture')

    def test_routed_episode_owns_gateway_and_counts_egress(self):
        import os
        binary=os.environ.get('M3_ROUTER_BINARY')
        if not binary: self.skipTest('set M3_ROUTER_BINARY for C gateway lifecycle test')
        from bench.evaluation.live import RouteSession
        from bench.evaluation.meter import Meter, serve
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            provider=Meter(mode='fixture',request_cap=8)
            with serve(provider,task_id='dag-v1',arm='text-aware') as url:
                upstream={'url':url,'reasoning_semantics':'unknown','tokenizer':'fixture'}
                config={'request_cap':8,'liability_usd_per_dispatch':0.1,'paid_cap_usd':1,
                    'baseline_endpoint':'private','baseline_model':'fixture','router_binary':binary,
                    'router_config':{'listen':{'host':'127.0.0.1','port':1},
                      'private':{'url':url,'model':'fixture'},'public':{'url':url,'model':'other-fixture'},
                      'auth':{'api_key_env':'M3_EPISODE_API'},
                      'aliases':[{'from':'baseline','endpoint':'private','model':'fixture'}],
                      'limits':{'max_body_bytes':1048576,'max_connections':16,'request_timeout_seconds':180},
                      'compliance':{'enabled':True,'public_allowed':False,'patterns':[]},
                      'context':{'mode':'active','tenant':'local','project':'eval',
                        'source_key_env':'M3_EPISODE_SOURCE','auto_alias':'auto','baseline_alias':'baseline','ttl_ms':2000,
                        'candidates':[{'alias':'baseline','quality_evidence':'synthetic',
                          'qualified_tasks':[],'context_limit':100000,'expected_task_cost':1.0}]}},
                    'upstreams':{'private':upstream,'public':upstream}}
                with RouteSession(config,Path(temp),'dag-v1','text-aware',fixture=True) as route:
                    status,raw,mime=route.handle('/v1/chat/completions',
                        {'model':'auto','max_tokens':256,'messages':[{'role':'user','content':'synthetic fixture'}]}, {})
                    self.assertEqual(status,200,raw)
                    self.assertIn(b'tool_calls',raw)
                    self.assertEqual(len(route.calls),1)
                    self.assertIsNotNone(getattr(route,'process',None),'dedicated gateway was not started')
                self.assertIsNotNone(route.process.poll())

    def test_private_dispatches_are_sequential_including_auxiliaries(self):
        from bench.evaluation.live import Egress
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading, time
        state={'active':0,'maximum':0}; lock=threading.Lock()
        class Provider(BaseHTTPRequestHandler):
            def log_message(self, format, *args): pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                with lock:
                    state['active']+=1; state['maximum']=max(state['maximum'],state['active'])
                time.sleep(0.15)
                with lock: state['active']-=1
                self.send_response(200); self.end_headers(); self.wfile.write(b'{}')
        server=ThreadingHTTPServer(('127.0.0.1',0),Provider)
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            with tempfile.TemporaryDirectory() as temp:
                cfg={'request_cap':2,'paid_cap_usd':1,'liability_usd_per_dispatch':0.1,
                     'upstreams':{'private':{'url':f'http://127.0.0.1:{server.server_port}',
                        'reasoning_semantics':'unknown','tokenizer':'fixture'}}}
                meter=Egress(cfg,Path(temp),'t','text-aware',fixture=True)
                workers=[threading.Thread(target=meter.forward,args=('private',{'max_tokens':1},{})) for _ in range(2)]
                for w in workers: w.start()
                for w in workers: w.join()
                self.assertEqual(len(meter.calls),2)
                self.assertEqual(state['maximum'],1)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_live_bounds_whitelist_context_and_nonreusable_allocation(self):
        from bench.evaluation import live
        self.assertTrue(hasattr(live,'admission'),'per-model admission absent')
        config={'context_limit':65536,'upstreams':{'private':{'model':'private-model'}}}
        body={'model':'openai/gpt-4.1-mini','max_tokens':4096,'reasoning_effort':'medium',
              'messages':[{'role':'user','content':'synthetic test'}]}
        liability,input_bound=live.admission(config,'public',body)
        from decimal import Decimal
        self.assertEqual(liability,Decimal(input_bound)*Decimal('0.0000004')+Decimal(4096)*Decimal('0.0000016'))
        for change in ({'model':'unknown'},{'tools':[{'type':'web_search'}]},
                       {'max_completion_tokens':8192},
                       {'plugins':[{'id':'web'}]},{'messages':[{'role':'user','content':'x'*65536}]}):
            with self.assertRaises(ValueError): live.admission(config,'public',dict(body,**change))
        with tempfile.TemporaryDirectory() as temp:
            cfg={'allocation_path':str(Path(temp)/'allocation.jsonl'),'allocation_reference':'parent-only',
                 'request_cap':72,'paid_cap_usd':2,'approval_reference':'approved'}
            live.create_allocation(cfg)
            with self.assertRaises(FileExistsError): live.create_allocation(cfg)

    def test_live_preflight_rejects_unapproved_and_missing_pricing(self):
        self.assertIsNotNone(importlib.util.find_spec('bench.evaluation.live'), 'live admission absent')
        from bench.evaluation.live import validate_live
        for config in ({}, {'approved':True}, {'approved':True,'paid_cap_usd':1}):
            with self.assertRaises(ValueError): validate_live(config)

    def test_egress_loopback_captures_usage_and_reserves_failed_attempts(self):
        self.assertIsNotNone(importlib.util.find_spec('bench.evaluation.live'), 'live meter absent')
        from bench.evaluation.live import Egress
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading, urllib.request, urllib.error
        class Provider(BaseHTTPRequestHandler):
            def log_message(self, format, *args): pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200); self.end_headers()
                self.wfile.write(b'data: {"model":"test","choices":[],"usage":{"prompt_tokens":11,"completion_tokens":5,"completion_tokens_details":{"reasoning_tokens":3},"cost":0.02}}\n\ndata: [DONE]\n\n')
        upstream=ThreadingHTTPServer(('127.0.0.1',0),Provider)
        thread=threading.Thread(target=upstream.serve_forever,daemon=True); thread.start()
        try:
            with tempfile.TemporaryDirectory() as temp:
                meter=Egress({'request_cap':1,'liability_usd_per_dispatch':0.1,'paid_cap_usd':0.1,
                              'upstreams':{'private':{'url':f'http://127.0.0.1:{upstream.server_port}/v1',
                              'reasoning_semantics':'inclusive','tokenizer':'test'}}},
                             Path(temp), 't', 'text-aware', fixture=True)
                status,raw,mime=meter.forward('private',{'max_tokens':32}, {})
                self.assertEqual(status,200)
                self.assertIn(b'[DONE]',raw)
                self.assertEqual(meter.calls[0]['input_tokens'],11)
                self.assertEqual(meter.calls[0]['reasoning_tokens'],3)
                self.assertEqual(meter.calls[0]['cost_usd'],0.02)
                self.assertEqual(meter.calls[0]['evidence_kind'],'fixture')
                self.assertEqual(meter.calls[0]['provider_model'],'test')
                self.assertEqual(meter.calls[0]['endpoint'],'private')
                self.assertEqual(meter.forward('private',{'max_tokens':32},{})[0],429)
                self.assertEqual(len(meter.calls),1)
                self.assertTrue((Path(temp)/'attempts.private.jsonl').exists())
        finally:
            upstream.shutdown(); upstream.server_close(); thread.join()


class PlanTests(unittest.TestCase):
    def test_interrupted_attempt_journal_is_recovered_before_reporting(self):
        from bench.evaluation import run
        self.assertTrue(hasattr(run,'recover_outcomes'),'crash reconciliation absent')
        assignment={'episode_id':'ep','task_id':'t','arm':'baseline','pair_id':'p'}
        with tempfile.TemporaryDirectory() as temp:
            episode=Path(temp)/'ep'; episode.mkdir()
            call=dict(dispatch_id='dispatched',task_id='t',arm='baseline',attempt=1,role='main',
                      input_tokens=None,output_tokens=None,reasoning_semantics='unknown')
            (episode/'attempts.private.jsonl').write_text(json.dumps(call)+'\n')
            rows=run.recover_outcomes(Path(temp),[assignment],[])
            self.assertEqual(rows[0]['calls'],[call])
            self.assertFalse(rows[0]['success'])
            self.assertFalse(rows[0]['collection_complete'])

    def test_plan_freezes_all_assignments_and_rejects_live_before_execution(self):
        from bench.evaluation import run
        self.assertTrue(hasattr(run,'plan'),'assignment planner absent')
        first=run.plan(2,7321)
        self.assertEqual(first,run.plan(2,7321))
        self.assertEqual(len(first),18)
        self.assertEqual(len({a['episode_id'] for a in first}),18)
        self.assertEqual({a['arm'] for a in first},set(run.ARMS))
        with tempfile.TemporaryDirectory() as temp:
            config=Path(temp)/'no-approval.json'; config.write_text('{}')
            with self.assertRaises((ValueError,SystemExit)):
                run.main(['--mode','live','--config',str(config),'--out',str(Path(temp)/'out')])
            self.assertFalse((Path(temp)/'out').exists())


class ReportTests(unittest.TestCase):
    def test_missing_episode_failed_expenditure_and_unknown_cost_remain(self):
        self.assertIsNotNone(importlib.util.find_spec('bench.evaluation.report'), 'report absent')
        from bench.evaluation.report import summarize
        assignments=[{'episode_id':str(i),'task_id':'t'+str(i//3),'arm':arm}
                     for i,arm in enumerate(('baseline','structured-only','text-aware')*2)]
        calls=[dict(dispatch_id='main',task_id='t0',arm='baseline',attempt=1,role='main',
                    input_tokens=10,output_tokens=2,reasoning_semantics='inclusive',
                    evidence_kind='actual',cost_usd=None),
               dict(dispatch_id='retry',task_id='t0',arm='baseline',attempt=2,role='interpreter',
                    input_tokens=4,output_tokens=1,reasoning_semantics='inclusive',
                    evidence_kind='actual',cost_usd=None)]
        rows=[dict(episode_id='0',success=False,calls=calls,collection_complete=True,
                   dispatch_ids=['main','retry'],evidence_kind='actual')]
        report=summarize(assignments,rows)
        self.assertEqual(report['assigned'],6)
        self.assertEqual(report['missing_outcomes'],5)
        # Legacy arm names map to canonical report arms (runner v2).
        self.assertEqual(report['arms']['baseline-direct']['known_tokens'],17)
        self.assertIsNone(report['arms']['baseline-direct']['total_tokens'])
        self.assertIsNone(report['arms']['baseline-direct']['cost_usd'])
        self.assertEqual(report['arms']['baseline-direct']['successes'],0)
        self.assertFalse(report['release_gate'])


class DockerTests(unittest.TestCase):
    def test_pinned_hermes_uses_metered_baseline_protocol(self):
        import os
        if os.environ.get('M3_DOCKER_TEST')!='1': self.skipTest('pinned-image integration opt-in')
        from bench.evaluation.run import run_episode, SETTINGS
        from bench.evaluation.tasks import TASKS
        from bench.evaluation.meter import Meter, serve
        with tempfile.TemporaryDirectory() as temp:
            provider=Meter(mode='fixture',request_cap=8)
            with serve(provider,task_id='dag-v1',arm='baseline') as url:
                config={'request_cap':8,'liability_usd_per_dispatch':0.1,'paid_cap_usd':1,
                        'baseline_endpoint':'private','baseline_model':'fixture',
                        'upstreams':{'private':{'url':url,'reasoning_semantics':'unknown','tokenizer':'fixture'}}}
                row=run_episode(TASKS[2],'baseline',Path(temp)/'episode',SETTINGS,
                                live_config=config,protocol_fixture=True)
                self.assertTrue(row['success'],row)
                self.assertEqual(row['physical_attempts'],4)
                self.assertEqual(row['evidence_kind'],'fixture')
                self.assertEqual(row['harness_settings']['context'],65536)
                self.assertTrue(row['collection_complete'])

    def test_pinned_hermes_completes_artifact_with_host_only_grader(self):
        import os
        if os.environ.get('M3_DOCKER_TEST') != '1':
            self.skipTest('set M3_DOCKER_TEST=1 for pinned-image integration')
        self.assertIsNotNone(importlib.util.find_spec('bench.evaluation.run'), 'runner absent')
        from bench.evaluation.run import run_episode, SETTINGS
        from bench.evaluation.tasks import TASKS
        with tempfile.TemporaryDirectory() as temp:
            result = run_episode(TASKS[2], 'baseline', Path(temp)/'episode', SETTINGS)
            self.assertTrue(result['success'], result)
            self.assertEqual(result['verifier']['passed'], 5)
            self.assertEqual(result['physical_attempts'], 4)
            self.assertTrue(result['source']['pristine'])
            self.assertGreater(result['hook_counts']['post_tool_call'], 0)
            self.assertEqual(result['evidence_kind'], 'fixture')
            self.assertGreater(result['context_event_count'],0)
            self.assertEqual(result['scope']['task_id'],'dag-v1')


class ProtocolTests(unittest.TestCase):
    def test_real_loopback_tool_stream_and_attempt_cap(self):
        self.assertIsNotNone(importlib.util.find_spec('bench.evaluation.meter'), 'meter absent')
        from bench.evaluation.meter import Meter, serve
        import urllib.request
        meter = Meter(mode='fixture', request_cap=2)
        with serve(meter, task_id='dag-v1', arm='baseline') as endpoint:
            req = lambda: urllib.request.Request(endpoint+'/chat/completions',
                data=json.dumps({'model':'fixture', 'messages':[], 'stream':True}).encode(),
                headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req()) as response:
                body=response.read().decode()
                self.assertIn('tool_calls', body)
                self.assertIn('[DONE]', body)
            with urllib.request.urlopen(req()) as response:
                self.assertEqual(response.status, 200)
            import urllib.error
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(req())
            self.assertEqual(caught.exception.code, 429)
            caught.exception.close()
        self.assertEqual(len(meter.calls), 2)
        self.assertEqual(len({c['dispatch_id'] for c in meter.calls}), 2)
        self.assertTrue(all(c['evidence_kind']=='fixture' for c in meter.calls))
        self.assertTrue(all(c['input_tokens'] is None for c in meter.calls))
        self.assertTrue(all(c['cost_usd'] is None for c in meter.calls))


if __name__ == '__main__':
    unittest.main()
