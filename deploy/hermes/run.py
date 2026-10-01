"""Isolated wrapper around the pinned, unmodified upstream AIAgent API."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

SHA = 'fb6715455877e0298674c3a46a2faa87cd27295b'


def main():
    os.umask(0o077)
    source = '/opt/hermes'
    git = ['git', '-c', 'safe.directory=/opt/hermes', '-C', source]
    sha = subprocess.check_output([*git, 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output([*git, 'status', '--porcelain'], text=True)
    import resource
    resource.setrlimit(resource.RLIMIT_FSIZE, (16777216, 16777216))
    assert sha == SHA and not dirty, 'upstream source is not pristine'
    home = Path(os.environ['HERMES_HOME'])
    assert not home.exists(), 'profile must be fresh'
    home.mkdir(parents=True)
    Path(os.environ['HOME']).mkdir(parents=True)
    shutil.copytree('/opt/observer', home / 'plugins' / 'recursant-observer')
    # A new synthetic fixture, never an existing user profile.
    (home / 'config.yaml').write_text('plugins:\n  enabled: [recursant-observer]\n  stream_reasoning_deltas: true\n')
    sys.path.insert(0, source)
    from run_agent import AIAgent
    from agent.plugin_stream_hooks import shutdown_plugin_stream_hook_dispatcher
    agent = AIAgent(model=os.environ['BASELINE_MODEL'],
                    base_url=os.environ['BASELINE_URL'], api_key='local-only',
                    provider='custom', api_mode='chat_completions',
                    max_iterations=3, max_tokens=2048, run_budget_seconds=180,
                    quiet_mode=True)
    try:
        result = agent.run_conversation('Run the terminal tool with exactly this command: printf ROUTING_OK. Then reply only ROUTING_OK. Do not use any other tools.')
        shutdown_plugin_stream_hook_dispatcher(timeout=5)
        Path('/artifacts/result.json').write_text(json.dumps(result, default=str))
        Path('/artifacts/source.json').write_text(json.dumps({'sha': sha, 'pristine_before_run': True}))
    finally:
        agent.close()


if __name__ == '__main__':
    main()
