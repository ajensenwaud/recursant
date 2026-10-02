"""Deterministic detectors: what the router does today, and proposed Australian identifier
validators (check digits, or a nearby keyword for formats without one)."""
import re
from bench.privacy import ids
from bench.privacy.build import EMAIL

SEP = r'[ -]?'
# No letter or digit on either side: digits inside hashes, UUIDs and identifiers don't count.
L, R = r'(?<![0-9A-Za-z])', r'(?![0-9A-Za-z])'
CARD_SHAPES = ((r'4', 16), (r'5[1-5]', 16), (r'2[2-7]', 16), (r'3[47]', 15), (r'6(?:011|5)', 16))


def card_valid(d):
    """Luhn plus a real card shape (Visa/Mastercard/Discover 16 digits, Amex 15)."""
    return ids.luhn_valid(d) and any(re.match(p, d) and len(d) == n for p, n in CARD_SHAPES)


DIGITS = {
    'tfn': (re.compile(L + r'\d{3}%s\d{3}%s\d{3}' % (SEP, SEP) + R), ids.tfn_valid),
    'medicare': (re.compile(L + r'[2-6]\d{3}%s\d{5}%s\d(?:%s\d)?' % (SEP, SEP, SEP) + R), ids.medicare_valid),
    'abn': (re.compile(L + r'\d{2}%s\d{3}%s\d{3}%s\d{3}' % (SEP, SEP, SEP) + R), ids.abn_valid),
    'card': (re.compile(L + r'(?:\d[ -]?){14,15}\d' + R), card_valid),
}
PHONE = re.compile(r'(?<![\d+])(?:\+61[ -]?4\d{2}|04\d{2})[ -]?\d{3}[ -]?\d{3}(?!\d)|\(0[2378]\)[ -]?\d{4}[ -]?\d{4}(?!\d)')
BANK = re.compile(r'\bBSB\b[^\n]{0,12}?\d{3}[ -]?\d{3}', re.I)
NEAR = {   # formats without a check digit: only with a keyword close by
    'passport': re.compile(r'passport[^\n]{0,30}?\b[A-Z]\d{7}\b', re.I),
    'licence': re.compile(r'licen[cs]e[^\n]{0,30}?\b\d{6,10}\b', re.I),
    'dob': re.compile(r'(?:\bDOB\b|date of birth|\bborn\b)[^\n]{0,20}?\b\d{1,2}[/.-]\d{1,2}[/.-](?:19|20)\d{2}\b', re.I),
}


def today(text):
    """The router's built-in rule (email only)."""
    return {'email'} if EMAIL.search(text) else set()


def rules(text):
    found = today(text)
    for kind, (pattern, valid) in DIGITS.items():
        if any(valid(re.sub(r'\D', '', m.group())) for m in pattern.finditer(text)): found.add(kind)
    if PHONE.search(text): found.add('phone')
    if BANK.search(text): found.add('bank')
    for kind, pattern in NEAR.items():
        if pattern.search(text): found.add(kind)
    return found
