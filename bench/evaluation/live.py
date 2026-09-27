"""Live egress admission and provider evidence. Never used by fixture mode.

Admission reserves a caller-reviewed worst-case dollar liability BEFORE dispatch,
including errors; it is not measured cost. Pricing/serving evidence must justify
that bound. Unknown provider or private-resource cost remains unknown.
"""
from decimal import Decimal
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit
import uuid


PUBLIC_RATES={'openai/gpt-4.1':('0.000002','0.000008'),
              'openai/gpt-4.1-mini':('0.0000004','0.0000016')}


def admission(config, endpoint, body):
    allowed={'model','messages','max_tokens','max_completion_tokens','temperature','top_p',
             'stream','stream_options','tools','tool_choice','parallel_tool_calls','response_format',
             'reasoning','reasoning_effort','stop','seed','frequency_penalty','presence_penalty'}
    if set(body)-allowed: raise ValueError('unreviewed request option / priced server tool')
    tools=body.get('tools') or []
    if any(t.get('type')!='function' for t in tools): raise ValueError('server tools forbidden')
    messages=body.get('messages') or []
    if any(m.get('content') is not None and not isinstance(m['content'],str) for m in messages):
        raise ValueError('only text messages are budget-qualified')
    output=body.get('max_tokens',body.get('max_completion_tokens'))
    if any(type(body[k]) is not int or not 0<body[k]<=4096 for k in ('max_tokens','max_completion_tokens') if k in body):
        raise ValueError('conflicting output bound')
    if type(output) is not int or not 0<output<=4096: raise ValueError('output bound')
    output=max(body[k] for k in ('max_tokens','max_completion_tokens') if k in body)
    # Byte-fallback tokenizer upper bound, not actual usage. Allow generous
    # per-message/tool framing plus 4096 fixed tokens. No images/server tools.
    upper=len(json.dumps(body).encode('utf-8'))+4096+128*(len(messages)+len(tools))
    if upper+output>config['context_limit']: raise ValueError('conservative context bound exceeded')
    model=body.get('model')
    if endpoint=='private':
        if model!=config['upstreams']['private']['model']: raise ValueError('private model not approved')
        return Decimal('0'),upper  # Public liability only, NOT private cost.
    if model not in PUBLIC_RATES: raise ValueError('public model not budget-qualified')
    input_rate,output_rate=map(Decimal,PUBLIC_RATES[model])
    return upper*input_rate+output*output_rate,upper


def create_allocation(config):
    # Parent must deduct this complete allocation from its aggregate allowance.
    # Exclusive creation forbids spending the same allocation twice after a crash.
    path=Path(config['allocation_path'])
    with path.open('x') as stream:
        os.chmod(path,0o600)
        stream.write(json.dumps({'allocation_reference':config['allocation_reference'],
            'approval_reference':config['approval_reference'],'request_cap':config['request_cap'],
            'paid_cap_usd':config['paid_cap_usd'],'resume_allowed':False})+'\n')
        stream.flush(); os.fsync(stream.fileno())


