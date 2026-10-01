from .histogram import histogram
from .quantile import percentile
from .rolling import rolling_mean


def summarise(values, bins=4, window=3):
    values = list(values)
    if not values:
        raise ValueError("values must not be empty")
    lo, hi = min(values), max(values)
    if lo == hi:
        hist = [len(values)] + [0] * (bins - 1)
    else:
        hist = histogram(values, lo, hi, bins)
    return {
        "count": len(values),
        "min": lo,
        "max": hi,
        "median": percentile(values, 50),
        "iqr": percentile(values, 75) - percentile(values, 25),
        "histogram": hist,
        "smoothed": rolling_mean(values, window),
    }
