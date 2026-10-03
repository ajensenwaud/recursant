"""Deterministic street-address recognisers (Australian shapes). Designed on the test set from
bench/privacy/build.py only; scored on bench/privacy/holdout_synth.py and
bench/privacy/holdout.py without changes (see docs/evidence/m2-privacy-pipeline.md)."""
import re

STATES = r'(?:NSW|VIC|QLD|WA|SA|TAS|NT|ACT)'
STREET_TYPES = (r'(?:St|Street|Rd|Road|Ave|Avenue|Pde|Parade|Hwy|Highway|Cres|Crescent|Pl|Place|Ln|Lane|Ct|Court|'
                r'Dr|Drive|Tce|Terrace|Blvd|Boulevard|Cl|Close|Gr|Grove|Sq|Square|Esp|Esplanade)')
# "12 George St", "7/41 Harbour Ave", "Unit 3/14 King William Rd": a number, one to three words, a street type.
STREET = re.compile(r'(?<![\w/.])(?:(?:Unit|Apt|Shop|Suite)\s+)?\d{1,5}[A-Za-z]?(?:/\d{1,5}[A-Za-z]?)?\s+'
                    r'(?:[A-Za-z][a-z\']+\s+){1,3}' + STREET_TYPES + r'\b\.?(?![\w(])')
# "Paddington NSW 2021": a word, a state, a four-digit postcode.
STATE_POSTCODE = re.compile(r'\b[A-Za-z][a-z]+,?\s+' + STATES + r',?\s+\d{4}\b')


def addresses(text):
    return bool(STREET.search(text) or STATE_POSTCODE.search(text))
