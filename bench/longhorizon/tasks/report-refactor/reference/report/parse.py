from dataclasses import dataclass


@dataclass(frozen=True)
class Sale:
    region: str
    product: str
    units: int
    unit_price_cents: int


def _price(text):
    dollars, _, cents = text.partition(".")
    if not dollars.isdigit() or (cents and (not cents.isdigit() or len(cents) > 2)):
        raise ValueError(text)
    return int(dollars) * 100 + int((cents + "00")[:2])


def parse(text):
    """Return (sales, skipped)."""
    sales, skipped = [], 0
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 4:
            skipped += 1
            continue
        try:
            units = int(parts[2])
            price = _price(parts[3])
        except ValueError:
            skipped += 1
            continue
        sales.append(Sale(parts[0], parts[1], units, price))
    return sales, skipped