def validate_live(config):
    if config.get('approved') is not True or not config.get('approval_reference'):
        raise ValueError('fresh explicit live approval required; original allowance consumed')
    for name in ('paid_cap_usd',):
        v=config.get(name)
        if type(v) not in (int,float) or not math.isfinite(v) or v<=0:
            raise ValueError('positive reviewed '+name+' required')
    if not config.get('token_bound_evidence') or not config.get('source_and_metrics_review'):
        raise ValueError('review and worst-case tariff/output/context bound evidence required')
    if type(config.get('request_cap')) is not int or not 1<=config['request_cap']<=188:
        raise ValueError('allocation B total physical request cap must be 1..188 (conservatively includes public)')
    if config['paid_cap_usd']>10 or not config.get('allocation_reference') or not config.get('allocation_path'):
        raise ValueError('parent allocation and at most US$10 public required')
    if Path(config['allocation_path']).exists(): raise ValueError('allocation already used; reconcile with parent, never resume')
    if type(config.get('context_limit')) is not int or config['context_limit']<8192:
        raise ValueError('explicit common serving/harness context required')
    if not config.get('budget_review'):
        raise ValueError('review 8 turns, 4096 output including reasoning, 180s task deadline and context constraints')
    if config.get('isolation_reviewed') is not True:
        raise ValueError('dedicated gateway/egress isolation review required')
    if config.get('router_sha256')!=hashlib.sha256(Path(config['router_binary']).read_bytes()).hexdigest():
        raise ValueError('router binary hash mismatch')
    for name in ('private','public'):
        upstream=config['upstreams'][name]
        url=urlsplit(upstream['url'])
        if (url.scheme not in ('http','https') or not url.hostname or url.username or url.password or
                url.query or url.fragment or (name=='public' and url.scheme!='https')):
            raise ValueError('invalid upstream URL; public requires HTTPS')
        if upstream.get('reasoning_semantics') not in ('inclusive','additive','unknown'):
            raise ValueError('declare reasoning usage semantics')
        if not upstream.get('tokenizer') or not upstream.get('serving_evidence'):
            raise ValueError('model/tokenizer/context/output capability evidence required')
    if config.get('baseline_endpoint') not in ('private','public') or not config.get('baseline_model'):
        raise ValueError('explicit baseline required')


