import datetime
import re

_MON = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}


def parse_date(text):
    t = text.strip()
    for pat, order in ((r"(\d{4})-(\d{2})-(\d{2})", "ymd"), (r"(\d{2})/(\d{2})/(\d{4})", "dmy")):
        m = re.fullmatch(pat, t)
        if m:
            parts = dict(zip(order, map(int, m.groups())))
            return datetime.date(parts["y"], parts["m"], parts["d"])
    m = re.fullmatch(r"(\d{1,2}) ([A-Za-z]{3}) (\d{4})", t)
    if m and m.group(2).lower() in _MON:
        return datetime.date(int(m.group(3)), _MON[m.group(2).lower()], int(m.group(1)))
    m = re.fullmatch(r"([A-Za-z]{3}) (\d{1,2}), (\d{4})", t)
    if m and m.group(1).lower() in _MON:
        return datetime.date(int(m.group(3)), _MON[m.group(1).lower()], int(m.group(2)))
    raise ValueError(text)
