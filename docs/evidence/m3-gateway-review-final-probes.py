"""Independent fix-bounded HTTP assertions; synthetic loopback only."""
import json, time, threading, unittest, sys
sys.path.insert(0, '/src/tests/integration')
from test_gateway_context import GatewayContextTests, ContextSink
T = GatewayContextTests()
results = []

def config(c, s, mode='active'):
    T.configure(c, s, mode)
    s.RequestHandlerClass = ContextSink
    c['context']['ttl_ms'] = 100
    c['compliance'] = {'enabled': True, 'public_allowed': True}
    c['aliases'].append({'from': 'other', 'endpoint': 'private', 'model': 'other-physical'})

def call(p, scope, n, model, hist):
    return T.request(p, headers=T.headers(scope, n), body={'model': model, 'messages': hist, 'max_tokens': 128})

def models(s):
    return [x[2]['model'] for x in s.seen if 'response_format' not in x[2]]

def ok(status, expected, label):
    assert status == expected, (label, status, expected)

# Repeat across selection modes and after TTL expiry. No guessed scope joins.
for mode in ('active', 'shadow'):
    for repeat in range(3):
        with T.router(lambda c,s: config(c,s,mode)) as (p,s):
            scope=T.open_scope(p); h=[{'role':'user','content':'start'}]
            s.tool_response=True
            ok(call(p,scope,1,'other',h)[0],200,'initial explicit private owner')
            assert models(s)==['other-physical']
            s.tool_response=False; time.sleep(.15)
            before=len(models(s)); outcomes=[]
            for model in ('auto','baseline','alias','other'):
                for missing in (('generation',),('branch',),('generation','branch')):
                    hs=T.headers(scope,2)
                    for field in missing: hs.pop('X-Recursant-'+field)
                    status=T.request(p,headers=hs,body={'model':model,'messages':h,'max_tokens':128})[0]
                    ok(status,403,'lost tags'); outcomes.append(status)
                for key,value in (('task_id','unknown'),('session_id','unknown'),('branch','unknown'),('generation','0'*32)):
                    bad={**scope,key:value}
                    ok(call(p,bad,3,model,h)[0],403,'mismatched identity')
                for identity in ({'task_id':'t','session_id':'unknown'}, {'task_id':'unknown','session_id':'s'}, {'task_id':'t'}, {'session_id':'s'}):
                    ok(call(p,identity,4,model,h)[0],403,'partial registered identity loss')
            assert len(models(s))==before
            ok(call(p,scope,5,'baseline',h)[0],403,'explicit pin conflict')
            ok(call(p,scope,6,'auto',h)[0],200,'automatic retains original owner')
            ok(call(p,scope,7,'other',h)[0],200,'explicit retains original owner')
            assert models(s)==['other-physical']*3
            for identity in ({}, {'task_id':'unrelated','session_id':'unrelated'}):
                for model,expected in (('auto','frontier'),('baseline','frontier'),('alias','physical'),('other','other-physical')):
                    ok(call(p,identity,8,model,h)[0],200,'genuinely unassociated')
                    assert models(s)[-1]==expected
            results.append({'case':'scope_loss_identity_pin_baseline','mode':mode,'repeat':repeat,'lost_tag_rejections':len(outcomes),'passed':True})

# Full explicit exchange advances authoritative history; late old worker cannot restore advice.
for delay in (0.0, .45):
    for repeat in range(3):
        def edit(c,s):
            config(c,s); c['context']['ttl_ms']=5000; s.interpreter_delay=delay
        with T.router(edit) as (p,s):
            scope=T.open_scope(p); hist=[{'role':'user','content':'start'}]
            T.turn(p,scope,1,hist)
            ok(T.ingest(p,T.event(scope,1,1)),202,'source')
            if not delay: time.sleep(.2)
            hist.append({'role':'user','content':'explicit private'})
            status,data,_=call(p,scope,2,'other',hist)
            ok(status,200,'preserve explicit other alias'); assert models(s)[-1]=='other-physical'
            hist.append(json.loads(data)['choices'][0]['message'])
            time.sleep(delay+.1)
            hist.append({'role':'user','content':'auto after full explicit history'})
            T.turn(p,scope,3,hist)
            assert models(s)==['frontier','other-physical','frontier'],models(s)
            results.append({'case':'mixed_explicit_auto_old_worker','delay':delay,'repeat':repeat,'models':models(s),'passed':True})

# Explicit calls participate in inflight exclusion in both directions and recover.
for first,second in (('auto','other'),('other','auto'),('other','baseline'),('other','other')):
    for repeat in range(3):
        def edit(c,s): config(c,s); s.chat_delay=.25
        with T.router(edit) as (p,s):
            scope=T.open_scope(p); hist=[{'role':'user','content':'start'}]; got=[]
            worker=threading.Thread(target=lambda:got.append(call(p,scope,1,first,hist)))
            worker.start()
            try:
                deadline=time.monotonic()+2
                while not models(s) and time.monotonic()<deadline: time.sleep(.005)
                assert models(s)
                ok(call(p,scope,2,second,hist)[0],409,'inflight')
            finally: worker.join()
            ok(got[0][0],200,'first completes'); assert len(models(s))==1
            hist.append(json.loads(got[0][1])['choices'][0]['message']); hist.append({'role':'user','content':'next'})
            ok(call(p,scope,3,'other',hist)[0],200,'scope released and full history accepts explicit')
            assert models(s)[-1]=='other-physical'
            results.append({'case':'inflight','first':first,'second':second,'repeat':repeat,'passed':True})

# Optional shadow failure does not veto; persistent source privacy still does.
for pinned in (False,True):
    def edit(c,s):
        config(c,s,'shadow'); c['context']['candidates'][0]['context_limit']=1; s.tool_response=pinned
    with T.router(edit) as (p,s):
        scope=T.open_scope(p); hist=[{'role':'user','content':'start'}]
        T.turn(p,scope,1,hist); assert models(s)==['frontier']
        s.tool_response=False
        ok(T.ingest(p,T.event(scope,1,1,'format alice@example.com')),202,'sensitive source')
        time.sleep(.3); hist.append({'role':'user','content':'clean continuation'})
        before=len(models(s))
        ok(call(p,scope,2,'baseline',hist)[0],403,'explicit privacy conflict')
        assert len(models(s))==before
        ok(call(p,scope,3,'auto',hist)[0],403 if pinned else 200,'mandatory shadow authority')
        if pinned: assert len(models(s))==before
        else: assert models(s)[-1]=='physical'
        results.append({'case':'shadow_optional_failure_mandatory_privacy','pinned':pinned,'passed':True})
print(json.dumps({'passed':True,'case_count':len(results),'cases':results},indent=2))
