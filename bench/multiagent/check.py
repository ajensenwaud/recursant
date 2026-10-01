"""Check the multi-agent (delegation) task pack offline: for every task under
bench/multiagent/tasks, the seed alone must FAIL the hidden tests and seed+reference
must PASS them. Grading and materialisation are shared with bench.longhorizon.check
(pinned Hermes image, network none).

Run from the repository root:  python3 -m bench.multiagent.check [task ...]"""
import sys, tempfile
from pathlib import Path

from bench.longhorizon.check import grade, materialise

HERE = Path(__file__).resolve().parent


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
