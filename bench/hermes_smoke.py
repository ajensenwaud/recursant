#!/usr/bin/env python3
"""Run one isolated private-endpoint Hermes smoke; print metadata only.

Raw bodies stay in ignored .hermes/runtime/hermes/<run-id> (0700).
Reuse the SAME image/observer and change only --base-url for a routed run.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import selectors
import socket
import subprocess
import time
from urllib.parse import urlsplit
import uuid

ROOT = Path(__file__).resolve().parents[1]
SHA = 'd0288be5b3330d2442e3907185b8e9d0958297bb'


def terminal_executed(events):
    for event in events:
        p = event.get('payload', {})
        result = p.get('result', {})
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except ValueError:
                continue
        if (event.get('event') == 'post_tool_call' and p.get('tool_name') == 'terminal'
                and p.get('status') == 'ok' and isinstance(result, dict)
                and result.get('exit_code') == 0
                and result.get('output', '').strip() == 'ROUTING_OK'):
            return True
    return False


def task_completed(result):
    text = result.get('final_response')
    return (result.get('completed') is True and isinstance(text, str)
            and text.strip() == 'ROUTING_OK'
            and not any(result.get(k) for k in ('failed', 'partial', 'interrupted')))


def endpoint_address(base_url, network):
    url = urlsplit(base_url)
    if url.scheme != 'http' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('only plain private HTTP endpoints without credentials/query are supported')
    if network and (not network.startswith('container:') or not network[len('container:'):]):
        raise ValueError('only container:<router-container> network sharing is supported')
    address = socket.gethostbyname(url.hostname)
    ip = ipaddress.ip_address(address)
    allowed = [ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '100.64.0.0/10')]
    if not (any(ip in net for net in allowed) or (network and ip.is_loopback)):
        raise ValueError('endpoint must be private; loopback requires --network container:<router>')
    return address


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://gx10:8888/v1')
    parser.add_argument('--model', default='GLM-5.3-Flash-EXL3')
    parser.add_argument('--image', default='recursant-v4-hermes:local')
    parser.add_argument('--label', default='direct')
    parser.add_argument('--network', help='optional container:<router-container> network namespace')
    args = parser.parse_args()
    url = urlsplit(args.base_url)
    try:
        address = endpoint_address(args.base_url, args.network)
    except ValueError as exc:
        parser.error(str(exc))
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    directory = ROOT / '.hermes/runtime/hermes' / run_id
    subprocess.run(['git', 'check-ignore', '-q', str(directory / 'events.jsonl')], cwd=ROOT, check=True)
    os.umask(0o077)
    directory.mkdir(parents=True, mode=0o700)
    image_id = subprocess.check_output(['docker', 'image', 'inspect', args.image, '--format', '{{.Id}}'], text=True).strip()
    name = 'recursant-hermes-' + uuid.uuid4().hex[:12]
    command = ['docker', 'run', '--rm', '--name', name, '--read-only', '--cap-drop=ALL',
               '--security-opt=no-new-privileges', '--pids-limit=128', '--memory=2g', '--cpus=2',
               '--log-driver=none', '--user', f'{os.getuid()}:{os.getgid()}',
               '--tmpfs', '/tmp:rw,nosuid,size=128m,mode=1777',
               '--tmpfs', '/isolated:rw,nosuid,size=128m,mode=1777',
               '--tmpfs', '/workspace:rw,nosuid,size=64m,mode=1777',
               *(['--network', args.network] if args.network else ['--add-host', f'{url.hostname}:{address}']),
               '--mount', f'type=bind,src={directory},dst=/artifacts',
               '-e', f'BASELINE_URL={args.base_url}', '-e', f'BASELINE_MODEL={args.model}',
               '-e', 'HERMES_OBSERVER_PATH=/artifacts/events.jsonl',
               '-e', 'TERMINAL_ENV=local', '-e', 'TERMINAL_CWD=/workspace', image_id]
    (directory / 'command.json').write_text(json.dumps(command, indent=2))
    start = time.monotonic()
    timed_out = False
    kept = 0
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    selector = selectors.DefaultSelector()
    assert process.stdout is not None
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        with (directory / 'console.log').open('wb') as output:
            while selector.get_map():
                if time.monotonic() - start > 240:
                    timed_out = True
                    subprocess.run(['docker', 'kill', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    break
                for key, _ in selector.select(timeout=1):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    chunk = chunk[:max(0, 4194304 - kept)]
                    output.write(chunk)
                    kept += len(chunk)
        code = process.wait(timeout=15)
    finally:
        selector.close()
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    events_path = directory / 'events.jsonl'
    events = [json.loads(line) for line in events_path.read_text().splitlines()] if events_path.exists() else []
    counts = dict(Counter(e['event'] for e in events))
    source_path = directory / 'source.json'
    source = json.loads(source_path.read_text()) if source_path.exists() else {}
    result_path = directory / 'result.json'
    result = json.loads(result_path.read_text()) if result_path.exists() else {}
    passed = (code == 0 and not timed_out and source.get('sha') == SHA and source.get('pristine_before_run')
              and terminal_executed(events) and counts.get('pre_api_request', 0) > 0
              and counts.get('post_api_request', 0) > 0 and counts.get('on_stream_delta', 0) > 0
              and not counts.get('observer_storage_limit') and task_completed(result))
    summary = {'status': 'pass' if passed else 'fail', 'label': args.label,
               'image_id': image_id, 'source': source, 'exit_code': code, 'timed_out': timed_out,
               'hook_counts': counts, 'terminal_executed': terminal_executed(events),
               'completed': result.get('completed'), 'final_response_verified': task_completed(result), 'stream_completeness': 'unknown (upstream queue loss unobservable)',
               'artifact_directory': str(directory), 'elapsed_seconds': round(time.monotonic() - start, 3)}
    (directory / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
