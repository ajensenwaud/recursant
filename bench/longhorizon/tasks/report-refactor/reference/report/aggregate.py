def _group(sales, key):
    acc = {}
    for s in sales:
        t = acc.setdefault(key(s), [0, 0])
        t[0] += s.units
        t[1] += s.units * s.unit_price_cents
    return [(k, u, c) for k, (u, c) in sorted(acc.items())]


def by_region(sales):
    return _group(sales, lambda s: s.region)


def by_product(sales):
    return _group(sales, lambda s: s.product)
