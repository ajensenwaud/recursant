"""Held-out synthetic personal data, written before the false-alarm filters and the address
rules, and never used to design them (they are designed on bench/privacy/build.py). Different
names, different address shapes and different surrounding text, so a detector tuned on the
first set is not scored on its own templates.

Only names, street addresses and dates of birth, because those are what the rules cannot
see; identifiers with check digits are covered by the first set. Also hard negatives: text
that mentions tech products, places or code identifiers that look like names but is not
personal data.
Output: .hermes/runtime/privacy/synth-holdout.jsonl (never committed).
usage: python3 -m bench.privacy.holdout_synth"""
import json, random
from bench.privacy.build import ROOT

OUT = ROOT / '.hermes/runtime/privacy/synth-holdout.jsonl'
FIRST = ['Hannah', 'Oscar', 'Zoe', 'Archie', 'Ruby', 'Hamish', 'Ananya', 'Jun', 'Leilani', 'Dmitri',
         'Grace', 'Tariq', 'Bronwyn', 'Callum', 'Yuki', 'Esther', 'Rhys', 'Sofia', 'Darcy', 'Kiri']
LAST = ['Fitzgerald', 'Huang', 'Okafor', 'Delaney', 'Sharma', 'Lindqvist', 'Costa', 'McKenzie', 'Hassan',
        'Bauer', 'Pham', 'Reid', 'Gallagher', 'Ivanova', 'Walsh', 'Kim', 'Ferreira', 'Doyle', 'Moreau', 'Stewart']
ADDRESS = [
    lambda r: 'Unit %d/%d %s Ave, %s' % (r.randrange(1, 40), r.randrange(1, 200), r.choice(['Harbour', 'Wattle', 'Victoria', 'Ocean']), r.choice(['Paddington NSW 2021', 'Bondi Beach NSW 2026', 'St Kilda VIC 3182'])),
    lambda r: 'Level %d, %d %s Place, Sydney' % (r.randrange(2, 30), r.randrange(1, 60), r.choice(['Martin', 'Chifley', 'Australia'])),
    lambda r: '%d %s Road, %s' % (r.randrange(1, 900), r.choice(['Old Northern', 'Mount Dandenong Tourist', 'Princes', 'Great Western']), r.choice(['Castle Hill', 'Olinda', 'Katoomba'])),
    lambda r: '%d %s Crescent %s %s' % (r.randrange(1, 90), r.choice(['Wattle', 'Banksia', 'Jacaranda']), r.choice(['Toowong', 'Subiaco', 'Glenelg']), r.choice(['QLD 4066', 'WA 6008', 'SA 5045'])),
    lambda r: '%d %s lane, %s' % (r.randrange(1, 70), r.choice(['wombat', 'kookaburra', 'river']), r.choice(['daylesford vic 3460', 'byron bay nsw 2481'])),
    lambda r: '%d %s Court, Palmerston North 4410, New Zealand' % (r.randrange(1, 50), r.choice(['Totara', 'Rimu'])),
]
TEMPLATES = [
    ('{"customer": {"first": "{f}", "last": "{l}"}, "plan": "gold", "renewal": "2027-01-01"}', ['name']),
    ('Author: {f} {l}\nDate:   Tue Sep 30 10:02:11 2026 +1000\n\n    fix rounding in invoice totals', ['name']),
    ('Thanks,\n{f} {l}\nSenior Analyst, Claims', ['name']),
    ('Spoke to {f} {l} this morning; she wants the refund processed by Friday.', ['name']),
    ('patient_name,ward,admitted\n{l} {f},4B,2026-09-28\n', ['name']),
    ('assigned_to: {f} {l}\nstatus: open\npriority: P2', ['name']),
    ('Hi {f}, your parcel is on its way.', ['name']),
    ('Deliver to: {addr}', ['address']),
    ('{"shipping_address": "{addr}", "items": 3}', ['address']),
    ('Residential address\n{addr}', ['address']),
    ('{f} {l} moved to {addr} last month.', ['name', 'address']),
    ('name={f} {l} dob={d} suburb=Newtown', ['name', 'dob']),
    ('Born on {d2}, {f} {l} joined the scheme in 2019.', ['name', 'dob']),
]
NEGATIVE = [
    'Run `pytest -k test_parse_address` and fix the failing case in AddressParser.',
    'class CustomerRecord:\n    first_name: str\n    last_name: str\n    street: str\n',
    'Deploying to Amazon Web Services region ap-southeast-2 (Sydney).',
    'The Apache Kafka consumer lags behind; restart the Spring Boot service.',
    'git checkout -b feature/jack-parser && git push origin HEAD',
    'Visited Melbourne and Hobart for the conference; slides are in /docs/talks/2026.',
    'Using Jest with React Testing Library; Sinon for stubs.',
    'SELECT first_name, last_name FROM users WHERE id = $1;',
    'error: Mia.Logging.Handler failed to flush (see logs/2026-10-02/mia-handler.log)',
    'Victoria Street station closed; use Elizabeth Line instead.',
    'Set HUGO_ENV=production and run `make docs` for Charlotte theme.',
    '{"street_type_codes": ["St", "Rd", "Ave", "Cres", "Pde"], "states": ["NSW", "VIC", "QLD"]}',
    'Ran 14 tests in 0.212s\n\nOK\nwrote 1,204 bytes to /workspace/out/report_2026_10_02.md',
    'Kubernetes pod web-7f9c8d-xk2lp restarted 3 times (OOMKilled).',
    'See Martin Fowler, Refactoring (2nd ed.), chapter 6.',
]


def main():
    r = random.Random(20261003)
    items = []
    for _ in range(20):
        for t, kinds in TEMPLATES:
            f, l = r.choice(FIRST), r.choice(LAST)
            d = '%d %s %d' % (r.randrange(1, 29), r.choice(['March', 'July', 'November']), r.randrange(1945, 2004))
            text = t.replace('{f}', f).replace('{l}', l).replace('{addr}', r.choice(ADDRESS)(r)).replace(
                '{d}', '%d-%02d-%02d' % (r.randrange(1945, 2004), r.randrange(1, 13), r.randrange(1, 29))).replace('{d2}', d)
            items.append({'source': 'synth-holdout', 'text': text, 'kinds': kinds})
    for t in NEGATIVE:
        items.append({'source': 'decoy-holdout', 'text': t, 'kinds': []})
    with open(OUT, 'w') as fh:
        for i, it in enumerate(items): fh.write(json.dumps(dict(id=i, **it)) + '\n')
    print(len(items), 'items ->', OUT)


if __name__ == '__main__':
    main()
