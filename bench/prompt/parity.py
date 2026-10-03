"""Check that the router's C classifier scores exactly what bench/prompt/features.py scores,
over every single-query question plus adversarial texts (Unicode, long tokens, code,
>64 KiB). Builds bench/prompt/score_dump.c in the dev container.
usage: python3 -m bench.prompt.parity WEIGHTS.json"""
import json, subprocess, sys, tempfile
from pathlib import Path
from bench.prompt.features import score

ROOT = Path(__file__).resolve().parents[2]


def main():
    model = json.load(open(sys.argv[1]))
    section = {**model, 'simple_min': 0.8}
    texts = [json.loads(l)['question'] for l in open(ROOT / '.hermes/runtime/prompt/single.jsonl')]
    texts += ['', '?', 'Café naïve résumé — 東京 は?', 'a' * 40 + ' the', 'x = f(y) / 3_a; {b[0]}',
              'word ' * 20000, 'MiXeD CaSe Tokens ARE folded', '\n\n\n', 'tab\tsep\rcr', '日本語のみ']
    with tempfile.TemporaryDirectory() as d:
        Path(d, 'cfg.json').write_text(json.dumps(section))
        Path(d, 'texts.jsonl').write_text(''.join(json.dumps({'text': t}) + '\n' for t in texts))
        out = subprocess.run(['docker', 'run', '--rm', '--network', 'none', '-v', '%s:/src:ro' % ROOT, '-v', '%s:/d' % d,
                              'recursant-v4-dev:local', 'sh', '-c',
                              'cc -O2 -Wall -Werror -I/src/core/include /src/bench/prompt/score_dump.c /src/core/src/context/prompt.c '
                              '-o /tmp/sd -ljansson -lm && /tmp/sd /d/cfg.json /d/texts.jsonl'],
                             capture_output=True, text=True, check=True).stdout.split()
    worst = 0.0
    for t, c in zip(texts, out):
        worst = max(worst, abs(float(c) - score(model, t)))
    print('%d texts, max |C - Python| = %.2e' % (len(texts), worst))
    sys.exit(0 if len(out) == len(texts) and worst < 1e-9 else 1)


if __name__ == '__main__':
    main()
