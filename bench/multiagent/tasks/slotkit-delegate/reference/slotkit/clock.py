import re

_HHMM = re.compile(r"([0-9]{2}):([0-9]{2})")


def to_minutes(text):
    m = _HHMM.fullmatch(text) if isinstance(text, str) else None
    if not m:
        raise ValueError("expected HH:MM, got %r" % (text,))
    hours, minutes = int(m.group(1)), int(m.group(2))
    if hours == 24 and minutes == 0:
        return 1440
    if hours > 23 or minutes > 59:
        raise ValueError("time out of range: %r" % (text,))
    return hours * 60 + minutes


def to_hhmm(minutes):
    if not 0 <= minutes <= 1440:
        raise ValueError("minutes out of range: %r" % (minutes,))
    return "%02d:%02d" % divmod(minutes, 60)
