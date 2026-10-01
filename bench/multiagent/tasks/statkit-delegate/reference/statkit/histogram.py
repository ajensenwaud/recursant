def histogram(values, lo, hi, bins):
    if bins < 1:
        raise ValueError("bins must be >= 1")
    if hi <= lo:
        raise ValueError("hi must be greater than lo")
    counts = [0] * bins
    for v in values:
        if v < lo or v > hi:
            continue
        i = int((v - lo) / (hi - lo) * bins)
        counts[min(i, bins - 1)] += 1
    return counts
