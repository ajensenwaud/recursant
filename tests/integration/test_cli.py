"""recursant CLI: check, configure, install --dry-run, serve + status. No systemd, no network."""
import http.server
import json
import os
import pathlib
import socket
import stat
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

BIN = pathlib.Path(os.environ.get('RECURSANT_BIN', pathlib.Path(__file__).resolve().parents[2] / 'build/container/recursant'))
KEYS = {'RC_CLI_AUTH': 'cli-client-key', 'RC_CLI_PUBLIC': 'cli-public-key'}


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def config(port=8080, sink=9):
    return {'listen': {'host': '127.0.0.1', 'port': port},
            'providers': [{'name': 'local', 'trust': 'private', 'url': 'http://127.0.0.1:%d/v1' % sink, 'adapter': 'openai-compatible'},
                          {'name': 'gw', 'trust': 'public', 'url': 'https://gateway.example/v1', 'key_env': 'RC_CLI_PUBLIC',
                           'adapter': 'openai-compatible'}],
            'private_default': {'provider': 'local', 'model': 'physical'},
            'auth': {'api_key_env': 'RC_CLI_AUTH'},
            'aliases': [{'from': 'alias', 'provider': 'local', 'model': 'physical'}]}


class CLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        # Isolated HOME: the CLI's default paths must never touch the real user.
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('RC_CLI_', 'RECURSANT_', 'XDG_'))}
        self.env['HOME'] = str(self.dir / 'home')

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, env=None, stdin=None):
        return subprocess.run([str(BIN), *map(str, args)], env={**self.env, **(env or {})}, input=stdin,
                              capture_output=True, text=True, timeout=30)

    def write(self, cfg, name='config.json'):
        path = self.dir / name
        path.write_text(json.dumps(cfg))
        return path

    # ---- usage ----
    def test_help_and_version(self):
        self.assertEqual(self.run_cli('--help').returncode, 0)
        self.assertIn('install', self.run_cli('--help').stdout)
        v = self.run_cli('version')
        self.assertEqual(v.returncode, 0)
        self.assertRegex(v.stdout, r'^recursant \d+\.\d+')
        self.assertEqual(self.run_cli().returncode, 2)
        self.assertEqual(self.run_cli('frobnicate').returncode, 2)
        self.assertEqual(self.run_cli('check', '--bogus').returncode, 2)

    # ---- check ----
    def test_check_reports_summary_and_names_missing_secrets(self):
        path = self.write(config())
        ok = self.run_cli('check', '--config', path, env=KEYS)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn('configuration valid', ok.stdout)
        self.assertIn('providers   2 (1 private, 1 public)', ok.stdout)
        missing = self.run_cli('check', path, env={'RC_CLI_AUTH': 'x'})
        self.assertEqual(missing.returncode, 1)
        self.assertIn('secret not set: RC_CLI_PUBLIC', missing.stderr)
        structure = self.run_cli('check', path, '--no-secrets')
        self.assertEqual(structure.returncode, 0, structure.stderr)
        self.assertIn('secrets     not set:', structure.stdout)
        for name in ('RC_CLI_AUTH', 'RC_CLI_PUBLIC'):
            self.assertIn(name, structure.stdout)

    def test_check_names_the_reason(self):
        cfg = config(); cfg['listen']['bogus'] = 1
        r = self.run_cli('check', self.write(cfg), env=KEYS)
        self.assertEqual(r.returncode, 1)
        self.assertIn('listen: unknown key "bogus"', r.stderr)
        cfg = config(); cfg['aliases'][0]['provider'] = 'nope'
        self.assertIn('unknown provider nope', self.run_cli('check', self.write(cfg), env=KEYS).stderr)
        cfg = config(); cfg['providers'][1]['url'] = 'http://gateway.example/v1'
        self.assertIn('provider gw: url must be https', self.run_cli('check', self.write(cfg), env=KEYS).stderr)
        # The original spelling keeps its terse contract and its prefix.
        v = self.run_cli('validate', self.write(cfg), env=KEYS)
        self.assertEqual(v.returncode, 1)
        self.assertTrue(v.stderr.startswith('invalid runtime configuration: '), v.stderr)
        broken = self.dir / 'broken.json'
        broken.write_text('{"compliance": {"patterns": ["secret-pattern-123"]')
        r = self.run_cli('check', broken, env=KEYS)
        self.assertIn('not valid JSON (line 1', r.stderr)
        self.assertNotIn('secret-pattern', r.stderr)

    def test_env_file_next_to_config_supplies_secrets_only_when_private(self):
        path = self.write(config())
        envfile = self.dir / 'recursant.env'
        envfile.write_text('# keys\nRC_CLI_AUTH=from-file\nexport RC_CLI_PUBLIC="quoted"\n')
        envfile.chmod(0o600)
        self.assertEqual(self.run_cli('check', path).returncode, 0)
        envfile.chmod(0o644)
        r = self.run_cli('check', path)
        self.assertEqual(r.returncode, 1)
        self.assertIn('not readable by others', r.stderr)

    def test_symbolic_listen_hosts(self):
        for host in ('localhost', 'any'):
            cfg = config(); cfg['listen']['host'] = host
            self.assertEqual(self.run_cli('check', self.write(cfg), env=KEYS).returncode, 0, host)
        cfg = config(); cfg['listen']['host'] = 'tailnet'
        r = self.run_cli('check', self.write(cfg), env=KEYS)
        if r.returncode == 0:
            self.assertIn('(tailnet)', r.stdout)  # this host really is on a tailnet
        else:
            self.assertIn('no Tailscale address', r.stderr)
        cfg = config(); cfg['listen']['host'] = 'example.com'
        self.assertIn('listen.host must be', self.run_cli('check', self.write(cfg), env=KEYS).stderr)

    def test_more_than_32_providers(self):
        cfg = config()
        cfg['providers'] += [{'name': 'p%d' % i, 'trust': 'private', 'url': 'http://10.0.0.%d:8000/v1' % i,
                              'adapter': 'openai-compatible'} for i in range(1, 60)]
        self.assertEqual(self.run_cli('check', self.write(cfg), env=KEYS).returncode, 0)

    # ---- configure ----
    def test_configure_creates_backs_up_and_refuses_invalid(self):
        path = self.dir / 'new' / 'config.json'
        created = self.run_cli('configure', '--config', path, '--add-provider', 'openrouter', '--alias', 'economy=openrouter:openai/gpt-6-luna')
        self.assertEqual(created.returncode, 0, created.stderr)
        cfg = json.loads(path.read_text())
        router = next(p for p in cfg['providers'] if p['name'] == 'openrouter')
        self.assertEqual((router['url'], router['key_env'], router['adapter'], router['trust']),
                         ('https://openrouter.ai/api/v1', 'OPENROUTER_API_KEY', 'openrouter', 'public'))
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        envfile = path.parent / 'recursant.env'
        self.assertEqual(stat.S_IMODE(envfile.stat().st_mode), 0o600)
        self.assertRegex(envfile.read_text(), r'RECURSANT_API_KEY=[0-9a-f]{48}\n')
        self.assertNotIn(envfile.read_text().split('RECURSANT_API_KEY=')[1][:48], created.stdout)  # never echoed
        self.assertIn('key missing OPENROUTER_API_KEY', created.stdout)

        before = path.read_text()
        bad = self.run_cli('configure', '--config', path, '--alias', 'x=nowhere:model')
        self.assertEqual(bad.returncode, 1)
        self.assertIn('no provider named nowhere', bad.stderr)
        refused = self.run_cli('configure', '--config', path, '--remove-provider', 'openrouter')
        self.assertEqual(refused.returncode, 1)
        self.assertIn('alias economy uses openrouter', refused.stderr)
        regex = self.run_cli('configure', '--config', path, '--add-pattern', '(unclosed')
        self.assertEqual(regex.returncode, 1)
        self.assertEqual(path.read_text(), before)
        self.assertEqual(list(path.parent.glob('*.bak')), [])

        dry = self.run_cli('configure', '--config', path, '--port', '9090', '--dry-run')
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertEqual(json.loads(dry.stdout)['listen']['port'], 9090)
        self.assertEqual(path.read_text(), before)

        edit = self.run_cli('configure', '--config', path, '--add-provider', 'lab', '--url', 'http://gx10:8888/v1', '--trust', 'private',
                            '--private-default', 'lab:GLM-5.3-Flash-EXL3', '--add-pattern', r'\bPROJ-\d{4}\b', '--listen', 'any')
        self.assertEqual(edit.returncode, 0, edit.stderr)
        backups = list(path.parent.glob('config.json.*.bak'))
        self.assertEqual(len(backups), 1)
        self.assertRegex(backups[0].name, r'^config\.json\.\d{4}-\d\d-\d\d-\d{6}\.bak$')
        self.assertEqual(backups[0].read_text(), before)
        cfg = json.loads(path.read_text())
        self.assertEqual(cfg['private_default'], {'provider': 'lab', 'model': 'GLM-5.3-Flash-EXL3'})
        self.assertIn(r'\bPROJ-\d{4}\b', cfg['compliance']['patterns'])
        self.assertEqual(cfg['listen']['host'], 'any')

    def test_configure_private_default_must_be_private(self):
        path = self.dir / 'config.json'
        self.assertEqual(self.run_cli('configure', '--config', path, '--add-provider', 'groq').returncode, 0)
        r = self.run_cli('configure', '--config', path, '--private-default', 'groq:llama')
        self.assertEqual(r.returncode, 1)
        self.assertIn('not a private provider', r.stderr)

    def test_configure_set_key_reads_stdin_not_argv(self):
        path = self.write(config())
        r = self.run_cli('configure', '--config', path, '--set-key', 'RC_CLI_PUBLIC', stdin='sk-test-123\n')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('RC_CLI_PUBLIC=sk-test-123\n', (self.dir / 'recursant.env').read_text())
        self.assertNotIn('sk-test-123', r.stdout + r.stderr)
        self.assertEqual(list(self.dir.glob('*.bak')), [])  # a key alone does not rewrite the config
        bad = self.run_cli('configure', '--config', path, '--set-key', 'RC_CLI_PUBLIC', stdin='has space\n')
        self.assertEqual(bad.returncode, 1)

    def test_configure_converts_legacy_form(self):
        path = self.write({'listen': {'host': '127.0.0.1', 'port': 8080},
                           'private': {'url': 'http://127.0.0.1:9/v1', 'model': 'physical'},
                           'public': {'url': 'https://openrouter.ai/api/v1', 'api_key_env': 'RC_CLI_PUBLIC'},
                           'auth': {'api_key_env': 'RC_CLI_AUTH'},
                           'aliases': [{'from': 'big', 'endpoint': 'public', 'model': 'openai/gpt-6-luna'}]})
        r = self.run_cli('configure', '--config', path, '--add-provider', 'mistral', env=KEYS)
        self.assertEqual(r.returncode, 0, r.stderr)
        cfg = json.loads(path.read_text())
        self.assertNotIn('private', cfg)
        self.assertEqual([p['name'] for p in cfg['providers']], ['private', 'public', 'mistral'])
        self.assertEqual(cfg['providers'][1]['adapter'], 'openrouter')
        self.assertEqual(cfg['aliases'][0], {'from': 'big', 'model': 'openai/gpt-6-luna', 'provider': 'public'})

    def test_configure_lists_known_gateways_and_needs_a_terminal(self):
        r = self.run_cli('configure', '--list-providers')
        for name in ('openrouter', 'openai', 'groq', 'mistral', 'deepseek', 'together'):
            self.assertIn(name, r.stdout)
        self.assertEqual(self.run_cli('configure', '--config', self.write(config()), stdin='').returncode, 2)

    def test_check_refuses_the_disabled_judge(self):
        # The decision-model judge (Jev/Decider) is off in default builds: a config
        # that asks for it is refused with the reason, not silently ignored.
        quick = json.loads((pathlib.Path(__file__).resolve().parents[2] / 'config/recursant.quickstart.json').read_text())
        quick['context']['judge'] = {'provider': 'openrouter', 'model': 'jev', 'url': 'https://example.test/v1/decisions',
                                     'timeout_ms': 500, 'routine_min': 0.9, 'difficulty_max': 0.5}
        keys = {'RECURSANT_API_KEY': 'a', 'OPENROUTER_API_KEY': 'b', 'RECURSANT_SOURCE_KEY': 'c'}
        refused = self.run_cli('check', self.write(quick, 'judge.json'), env=keys)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn('judge is disabled in this build', refused.stderr)

    def test_check_warns_when_auto_sessions_have_no_private_candidate(self):
        quick = json.loads((pathlib.Path(__file__).resolve().parents[2] / 'config/recursant.quickstart.json').read_text())
        keys = {'RECURSANT_API_KEY': 'a', 'OPENROUTER_API_KEY': 'b', 'RECURSANT_SOURCE_KEY': 'c'}
        ok = self.run_cli('check', self.write(quick, 'quick.json'), env=keys)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertNotIn('no private context candidate', ok.stderr)
        quick['context']['candidates'] = [c for c in quick['context']['candidates'] if c['alias'] != 'local']
        warned = self.run_cli('check', self.write(quick, 'nolocal.json'), env=keys)
        self.assertEqual(warned.returncode, 0)  # a warning, not an error: it fails closed
        self.assertIn('no private context candidate', warned.stderr)

    # ---- install ----
    def test_install_dry_run_renders_units_and_writes_nothing(self):
        user_cfg = self.dir / 'home' / '.config' / 'recursant' / 'config.json'
        user_cfg.parent.mkdir(parents=True)
        user_cfg.write_text(json.dumps(config()))
        r = self.run_cli('install', '--user', '--dry-run')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('serve --config %s' % user_cfg, r.stdout)
        self.assertIn('EnvironmentFile=-%s' % (user_cfg.parent / 'recursant.env'), r.stdout)
        self.assertIn('WantedBy=default.target', r.stdout)
        self.assertIn('would run: systemctl --user enable recursant.service', r.stdout)
        self.assertFalse((self.dir / 'home' / '.config' / 'systemd').exists())
        self.assertFalse((self.dir / 'home' / '.local').exists())
        system = self.run_cli('install', '--system', '--dry-run', '--config', self.write(config()))
        self.assertEqual(system.returncode, 0, system.stderr)
        for line in ('DynamicUser=yes', 'LoadCredential=config.json:', 'ExecStart=/usr/local/bin/recursant serve --config ${CREDENTIALS_DIRECTORY}/config.json',
                     'CapabilityBoundingSet=\n', 'SyslogIdentifier=recursant'):
            self.assertIn(line, system.stdout)
        low = config(port=443)
        self.assertIn('AmbientCapabilities=CAP_NET_BIND_SERVICE',
                      self.run_cli('install', '--system', '--dry-run', '--config', self.write(low, 'low.json')).stdout)
        cfg = config(); cfg['aliases'][0]['provider'] = 'nope'
        self.assertEqual(self.run_cli('install', '--user', '--dry-run', '--config', self.write(cfg, 'bad.json')).returncode, 1)
        self.assertEqual(self.run_cli('install', '--user', '--config', self.dir / 'absent.json').returncode, 1)

    def test_commands_follow_the_installed_units_config(self):
        cfg = self.write(config(), 'elsewhere.json')
        unit = self.dir / 'home' / '.config' / 'systemd' / 'user' / 'recursant.service'
        unit.parent.mkdir(parents=True)
        unit.write_text('[Service]\nExecStart=/x/recursant serve --config %s\n' % cfg)
        report = json.loads(self.run_cli('status', '--user', '--json').stdout)
        self.assertEqual(report['config'], str(cfg))
        self.assertTrue(report['service']['installed'])
        self.assertIn('config      %s' % cfg, self.run_cli('check', '--user', '--no-secrets').stdout)
        explicit = self.write(config(), 'explicit.json')  # --config still wins
        self.assertEqual(json.loads(self.run_cli('status', '--user', '--json', '--config', explicit).stdout)['config'], str(explicit))

    # ---- serve + status ----
    def test_status_endpoint_counts_requests(self):
        class Sink(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                body = b'{"id":"x","object":"chat.completion","created":1,"model":"physical","choices":[]}'
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        sink = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Sink)
        threading.Thread(target=sink.serve_forever, daemon=True).start()
        port = free_port()
        path = self.write(config(port, sink.server_port))
        envfile = self.dir / 'recursant.env'
        envfile.write_text('RC_CLI_AUTH=cli-client-key\nRC_CLI_PUBLIC=cli-public-key\n')
        envfile.chmod(0o600)
        proc = subprocess.Popen([str(BIN), 'serve', '--config', str(path), '--test-mode'], env=self.env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            base = 'http://127.0.0.1:%d/v1' % port
            for _ in range(100):
                try:
                    urllib.request.urlopen('http://127.0.0.1:%d/healthz' % port, timeout=1).close(); break
                except OSError:
                    time.sleep(0.05)
            def call(url, data=None, key='cli-client-key'):
                req = urllib.request.Request(url, data=data, headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
                return urllib.request.urlopen(req, timeout=5)
            with self.assertRaises(urllib.error.HTTPError) as denied:
                call(base + '/status', key='wrong')
            self.assertEqual(denied.exception.code, 401)
            denied.exception.close()
            with call(base + '/chat/completions', json.dumps({'model': 'alias', 'messages': [{'role': 'user', 'content': 'hi'}]}).encode()) as ok:
                ok.read()
            with self.assertRaises(urllib.error.HTTPError) as rejected:
                call(base + '/chat/completions', json.dumps({'model': 'unknown', 'messages': []}).encode())
            rejected.exception.close()
            with call(base + '/status') as resp:
                status = json.loads(resp.read())
            self.assertEqual(status['requests'], {'total': 2, 'ok': 1, 'rejected': 1, 'upstream_errors': 0, 'private': 1, 'public': 0})
            self.assertEqual((status['providers'], status['aliases'], status['port']), (2, 1, port))
            cli = self.run_cli('status', '--config', path, '--json')
            self.assertEqual(cli.returncode, 0, cli.stderr)
            report = json.loads(cli.stdout)
            self.assertEqual(report['endpoint'], base)
            self.assertEqual(report['router']['requests']['total'], 2)
            self.assertFalse(report['service']['installed'])
            text = self.run_cli('status', '--config', path)
            self.assertIn('requests    2 total: 1 ok, 1 rejected', text.stdout)
        finally:
            proc.terminate()
            _, err = proc.communicate(timeout=10)
            sink.shutdown()
            sink.server_close()
        self.assertIn(b'listening on http://127.0.0.1:%d/v1' % port, err)
        down = self.run_cli('status', '--config', path)
        self.assertEqual(down.returncode, 3)
        self.assertIn('endpoint not reachable', down.stdout)


if __name__ == '__main__':
    unittest.main()
