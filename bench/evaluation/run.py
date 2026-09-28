"""Full-artifact M3 fixture runner using installed pinned Hermes; no inference."""
import argparse
from contextlib import nullcontext
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import random
import socketserver
import subprocess
import tempfile
import threading
import time
import uuid
from .meter import Meter, handler
from .tasks import TASKS, CASES, fingerprint

IMAGE='sha256:ad2bceb50b5074adf042afd53079eb57f0f17e0e9ce4257a0e03a91ad3e55f1b'
SETTINGS=dict(model='fixture',turns=8,output=4096,deadline_s=180,
              context=65536,
              reasoning='pinned upstream defaults; not disabled', sampling='pinned upstream defaults',
              toolsets='pinned upstream default', cpus=2, memory='2g', pids=128,
              request_cap=16)
from .live import CANONICAL_ARMS as ARMS
HERE=Path(__file__).resolve().parent


def write(path, data):
    path.write_text(json.dumps(data,indent=2,sort_keys=True,allow_nan=False)+'\n')


def sandbox(name):
    return ['docker','run','--rm','--pull=never','--name',name,'--network=none',
            '--read-only','--cap-drop=ALL','--security-opt=no-new-privileges',
            '--pids-limit=128','--memory=2g','--cpus=2','--log-driver=none',
            '--user',f'{os.getuid()}:{os.getgid()}',
            '--tmpfs','/tmp:rw,nosuid,size=128m,mode=1777',
            '--tmpfs','/isolated:rw,nosuid,size=128m,mode=1777']


def bounded_run(command, *, timeout, output, stdin=None):
    name=command[command.index('--name')+1]
    try:
        with output.open('w') as stream:
            proc=subprocess.run(command,input=stdin,text=True,stdout=stream,stderr=subprocess.STDOUT,
                                timeout=timeout)
        return proc.returncode
    except subprocess.TimeoutExpired:
        return 124
    finally:
        subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


def verify(task_id, workspace, out):
    solution=workspace/'solution.py'
    if not solution.is_file() or solution.is_symlink() or solution.stat().st_size>1048576:
        return dict(success=False,passed=0,total=len(CASES[task_id]),failure='missing_or_invalid_artifact')
    # Only the candidate artifact enters a fresh no-network verifier container.
    # Hidden expected values and grader code remain host-side.
    submission=out/'submission'; submission.mkdir()
    (submission/'solution.py').write_bytes(solution.read_bytes())
    command=sandbox('m3-grade-'+uuid.uuid4().hex[:12])+[
        '-i','--mount',f'type=bind,src={submission},dst=/submission,readonly',
        '--entrypoint','python',IMAGE,'/submission/solution.py']
    inputs=''.join(json.dumps(v)+'\n' for v,_ in CASES[task_id])
    code=bounded_run(command,timeout=15,output=out/'grader-output.private',stdin=inputs)
    try:
        lines=(out/'grader-output.private').read_text().splitlines()
        actual=[json.loads(line) for line in lines]
        checks=[a==e and type(a) is type(e) for a,(_,e) in zip(actual,CASES[task_id])]
        passed=sum(checks)
        success=code==0 and len(actual)==len(CASES[task_id]) and all(checks)
    except (ValueError,OSError):
        passed=0; success=False
    return dict(success=success,passed=passed,total=len(CASES[task_id]),exit_code=code,
                artifact_sha256=hashlib.sha256(solution.read_bytes()).hexdigest())


