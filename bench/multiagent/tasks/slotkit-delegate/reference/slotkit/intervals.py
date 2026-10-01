def merge(intervals):
    pairs = []
    for start, end in intervals:
        if not start < end:
            raise ValueError("interval needs start < end: %r" % ((start, end),))
        pairs.append((start, end))
    pairs.sort()
    out = []
    for start, end in pairs:
        if out and start <= out[-1][1]:
            if end > out[-1][1]:
                out[-1] = (out[-1][0], end)
        else:
            out.append((start, end))
    return out
