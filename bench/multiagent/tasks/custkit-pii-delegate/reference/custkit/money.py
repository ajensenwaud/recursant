def format_cents(cents):
    sign = "-" if cents < 0 else ""
    dollars, rest = divmod(abs(cents), 100)
    return "%s$%s.%02d" % (sign, format(dollars, ","), rest)


def split_evenly(total_cents, parts):
    if parts < 1:
        raise ValueError("parts must be >= 1")
    if total_cents < 0:
        raise ValueError("total_cents must be >= 0")
    base, extra = divmod(total_cents, parts)
    return [base + 1] * extra + [base] * (parts - extra)
