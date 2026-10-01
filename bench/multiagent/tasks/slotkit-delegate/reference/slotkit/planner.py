from .clock import to_hhmm, to_minutes
from .gaps import free_slots
from .intervals import merge


def find_free(busy, day_start="09:00", day_end="17:00", min_minutes=30):
    merged = merge([(to_minutes(a), to_minutes(b)) for a, b in busy])
    slots = free_slots(merged, to_minutes(day_start), to_minutes(day_end), min_minutes)
    return ["%s-%s" % (to_hhmm(a), to_hhmm(b)) for a, b in slots]
