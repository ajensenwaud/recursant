"""Lead-time analysis: for every model request after the first, how long before it did each
observable signal arrive? Reads trace/events.jsonl from runner episode dirs.

Usage: python3 -m bench.longhorizon.leadtime DIR [DIR ...]
"""
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

SIGNALS = ('on_stream_start', 'on_stream_end', 'pre_tool_call', 'post_tool_call',
           'subagent_start', 'subagent_stop', 'post_auxiliary_call')


def episode_leads(events):
    """For each pre_api_request (after the first), lead = request_ns - most recent signal_ns of each kind
    since the previous request."""
    leads = defaultdict(list)
    tool_time = []
    last_req = None
    pending = {}
    pre_tool = {}
    for e in events:
        ev, ns = e.get('event'), e.get('received_ns')
        if ns is None:
            continue
        if ev == 'pre_api_request':
            if last_req is not None:
                for k, t in pending.items():
                    leads[k].append((ns - t) / 1e9)
            pending = {}
            last_req = ns
        elif ev in SIGNALS:
            # keep the FIRST occurrence of each kind within the turn: earliest possible arrival
            pending.setdefault(ev, ns)
            tid = (e.get('payload') or {}).get('tool_call_id')
            if ev == 'pre_tool_call' and tid:
                pre_tool[tid] = ns
            if ev == 'post_tool_call' and tid in pre_tool:
                tool_time.append((ns - pre_tool.pop(tid)) / 1e9)
    return leads, tool_time


def q(v):
    if not v:
        return 'n=0'
    v = sorted(v)
    return 'n=%-4d median %7.2fs  p10 %7.2fs  p90 %7.2fs  max %7.2fs' % (
        len(v), statistics.median(v), v[len(v) // 10], v[min(len(v) - 1, 9 * len(v) // 10)], v[-1])


def main(dirs):
    allv, tools, turns = defaultdict(list), [], []
    per_task = {}
    for d in dirs:
        for f in sorted(Path(d).glob('*/trace/events.jsonl')):
            evs = []
            for line in f.read_text().splitlines():
                try:
                    evs.append(json.loads(line))
                except ValueError:
                    pass
            leads, tt = episode_leads(evs)
            for k, v in leads.items():
                allv[k] += v
            tools += tt
            n = sum(1 for e in evs if e.get('event') == 'pre_api_request')
            turns.append(n)
            per_task[f.parent.parent.name] = dict(turns=n, tool_s=round(sum(tt), 1),
                                                  subagents=sum(1 for e in evs if e.get('event') == 'subagent_start'))
    print('episodes', len(turns), 'turns/episode', turns)
    print('tool execution time (pre_tool_call -> post_tool_call):', q(tools))
    print('lead time before the NEXT model request, by first signal of each kind in the turn:')
    for k in SIGNALS:
        print('  %-20s %s' % (k, q(allv[k])))
    for k, v in per_task.items():
        print('  ', k, v)


if __name__ == '__main__':
    main(sys.argv[1:])
