"""Check that the router's C features (core/src/context/efficiency.c) equal the Python
features the model was trained on (bench/efficiency/features.py), on every recorded request.

Build and dump in the dev container, then compare:
  docker run --rm --network none -v "$PWD:/work" -w /work recursant-v4-dev:local sh -c \\
    'cc -O1 -Icore/include bench/efficiency/features_dump.c core/src/context/efficiency.c -ljansson -lm -o /tmp/fd && \\
     cd .hermes/runtime/m3-live && /tmp/fd */*/traces.private.json' > .hermes/runtime/m3-live/features-c.jsonl
  python3 -m bench.efficiency.parity
usage: python3 -m bench.efficiency.parity [DUMP]"""
import json, sys
from bench.efficiency.features import LIVE, features
from bench.efficiency.features import KEYS


def main():
    dump = sys.argv[1] if sys.argv[1:] else str(LIVE / 'features-c.jsonl')
    cache, n, bad, worst = {}, 0, 0, 0.0
    for line in open(dump):
        row = json.loads(line)
        if row['file'] not in cache: cache[row['file']] = json.load(open(LIVE / row['file']))
        req = cache[row['file']][row['index']].get('request')
        if isinstance(req, str): req = json.loads(req)
        if not isinstance(req, dict) or not isinstance(req.get('messages'), list):
            if row['x'] is not None: bad += 1
            continue
        py = features(req); n += 1
        diff = max(abs(py[k] - c) for k, c in zip(KEYS, row['x']))
        worst = max(worst, diff)
        if diff > 1e-9:
            bad += 1
            if bad <= 5: print('mismatch', row['file'], row['index'], {k: (py[k], c) for k, c in zip(KEYS, row['x']) if abs(py[k] - c) > 1e-9})
    print('%d requests compared, %d mismatches, largest difference %.3g' % (n, bad, worst))
    return bad


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
