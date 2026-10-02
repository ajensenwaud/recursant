"""Australian identifier generators and validators (check digits).

Sources for the algorithms: ATO TFN check (weights 1,4,3,7,5,8,6,9,10, mod 11), Services
Australia Medicare check digit (weights 1,3,7,9,1,3,7,9 on the first 8 digits, mod 10),
ABR ABN check (subtract 1 from the first digit, weights 10,1,3,...,19, mod 89), Luhn for
payment cards."""
import random

TFN_W = (1, 4, 3, 7, 5, 8, 6, 9, 10)
MEDICARE_W = (1, 3, 7, 9, 1, 3, 7, 9)
ABN_W = (10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19)


def tfn_valid(d):
    return len(d) == 9 and d.isdigit() and sum(int(c) * w for c, w in zip(d, TFN_W)) % 11 == 0


def medicare_valid(d):
    # 10 digits (8 + check + issue number) or 11 (+ individual reference number)
    if len(d) not in (10, 11) or not d.isdigit() or d[0] not in '23456' or d[9] == '0':
        return False
    return sum(int(c) * w for c, w in zip(d[:8], MEDICARE_W)) % 10 == int(d[8])


def abn_valid(d):
    if len(d) != 11 or not d.isdigit() or d[0] == '0':
        return False
    digits = [int(d[0]) - 1] + [int(c) for c in d[1:]]
    return sum(x * w for x, w in zip(digits, ABN_W)) % 89 == 0


def luhn_valid(d):
    if not (13 <= len(d) <= 19) or not d.isdigit():
        return False
    total = 0
    for i, c in enumerate(reversed(d)):
        n = int(c) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


def tfn(rng):
    while True:
        d = ''.join(rng.choice('0123456789') for _ in range(9))
        if d[0] != '0' and tfn_valid(d):
            return d


def medicare(rng):
    while True:
        d = rng.choice('23456') + ''.join(rng.choice('0123456789') for _ in range(7))
        d += str(sum(int(c) * w for c, w in zip(d, MEDICARE_W)) % 10) + rng.choice('123456789')
        if medicare_valid(d):
            return d


def abn(rng):
    while True:
        d = rng.choice('123456789') + ''.join(rng.choice('0123456789') for _ in range(10))
        if abn_valid(d):
            return d


def card(rng):
    prefix = rng.choice(['4', '51', '52', '53', '37'])
    length = 15 if prefix == '37' else 16
    while True:
        d = prefix + ''.join(rng.choice('0123456789') for _ in range(length - len(prefix)))
        if luhn_valid(d):
            return d


def invalid_like(rng, valid, length):
    """A digit string of the same length that fails the check (a decoy)."""
    while True:
        d = rng.choice('123456789') + ''.join(rng.choice('0123456789') for _ in range(length - 1))
        if not valid(d):
            return d
