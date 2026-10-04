"""Shared plumbing for the seeded task packs (bench.longhorizon, bench.multiagent) and the
episode plan used by every runner. No inference, no Docker at import time.

A pack is a directory of task directories, each with TASK.md, seed/, hidden/ and an
optional reference/ (plus reference/DELETE listing seed files the reference removes).
The pack runners keep their own names (load_tasks, fingerprint, seeder, verifier, plan)
as thin wrappers so recorded-run drivers and tests keep importing them unchanged."""
import base64
import hashlib
import io
import random
import shutil
import tarfile
import tempfile
from pathlib import Path


def load_tasks(tasks_dir, names=None):
    """Tasks in a pack, sorted by directory name; names (optional) filters by id."""
    tasks = []
    for d in sorted(p for p in Path(tasks_dir).iterdir() if p.is_dir()):
        if names and d.name not in names: continue
        tasks.append(dict(id=d.name, dir=d, prompt=(d / 'TASK.md').read_text()))
    return tasks


def fingerprint(tasks_dir):
    """SHA-256 over every file of the pack (relative path and bytes), caches excluded."""
    tasks_dir = Path(tasks_dir)
    h = hashlib.sha256()
    for p in sorted(tasks_dir.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts:
            h.update(str(p.relative_to(tasks_dir)).encode() + b'\0' + p.read_bytes() + b'\0')
    return h.hexdigest()


def seeder(task):
    def seed(workspace: Path):
        shutil.copytree(task['dir'] / 'seed', workspace, dirs_exist_ok=True)
        (workspace / 'TASK.md').write_text(task['prompt'])
    return seed


def verifier(task):
    from bench.longhorizon.check import grade

    def verify(workspace: Path, out: Path):
        v = grade(task['dir'], workspace)
        (out / 'grader-output.private').write_text(v.pop('tail', '') or '')
        return v
    return verify


def reference_tarball(task, *, exclude_names=()):
    """(base64 tar.gz of seed+reference, files reference/DELETE removes) for scripted agents."""
    from bench.longhorizon.check import materialise
    with tempfile.TemporaryDirectory() as tmp:
        ref = materialise(task['dir'], Path(tmp) / 'r', True)
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as tf:
            for p in sorted(ref.rglob('*')):
                if p.is_file() and '__pycache__' not in p.parts and p.name not in exclude_names:
                    tf.add(p, arcname=str(p.relative_to(ref)))
        deletes = task['dir'] / 'reference' / 'DELETE'
        return base64.b64encode(buf.getvalue()).decode(), (deletes.read_text().split() if deletes.exists() else [])


def plan(tasks, arms, repeats, seed, *, with_repeat=False):
    """Repeat-major, task-major, arms shuffled per (task, repeat) with a seeded RNG.
    with_repeat adds the repeat index to every assignment (bench.multiagent rows)."""
    rng = random.Random(seed); out = []
    for r in range(repeats):
        for t in tasks:
            order = list(arms); rng.shuffle(order)
            for a in order:
                pair = f"{t['id']}-r{r}"
                row = dict(episode_id=f'{pair}-{a}', pair_id=pair, task_id=t['id'], arm=a)
                if with_repeat: row['repeat'] = r
                out.append(row)
    return out
