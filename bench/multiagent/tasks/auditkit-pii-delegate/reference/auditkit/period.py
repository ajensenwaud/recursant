import datetime
import re

_DATE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")
_KEY = re.compile(r"([0-9]{4})-([0-9]{2})")


def month_key(date_text):
    m = _DATE.fullmatch(date_text)
    if not m:
        raise ValueError("expected YYYY-MM-DD, got %r" % (date_text,))
    datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))  # ValueError if not a real date
    return date_text[:7]


def _parse_key(key):
    m = _KEY.fullmatch(key)
    if not m or not 1 <= int(m.group(2)) <= 12:
        raise ValueError("expected YYYY-MM, got %r" % (key,))
    return int(m.group(1)) * 12 + int(m.group(2)) - 1


def month_range(first, last):
    a, b = _parse_key(first), _parse_key(last)
    if a > b:
        raise ValueError("first month is after last month")
    return ["%04d-%02d" % (n // 12, n % 12 + 1) for n in range(a, b + 1)]