class RouteSession:
    """One episode's egress ledger, including auxiliaries; baseline is direct."""
    def __init__(self, config, out, task_id, arm, *, fixture=False, budget=None):
        self.egress=Egress(config,out,task_id,arm,fixture=fixture,budget=budget)
        self.config=config; self.arm=arm
        self.calls=self.egress.calls; self.traces=self.egress.traces
        self.context_events=[]

    def __enter__(self):
        if self.arm=='baseline': return self
        import copy
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import socket
        import subprocess
        self.api_key=uuid.uuid4().hex; self.source_key=uuid.uuid4().hex
        self.egress_token=uuid.uuid4().hex
        owner=self
        class Sink(BaseHTTPRequestHandler):
            def log_message(self, format, *args): pass
            def do_POST(self):
                parts=self.path.split('/')
                if (len(parts)!=6 or parts[1]!=owner.egress_token or parts[2] not in ('private','public') or
                        parts[3:]!=['v1','chat','completions']):
                    self.send_error(404); return
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=4*1024*1024: self.send_error(413); return
                status,raw,mime=owner.egress.forward(parts[2],json.loads(self.rfile.read(length)),{})
                self.send_response(status); self.send_header('Content-Type',mime)
                self.send_header('Content-Length',str(len(raw))); self.end_headers()
                self.wfile.write(raw)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Sink)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        with socket.socket() as port:
            port.bind(('127.0.0.1',0)); self.port=port.getsockname()[1]
        cfg=copy.deepcopy(self.config['router_config'])
        cfg['listen']={'host':'127.0.0.1','port':self.port}
        cfg['auth']={'api_key_env':'M3_EPISODE_API'}
        cfg['context']['source_key_env']='M3_EPISODE_SOURCE'
        for endpoint in ('private','public'):
            cfg[endpoint]['url']=f'http://127.0.0.1:{self.server.server_port}/{self.egress_token}/{endpoint}/v1'
            if endpoint=='private': cfg[endpoint].pop('api_key_env',None)
            else: cfg[endpoint]['api_key_env']='M3_EPISODE_API'
        path=self.egress.out/'router.private.json'; path.write_text(json.dumps(cfg))
        self.log=(self.egress.out/'router.private.log').open('w')
        try:
            self.process=subprocess.Popen([self.config['router_binary'],'serve',str(path),'--test-mode'],
                env={'PATH':os.environ.get('PATH',''),'M3_EPISODE_API':self.api_key,'M3_EPISODE_SOURCE':self.source_key},
                stdout=self.log,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                if self.process.poll() is not None:
                    raise RuntimeError('dedicated gateway startup: '+(self.egress.out/'router.private.log').read_text()[:1000])
                try:
                    conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=0.2)
                    conn.request('GET','/healthz'); response=conn.getresponse(); response.read()
                    if response.status==200: return self
                except OSError: pass
                finally: conn.close()
                time.sleep(0.02)
            raise RuntimeError('dedicated gateway readiness timeout')
        except BaseException:
            self.__exit__(None,None,None); raise

    def __exit__(self, *args):
        import subprocess
        if hasattr(self,'process'):
            self.process.terminate()
            try: self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill(); self.process.wait(timeout=5)
        if hasattr(self,'server'):
            self.server.shutdown(); self.server.server_close(); self.thread.join()
        if hasattr(self,'log'): self.log.close()
        return False

    def handle(self, path, body, headers):
        if self.arm!='baseline':
            if path=='/v1/chat/completions':
                body=dict(body,model=self.config['router_config']['context']['auto_alias'])
            if self.arm=='structured-only' and path.startswith('/v1/context') and isinstance(body.get('event'),dict):
                # Identical harness/observer; only router access to text is ablated.
                body=json.loads(json.dumps(body))
                body['event'].pop('text',None); body['event'].pop('text_truncated',None)
            self.context_events.append({'path':path,'body':body}) if path.startswith('/v1/context') else None
            hs={k:v for k,v in headers.items() if k.lower().startswith('x-recursant-')}
            hs['Content-Type']='application/json'
            hs['Authorization']='Bearer '+(self.source_key if path.startswith('/v1/context') else self.api_key)
            conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=185)
            try:
                conn.request('POST',path,json.dumps(body),hs)
                response=conn.getresponse(); raw=response.read(16*1024*1024+1)
                if len(raw)>16*1024*1024: raise ValueError('gateway response size limit')
                return response.status,raw,response.getheader('Content-Type','application/json')
            finally: conn.close()
        if path=='/v1/context/open':
            return 201,json.dumps(dict(body,generation=uuid.uuid4().hex)).encode(),'application/json'
        if path.startswith('/v1/context'):
            self.context_events.append(body)
            return 202,b'{}','application/json'
        if path!='/v1/chat/completions':
            return 404,b'{}','application/json'
        return self.egress.forward(self.config['baseline_endpoint'],body,headers)


