import sys, json, time, threading, socket, struct
sys.path.insert(0, '/src/tests/integration')
from test_gateway_context import GatewayContextTests, ContextSink
T = GatewayContextTests()
results = {}
def edit(c,s):
    T.configure(c,s); s.RequestHandlerClass=ContextSink
# Scoped explicit requests must not leave old auto evidence eligible.
with T.router(edit) as (p,s):
    scope=T.open_scope(p); hist=[{'role':'user','content':'start'}]
    T.turn(p,scope,1,hist); assert T.ingest(p,T.event(scope,1,1))==202; time.sleep(.25)
    s.tool_response=True
    status,data,_=T.request(p,headers=T.headers(scope,2),body={'model':'baseline','messages':hist,'max_tokens':128})
    s.tool_response=False
    hist.append({'role':'user','content':'continue without mentioning the tool exchange'})
    T.turn(p,scope,3,hist)
    results['explicit_tool_exchange']={'explicit_status':status,'tool_reply':json.loads(data),'subsequent_auto_model':s.seen[-1][2]['model']}
# Shadow selection failure must not deny an otherwise baseline-forwardable request.
def tiny(c,s):
    T.configure(c,s,'shadow'); s.RequestHandlerClass=ContextSink
    c['context']['candidates'][0]['context_limit']=1
with T.router(tiny) as (p,s):
    scope=T.open_scope(p)
    body={'model':'auto','messages':[{'role':'user','content':'hello'}],'max_tokens':128}
    unassociated=T.request(p,body=body)[0]
    associated=T.request(p,body=body,headers=T.headers(scope,1))[0]
    results['shadow_candidate_veto']={'unassociated_status':unassociated,'associated_status':associated,'physical_dispatches':len(s.seen)}
# Shadow sensitive observations currently change actual routing.
def shadow(c,s):
    T.configure(c,s,'shadow');s.RequestHandlerClass=ContextSink
    c['compliance']={'enabled':True,'public_allowed':True}
with T.router(shadow) as (p,s):
    scope=T.open_scope(p);hist=[{'role':'user','content':'start'}]
    T.turn(p,scope,1,hist); first=s.seen[-1][2]['model']
    assert T.ingest(p,T.event(scope,1,1,'format alice@example.com'))==202
    time.sleep(.25);hist.append({'role':'user','content':'continue'})
    T.turn(p,scope,2,hist)
    results['shadow_source_placement']={'first_model':first,'second_model':s.seen[-1][2]['model']}
# Reset cancellation should release scope but pin to original owner.
def slow(c,s):
    edit(c,s); s.chat_delay=.5
with T.router(slow) as (p,s):
    scope=T.open_scope(p)
    body=json.dumps({'model':'auto','messages':[{'role':'user','content':'start'}],'max_tokens':128}).encode()
    headers={'Authorization':'Bearer local-test-key','Content-Length':str(len(body)),**T.headers(scope,1)}
    wire=('POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\n'+''.join(k+': '+v+'\r\n' for k,v in headers.items())+'\r\n').encode()+body
    sock=socket.create_connection(('127.0.0.1',p));sock.sendall(wire)
    for _ in range(100):
        if s.seen:break
        time.sleep(.01)
    sock.setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack('ii',1,0));sock.close();time.sleep(1.2)
    code=T.request(p,headers=T.headers(scope,2),body={'model':'auto','messages':[{'role':'user','content':'new clean history'}],'max_tokens':128})[0]
    results['client_reset']={'next_status':code,'next_model':s.seen[-1][2]['model']}
print(json.dumps(results,indent=2))
