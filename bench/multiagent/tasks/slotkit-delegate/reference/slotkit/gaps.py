def free_slots(busy, start, end, min_len=1):
    if start >= end:
        raise ValueError("window needs start < end")
    if min_len < 1:
        raise ValueError("min_len must be >= 1")
    out = []
    cursor = start
    for b_start, b_end in busy:
        if b_end <= cursor:
            continue
        if b_start >= end:
            break
        if b_start - cursor >= min_len:
            out.append((cursor, b_start))
        cursor = max(cursor, b_end)
        if cursor >= end:
            break
    if cursor < end and end - cursor >= min_len:
        out.append((cursor, end))
    return out
