import unittest,time,json
from pathlib import Path
from probe import Probe

class OOM(unittest.TestCase):
    router=Probe.router
    request=Probe.request
    configure=staticmethod(Probe.configure)
    open_scope=Probe.open_scope
    headers=staticmethod(Probe.headers)
    event=Probe.event
    ingest=Probe.ingest
    tools=staticmethod(Probe.tools)
    setup=Probe.setup
    start=Probe.start
    advice=Probe.advice
    continuation=Probe.continuation
    def test_snapshot_and_replay_failures_pin(self):
        marker=Path('/tmp/rc-tool-oom-target')
        for target in 'htcor':
            with self.subTest(target=target),self.router(self.setup) as (p,s):
                if target!='r':marker.write_text(target)
                scope,h=self.start(p,s,{'tool_choice':{'type':'function','function':{'name':'f'}}})
                self.advice(p,scope)
                h.append(dict(role='tool',tool_call_id='call-1',content='result'))
                if target=='r':marker.write_text(target)
                s.tool_response=False
                code,raw,_=self.continuation(p,scope,h)
                self.assertEqual(code,200);self.assertFalse(marker.exists(),'fault not exercised')
                self.assertEqual(s.seen[-1][2]['model'],'frontier')
                h += [json.loads(raw)['choices'][0]['message'],dict(role='user',content='again')]
                self.assertEqual(self.ingest(p,self.event(scope,2,2)),202);time.sleep(.25)
                self.assertEqual(self.request(p,headers=self.headers(scope,3),body=dict(model='auto',messages=h,max_tokens=128))[0],200)
                self.assertEqual(s.seen[-1][2]['model'],'frontier')
                print('injected and consumed OOM target',target,flush=True)

if __name__=='__main__':unittest.main(defaultTest='OOM',verbosity=2)
