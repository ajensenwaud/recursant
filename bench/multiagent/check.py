"""Check the multi-agent (delegation) task pack offline: for every task under
bench/multiagent/tasks, the seed alone must FAIL the hidden tests and seed+reference
must PASS them. Grading and materialisation are shared with bench.longhorizon.check
(pinned Hermes image, network none).

Run from the repository root:  python3 -m bench.multiagent.check [task ...]"""
import sys
from pathlib import Path

from bench.longhorizon.check import check_pack

HERE = Path(__file__).resolve().parent


if __name__ == '__main__':
    sys.exit(0 if check_pack(HERE / 'tasks', sys.argv[1:]) else 1)
