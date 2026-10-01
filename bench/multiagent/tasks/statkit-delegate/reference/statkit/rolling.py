def rolling_mean(values, window):
    if window < 1:
        raise ValueError("window must be >= 1")
    out = []
    for i in range(len(values)):
        chunk = values[max(0, i - window + 1): i + 1]
        out.append(float(sum(chunk) / len(chunk)))
    return out
