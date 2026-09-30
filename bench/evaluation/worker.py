"""Mounted alone in the isolated image; contains no tasks, grader or oracle."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading

SHA='d0288be5b3330d2442e3907185b8e9d0958297bb'


class UnixConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(185)
        self.sock.connect('/bridge/api.sock')


class Relay(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_POST(self):
        body=self.rfile.read(int(self.headers.get('Content-Length','0')))
        conn=UnixConnection('localhost',timeout=185)
        try:
            conn.request('POST',self.path,body,dict(self.headers))
            response=conn.getresponse()
            self.send_response(response.status)
            self.send_header('Content-Type',response.getheader('Content-Type','application/json'))
            self.end_headers()
            while chunk:=response.read1(65536):
                self.wfile.write(chunk); self.wfile.flush()
        finally:
            conn.close()


def main():
    os.umask(0o077)
    git=['git','-c','safe.directory=/opt/hermes','-C','/opt/hermes']
    sha=subprocess.check_output(git+['rev-parse','HEAD'],text=True).strip()
    pristine=not subprocess.check_output(git+['status','--porcelain'],text=True)
    if sha!=SHA or not pristine:
        raise RuntimeError('pinned source mismatch')
    Path('/trace/source.json').write_text(json.dumps({'sha':sha,'pristine':pristine}))
    settings=json.loads(Path('/input/settings.json').read_text())
    for name in ('HOME','HERMES_HOME'):
        p=Path(os.environ[name]); p.mkdir(parents=True,exist_ok=False)
    home=Path(os.environ['HERMES_HOME'])
    shutil.copytree('/opt/observer',home/'plugins/recursant-observer')
    (home/'config.yaml').write_text('plugins:\n  enabled: [recursant-observer]\n  stream_reasoning_deltas: true\n')
    sys.path.insert(0,'/opt/hermes')
    # One-shot runner: nothing drains Hermes' async completion queue, so background
    # subagent results would be discarded when the turn ends. Declare the channel
    # stateless (as `hermes -z` does) so delegate_task runs children synchronously.
    # Deliberately NOT HERMES_SINGLE_QUERY_SESSION: that also enables no-user command
    # blocking, which would change harness behaviour versus the recorded baseline.
    from gateway.session_context import declare_stateless_channel
    declare_stateless_channel()
    from run_agent import AIAgent
    from agent.plugin_stream_hooks import shutdown_plugin_stream_hook_dispatcher
    server=ThreadingHTTPServer(('127.0.0.1',0),Relay)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    endpoint=f'http://127.0.0.1:{server.server_port}/v1'
    sys.path.insert(0,'/integration')
    from context_adapter.gateway import install_gateway
    from hermes_cli.plugins import PluginContext, PluginManifest, get_plugin_manager
    manager=get_plugin_manager(); manager.discover_and_load()
    ctx=PluginContext(PluginManifest(name='evaluation-context'),manager)
    os.environ['EVALUATION_SOURCE']='isolated-meter-only'
    bridge=install_gateway(ctx,enabled=True,endpoint=endpoint,
        task_id=settings['task_id'],session_id=settings['session_id'],branch='main',
        source_key_env='EVALUATION_SOURCE',content_enabled=True)
    (home/'config.yaml').write_text(json.dumps({
        'plugins':{'enabled':['recursant-observer'],'stream_reasoning_deltas':True},
        'model':{'default':settings['model'],'provider':'custom','base_url':endpoint,
                 'context_length':settings['context']}}))
    agent=AIAgent(model=settings['model'],base_url=endpoint,
                  api_key='isolated-meter-only',provider='custom',api_mode='chat_completions',
                  max_iterations=settings['turns'],max_tokens=settings['output'],
                  run_budget_seconds=settings['deadline_s'],quiet_mode=True,
                  skip_context_files=True,skip_memory=True,skip_background_review=True,
                  cwd='/workspace',save_trajectories=False,session_id=settings['session_id'])
    Path('/trace/harness-settings.json').write_text(json.dumps({
        'context':agent._config_context_length,'model':agent.model,'output':settings['output'],
        'turns':settings['turns'],'deadline_s':settings['deadline_s']}))
    try:
        result=agent.run_conversation(Path('/workspace/TASK.md').read_text(),task_id=settings['task_id'])
        shutdown_plugin_stream_hook_dispatcher(timeout=5)
        Path('/trace/result.json').write_text(json.dumps(result,default=str))
    finally:
        bridge.close(timeout=5)
        Path('/trace/scope.json').write_text(json.dumps(dict(bridge.scope,generation=bridge.generation,
            middleware_invocations=len(bridge.attempts),source_sequence=bridge.sequence,dropped=bridge.dropped,
            last_status=bridge.last_status)))
        agent.close(); server.shutdown(); server.server_close()


if __name__=='__main__':
    main()
