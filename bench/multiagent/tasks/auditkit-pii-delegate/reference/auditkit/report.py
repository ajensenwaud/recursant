from .chart import bar_chart
from .period import month_key, month_range
from .subscribers import load_subscribers


def signup_chart(path, width=20):
    counts = {}
    for rec in load_subscribers(path):
        key = month_key(rec["signup_date"])
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return []
    months = month_range(min(counts), max(counts))
    return bar_chart([(m, counts.get(m, 0)) for m in months], width)
