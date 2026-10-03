import json,os,subprocess,tempfile,pathlib
base={'listen':{'host':'127.0.0.1','port':12345},'private':{'url':'http://127.0.0.1:1/v1','model':'physical'},'public':{'url':'http://127.0.0.1:1/v1','model':'frontier','api_key_env':'RC_TEST_AUTH'},'auth':{'api_key_env':'RC_TEST_AUTH'},'aliases':[{'from':'baseline','endpoint':'public','model':'frontier'},{'from':'cheap','endpoint':'private','model':'physical'}],'context':{'mode':'active','tenant':'local','project':'single','source_key_env':'RC_TEST_SOURCE','auto_alias':'auto','baseline_alias':'baseline','ttl_ms':2000,'candidates':[{'alias':'baseline','quality_evidence':'fixture','qualified_tasks':[],'context_limit':100000,'expected_task_cost':10},{'alias':'cheap','quality_evidence':'fixture','qualified_tasks':['format_simple'],'context_limit':100000,'expected_task_cost':1}]}}
for cap in (None,[],True,{'future':True},{'tool_history':1},{'function_tools':'true'},{'parallel_tools':None}):
    base['context']['candidates'][1]['capabilities']=cap
    with tempfile.TemporaryDirectory() as d:
        p=pathlib.Path(d)/'config.json';p.write_text(json.dumps(base))
        r=subprocess.run([os.environ['RECURSANT_BIN'],'serve',str(p),'--test-mode'],env=dict(os.environ,RC_TEST_SOURCE='source-only-test-key',RC_TEST_AUTH='local-test-key'),capture_output=True,timeout=3)
        assert r.returncode!=0,(cap,r.stdout,r.stderr)
        assert b'AddressSanitizer' not in r.stderr and b'runtime error:' not in r.stderr,r.stderr
        assert b'invalid runtime configuration' in r.stderr,r.stderr
        print('rejected',repr(cap),'exit',r.returncode)
print('7 malformed capability configurations rejected')
# A matching valid control proves the matrix did not fail on another field.
import time,http.client
base['context']['candidates'][1]['capabilities']={'tool_history':True,'function_tools':True,'parallel_tools':False}
with tempfile.TemporaryDirectory() as d:
    p=pathlib.Path(d)/'config.json';p.write_text(json.dumps(base))
    proc=subprocess.Popen([os.environ['RECURSANT_BIN'],'serve',str(p),'--test-mode'],env=dict(os.environ,RC_TEST_SOURCE='source-only-test-key',RC_TEST_AUTH='local-test-key'),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for _ in range(100):
            assert proc.poll() is None,'valid control exited'
            try:
                c=http.client.HTTPConnection('127.0.0.1',12345,timeout=1);c.request('GET','/healthz');code=c.getresponse().status;c.close()
                if code==200:break
            except OSError:time.sleep(.01)
        else:raise AssertionError('valid control not ready')
    finally:
        proc.terminate();out,err=proc.communicate(timeout=5)
    assert proc.returncode==0,err
    assert b'AddressSanitizer' not in err and b'runtime error:' not in err,err
print('valid boolean capability control starts and shuts down cleanly')
