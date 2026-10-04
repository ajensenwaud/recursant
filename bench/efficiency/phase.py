"""Phase rule check on the 1,339 counterfactual pairs: does agreement between the cheap model and
gpt-4.1 depend on the agent's phase (last tool called, last result ok/failed, what gpt-4.1 did next)?
Zero spend. usage: python3 -m bench.efficiency.phase"""
from collections import defaultdict
from bench.efficiency.features import pairs, TOOLS

def phase(f):
    last = next((t for t in TOOLS if f['last_call_' + t]), 'none')
    if f['no_tools_offered']: return 'final-answer'
    if f['last_failed']: return 'after-failure'
    if last == 'none': return 'first-step'
    if last in ('read_file', 'search_files'): return 'exploring'
    if last in ('write_file', 'patch'): return 'after-write'
    if last == 'terminal': return 'after-command'
    if last == 'delegate_task': return 'after-delegate'
    return last

def table(rows, key, title):
    by = defaultdict(lambda: [0, 0, 0])
    for f, y, g, m in rows:
        k = key(f, m); by[k][0] += 1; by[k][1] += y; by[k][2] += m['same_target']
    print('\n%s' % title)
    print('  %-16s %5s %9s %12s' % ('', 'n', 'same move', 'same target'))
    for k, (n, a, t) in sorted(by.items(), key=lambda kv: -kv[1][0]):
        print('  %-16s %5d %8.0f%% %11.0f%%' % (k, n, 100 * a / n, 100 * t / n))

ps = pairs()
mini = [p for p in ps if p[3]['model'] == 'mini']; glm = [p for p in ps if p[3]['model'] == 'glm']
print('%d pairs (%d gpt-4.1-mini, %d GLM); overall same move %.0f%%' % (len(ps), len(mini), len(glm), 100 * sum(p[1] for p in ps) / len(ps)))
table(mini, lambda f, m: phase(f), 'gpt-4.1-mini vs gpt-4.1 by phase (what the agent just did)')
table(mini, lambda f, m: (m['big'] or ['text'])[0], 'gpt-4.1-mini vs gpt-4.1 by what gpt-4.1 did NEXT (the expensive step?)')
table(mini, lambda f, m: phase(f) + ' -> ' + (m['big'] or ['text'])[0], 'phase -> next move (n >= 20 shown)')
table(glm, lambda f, m: phase(f), 'GLM vs gpt-4.1 by phase')
