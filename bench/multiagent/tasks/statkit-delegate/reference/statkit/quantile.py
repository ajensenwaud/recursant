import math


def percentile(values, p):
    data = sorted(values)
    if not data:
        raise ValueError("values must not be empty")
    if not 0 <= p <= 100:
        raise ValueError("p must be between 0 and 100")
    r = (len(data) - 1) * p / 100
    lo, hi = math.floor(r), math.ceil(r)
    return float(data[lo] + (data[hi] - data[lo]) * (r - lo))