def run_episode(task, arm, out, settings, *, live_config=None, protocol_fixture=False, budget=None):
    out=out.resolve(); out.mkdir(parents=True,exist_ok=False)
    os.chmod(out,0o700)
    workspace=out/'workspace'; workspace.mkdir()
    trace=out/'trace'; trace.mkdir()
    inputs=out/'input'; inputs.mkdir()
    (workspace/'TASK.md').write_text(task['prompt'])
    settings=dict(settings,task_id=task['id'],session_id=uuid.uuid4().hex)
    if live_config:
        settings['model']=live_config['baseline_model']
    write(inputs/'settings.json',settings)
    if live_config:
        from .live import RouteSession
        meter=RouteSession(live_config,out,task['id'],arm,fixture=protocol_fixture,budget=budget)
        lifecycle=meter
    else:
        meter=Meter(mode='fixture',request_cap=settings['request_cap'])
        lifecycle=nullcontext()
    start=time.monotonic()
    # Short socket pathname avoids AF_UNIX path-length issues; no sibling mount.
    with lifecycle, tempfile.TemporaryDirectory(prefix='m3-bridge-') as bridge:
        server=socketserver.ThreadingUnixStreamServer(str(Path(bridge)/'api.sock'),
                                                      handler(meter,task['id'],arm))
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        command=sandbox('m3-task-'+uuid.uuid4().hex[:12])+[
            '--mount',f'type=bind,src={workspace},dst=/workspace',
            '--mount',f'type=bind,src={trace},dst=/trace',
            '--mount',f'type=bind,src={inputs},dst=/input,readonly',
            '--mount',f'type=bind,src={bridge},dst=/bridge,readonly',
            '--mount',f'type=bind,src={HERE / "worker.py"},dst=/runner.py,readonly',
            '--mount',f'type=bind,src={HERE.parents[1] / "deploy/hermes/context_adapter"},dst=/integration/context_adapter,readonly',
            '-e','HERMES_OBSERVER_PATH=/trace/events.jsonl',
            '-e','TERMINAL_ENV=local','-e','TERMINAL_CWD=/workspace',
            '--entrypoint','python',IMAGE,'/runner.py']
        write(out/'command.private.json',command)
        try:
            code=bounded_run(command,timeout=settings['deadline_s']+30,output=out/'console.private.log')
        finally:
            server.shutdown(); server.server_close(); thread.join()
    def load(path):
        try: return json.loads(path.read_text())
        except (OSError,ValueError): return {}
    source=load(trace/'source.json'); result=load(trace/'result.json')
    events=[]
    if (trace/'events.jsonl').exists():
        for line in (trace/'events.jsonl').read_text().splitlines():
            try: events.append(json.loads(line))
            except ValueError: pass
    verdict=verify(task['id'],workspace,out)
    row=dict(task_id=task['id'],arm=arm,evidence_kind='actual' if live_config and not protocol_fixture else 'fixture',success=verdict['success'],
             verifier=verdict,exit_code=code,harness_completed=result.get('completed'),
             elapsed_seconds=time.monotonic()-start,source=source,
             hook_counts=dict(Counter(e.get('event') for e in events)),
             physical_attempts=len(meter.calls),calls=meter.calls,
             collection_complete=True,dispatch_ids=[c['dispatch_id'] for c in meter.calls],
             harness_settings=load(trace/'harness-settings.json'),
             context_event_count=len(meter.context_events),scope=load(trace/'scope.json'),
             readiness={'eligible_dispatches':None,'semantic_ready_dispatches':None,
                        'reason':'not independently observed; context events retained, no readiness inferred'},
             failure=None if verdict['success'] else ('timeout' if code==124 else 'verifier_or_harness_failure'))
    write(out/'context.private.json',meter.context_events)
    write(out/'calls.private.json',meter.calls)
    write(out/'traces.private.json',meter.traces)
    write(out/'outcome.json',row)
    return row


def plan(repeats, seed):
    if type(repeats) is not int or not 1<=repeats<=10: raise ValueError('repeats must be 1..10')
    assignments=[]; rng=random.Random(seed)
    for repeat in range(repeats):
        for task in TASKS:
            order=list(ARMS); rng.shuffle(order)
            for arm in order:
                pair=f'{task["id"]}-r{repeat}'
                assignments.append(dict(episode_id=f'{pair}-{arm}',pair_id=pair,task_id=task['id'],arm=arm))
    return assignments


