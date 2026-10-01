"""Check a long-horizon task pack offline: seed must FAIL hidden tests, seed+reference
must PASS them, and the task's own visible tests must pass on the reference.
Runs in the pinned Hermes image (network none), same as the live grader."""
import json, shutil, subprocess, sys, tempfile, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
IMAGE = 'sha256:7c6c6417032db7457460dd9d9bdf128ff004f4fec6bb66bc9f5eab5f48fead53'


def grade(task_dir: Path, workspace: Path, timeout=300):
    """Copy hidden tests next to the candidate workspace (never visible to the agent) and run them."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        shutil.copytree(workspace, tmp / 'w', ignore=shutil.ignore_patterns('.git', '__pycache__'))
        shutil.copytree(task_dir / 'hidden', tmp / 'w' / '_hidden')
        (tmp / 'w' / '_hidden' / '__init__.py').touch()
        name = 'lh-grade-' + uuid.uuid4().hex[:10]
        cmd = ['docker', 'run', '--rm', '--pull=never', '--name', name, '--network=none', '--cap-drop=ALL',
               '--security-opt=no-new-privileges', '--memory=2g', '--cpus=2', '--pids-limit=256',
               '--user', '%d:%d' % (__import__('os').getuid(), __import__('os').getgid()),
               '--mount', f'type=bind,src={tmp / "w"},dst=/w', '-w', '/w', '-e', 'PYTHONDONTWRITEBYTECODE=1',
               '--entrypoint', 'python', IMAGE, '-m', 'unittest', 'discover', '-s', '_hidden', '-t', '.', '-v']
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
            return dict(success=False, passed=0, total=None, failure='timeout')
        out = p.stderr
        import re
        ran = re.search(r'Ran (\d+) test', out)
        total = int(ran.group(1)) if ran else 0
        bad = len(re.findall(r'\.\.\. (FAIL|ERROR)', out)) + len(re.findall(r'^(FAIL|ERROR): ', out, re.M))
        bad = min(bad, total) if total else bad
        return dict(success=p.returncode == 0 and total > 0, passed=max(0, total - len(set(re.findall(r'^(?:FAIL|ERROR): (\S+)', out, re.M)))), total=total,
                    exit_code=p.returncode, tail=out[-600:])


def materialise(task_dir: Path, dest: Path, with_reference: bool):
    shutil.copytree(task_dir / 'seed', dest)
    if with_reference and (task_dir / 'reference').exists():
        shutil.copytree(task_dir / 'reference', dest, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('DELETE'))
        rm = task_dir / 'reference' / 'DELETE'
        for rel in (rm.read_text().split() if rm.exists() else []):
            (dest / rel).unlink()
    return dest


if __name__ == '__main__':
    names = sys.argv[1:] or sorted(p.name for p in (HERE / 'tasks').iterdir() if p.is_dir())
    ok = True
    for n in names:
        t = HERE / 'tasks' / n
        with tempfile.TemporaryDirectory() as tmp:
            seed = grade(t, materialise(t, Path(tmp) / 's', False))
            ref = grade(t, materialise(t, Path(tmp) / 'r', True))
        good = (not seed['success']) and ref['success']
        ok &= good
        print(f"{n:22} seed {seed['passed']}/{seed['total']} {'FAIL' if not seed['success'] else 'PASS(!)'}  "
              f"reference {ref['passed']}/{ref['total']} {'PASS' if ref['success'] else 'FAIL(!)'}  {'OK' if good else 'BROKEN'}")
        if not ref['success']: print(ref.get('tail'))
    sys.exit(0 if ok else 1)