class Egress:
    def __init__(self, config, out, task_id, arm, *, fixture=False, budget=None):
        self.config,self.out,self.task_id,self.arm=config,out,task_id,arm
        self.fixture=fixture
        self.calls=[]; self.traces=[]
        self.budget=budget if budget is not None else {'count':0,'reserved':Decimal('0'),'lock':threading.Lock()}
        self.budget.setdefault('private_lock',threading.Lock())

    def journal(self, call):
        paths=[self.out/'attempts.private.jsonl']
        if not self.fixture: paths.append(Path(self.config['allocation_path']))
        for path in paths:
            with path.open('a') as stream:
                stream.write(json.dumps(call,allow_nan=False)+'\n'); stream.flush(); os.fsync(stream.fileno())

    def forward(self, endpoint, body, headers):
        from contextlib import nullcontext
        with self.budget['private_lock'] if endpoint=='private' else nullcontext():
            return self._forward(endpoint,body,headers)

    def _forward(self, endpoint, body, headers):
        with self.budget['lock']:
            input_bound=None
            if self.fixture:
                liability=Decimal(str(self.config['liability_usd_per_dispatch']))
            else:
                try: liability,input_bound=admission(self.config,endpoint,body)
                except (ValueError,TypeError,KeyError):
                    return 400,b'{"error":"unqualified_model_or_context_or_tool_budget"}','application/json'
            if (self.budget['count']>=self.config['request_cap'] or
                    self.budget['reserved']+liability>Decimal(str(self.config['paid_cap_usd']))):
                return 429,b'{"error":"global_admission_cap"}','application/json'
            output=body.get('max_tokens',body.get('max_completion_tokens'))
            if type(output) is not int or not 0<output<=4096:
                return 400,b'{"error":"output_bound_required"}','application/json'
            self.budget['count']+=1; self.budget['reserved']+=liability
            # Role is conservative: router's private endpoint is shared with its
            # interpreter and carries no authenticated role discriminator.
            role='router-private-unclassified' if endpoint=='private' and self.arm!='baseline' else 'main'
            call=dict(dispatch_id=uuid.uuid4().hex,task_id=self.task_id,arm=self.arm,
                      attempt=len(self.calls)+1,role=role,evidence_kind='fixture' if self.fixture else 'actual',
                      evidence_ref='attempts.private.jsonl',input_tokens=None,output_tokens=None,
                      reasoning_tokens=None,cached_input_tokens=None,cost_usd=None,
                      reasoning_semantics='unknown',tokenizer=None,started_at=time.time(),
                      status=None,liability_reserved_usd=str(liability),endpoint=endpoint,
                      requested_model=body.get('model'),provider_model=None,input_token_upper_bound=input_bound)
            self.calls.append(call); self.journal(call)
        upstream=self.config['upstreams'][endpoint]
        url=urlsplit(upstream['url'])
        cls=http.client.HTTPSConnection if url.scheme=='https' else http.client.HTTPConnection
        conn=cls(url.hostname,url.port,timeout=180)
        timer=None
        try:
            conn.connect()
            sock=conn.sock
            def interrupt():
                import socket
                try: sock.shutdown(socket.SHUT_RDWR)
                except OSError: pass
            timer=threading.Timer(180,interrupt); timer.daemon=True; timer.start()
            auth=os.environ.get(upstream.get('api_key_env',''),'')
            hs={'Content-Type':'application/json'}
            if auth: hs['Authorization']='Bearer '+auth
            raw_request=json.dumps(body).encode()
            conn.request('POST',url.path.rstrip('/')+'/chat/completions',raw_request,hs)
            response=conn.getresponse()
            raw=response.read(16*1024*1024+1)
            if len(raw)>16*1024*1024: raise ValueError('response size limit')
            call['status']=response.status
            call['provider_response_sha256']=hashlib.sha256(raw).hexdigest()
            records=[]
            if raw.lstrip().startswith(b'data:'):
                for line in raw.splitlines():
                    if line.startswith(b'data:') and line[5:].strip()!=b'[DONE]':
                        records.append(json.loads(line[5:]))
            else:
                records=[json.loads(raw)]
            call['provider_model']=next((r['model'] for r in records if r.get('model')),None)
            usage=next((r['usage'] for r in reversed(records) if isinstance(r.get('usage'),dict)),{})
            call.update(input_tokens=usage.get('prompt_tokens'),output_tokens=usage.get('completion_tokens'),
                        reasoning_tokens=usage.get('completion_tokens_details',{}).get('reasoning_tokens'),
                        cached_input_tokens=usage.get('prompt_tokens_details',{}).get('cached_tokens'),
                        cost_usd=usage.get('cost'),reasoning_semantics=upstream['reasoning_semantics'],
                        tokenizer=upstream['tokenizer'])
            self.traces.append({'dispatch_id':call['dispatch_id'],'request':body,'response':raw.decode(errors='replace')})
            return response.status,raw,response.getheader('Content-Type','application/json')
        except (OSError,ValueError,http.client.HTTPException) as exc:
            call['error']=type(exc).__name__
            return 502,b'{"error":"ambiguous_upstream_attempt"}','application/json'
        finally:
            if timer: timer.cancel()
            conn.close(); call['finished_at']=time.time(); self.journal(call)