def recover_outcomes(out, assignments, rows):
    rows=list(rows); present={r['episode_id'] for r in rows}
    for assignment in assignments:
        if assignment['episode_id'] in present: continue
        journal=out/assignment['episode_id']/'attempts.private.jsonl'
        if not journal.exists(): continue
        latest={}
        for line in journal.read_text().splitlines():
            try:
                call=json.loads(line); latest[call['dispatch_id']]=call
            except (ValueError,KeyError): pass
        rows.append(dict(assignment,success=False,calls=list(latest.values()),
                         collection_complete=False,evidence_kind='unreconciled',failure='interrupted'))
    return rows


def main(argv=None):
    from .report import summarize
    from .live import validate_live, create_allocation
    from decimal import Decimal
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['fixture','live'],default='fixture')
    parser.add_argument('--config',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--repeats',type=int,default=2)
    parser.add_argument('--seed',type=int,default=7321)
    parser.add_argument('--report-only',action='store_true')
    args=parser.parse_args(argv)
    if args.report_only:
        manifest=json.loads((args.out/'manifest.json').read_text())
        path=args.out/'outcomes.json'
        rows=json.loads(path.read_text()) if path.exists() else []
        rows=recover_outcomes(args.out,manifest['assignments'],rows)
        report=summarize(manifest['assignments'],rows)
        write(args.out/'report.json',report); print(json.dumps(report,indent=2)); return 0
    assignments=plan(args.repeats,args.seed)
    config=None
    if args.mode=='live':
        if args.config is None: parser.error('--config with fresh approval and reviewed bounds required')
        config=json.loads(args.config.read_text()); validate_live(config)
    os.umask(0o077)
    args.out.mkdir(parents=True,exist_ok=False)
    if config: create_allocation(config)
    settings=dict(SETTINGS)
    if config: settings['context']=config['context_limit']
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.py')}
    adapter=HERE.parents[1]/'deploy/hermes/context_adapter'
    hashes.update({'adapter/'+p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in adapter.glob('*.py')})
    manifest=dict(version=1,evidence_kind=args.mode,task_pack_sha256=fingerprint(),
                  image=IMAGE,settings=settings,arms=ARMS,repeats=args.repeats,seed=args.seed,
                  assignments=assignments,source_sha256=hashes,
                  configuration_sha256=hashlib.sha256(args.config.read_bytes()).hexdigest() if config else None,
                  limits={'max_physical_dispatches':config['request_cap'] if config else len(assignments)*settings['request_cap'],
                          'paid_cap_usd':config['paid_cap_usd'] if config else None})
    write(args.out/'manifest.json',manifest)
    rows=[]; budget={'count':0,'reserved':Decimal('0'),'lock':threading.Lock()}
    try:
        for assignment in assignments:
            task=next(t for t in TASKS if t['id']==assignment['task_id'])
            out=args.out/assignment['episode_id']
            try:
                row=run_episode(task,assignment['arm'],out,settings,live_config=config,budget=budget)
            except Exception as exc:
                # Interrupted/failed setup is still an assigned task. Preserve
                # any already-admitted costs instead of dropping the episode.
                latest={}
                journal=out/'attempts.private.jsonl'
                if journal.exists():
                    for line in journal.read_text().splitlines():
                        try:
                            call=json.loads(line); latest[call['dispatch_id']]=call
                        except ValueError: pass
                row=dict(success=False,calls=list(latest.values()),collection_complete=False,
                         failure='orchestration_'+type(exc).__name__,evidence_kind=args.mode)
            row.update(assignment); rows.append(row)
            write(args.out/'outcomes.json',rows)
            write(args.out/'report.json',summarize(assignments,rows))
    finally:
        rows=recover_outcomes(args.out,assignments,rows)
        write(args.out/'outcomes.json',rows)
        report=summarize(assignments,rows)
        write(args.out/'report.json',report)
    print(json.dumps(report,indent=2))
    return 0 if report['assigned']==report['successes'] else 1


if __name__=='__main__':
    raise SystemExit(main())
