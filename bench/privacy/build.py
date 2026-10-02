"""Build the privacy test set (positives with labelled kinds, negatives from real agent
traffic). Output stays local: .hermes/runtime/privacy/testset.jsonl.

Each item: {"id", "source", "text", "kinds": [...]}; empty kinds = no personal data.
Kinds: email, phone, tfn, medicare, abn, card, bank, name, address, dob, passport, licence.
usage: python3 -m bench.privacy.build"""
import glob, json, random, re
from pathlib import Path
from bench.privacy import ids

ROOT = Path(__file__).resolve().parents[2]
EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")   # the router's built-in rule
OUT = ROOT / '.hermes/runtime/privacy/testset.jsonl'
LIVE = ROOT / '.hermes/runtime/m3-live'
FIRST = ['Olivia', 'Jack', 'Charlotte', 'Liam', 'Amelia', 'Noah', 'Isla', 'William', 'Mia', 'Thomas',
         'Priya', 'Wei', 'Aroha', 'Mohammed', 'Siobhan', 'Nguyen', 'Kaito', 'Fatima', 'Lachlan', 'Matilda']
LAST = ['Smith', 'Nguyen', 'Williams', 'Brown', 'Wilson', 'Taylor', 'Anderson', 'Patel', 'Chen', "O'Brien",
        'Kowalski', 'Tran', 'MacDonald', 'Singh', 'Papadopoulos', 'Murphy', 'Lee', 'Martin', 'Kelly', 'Rossi']
STREETS = ['George St', 'Collins Street', 'Elizabeth St', 'Queen Street', 'Bourke St', 'Hay Street',
           'King William Rd', 'Smith Street', 'Anzac Parade', 'Pacific Hwy']
SUBURBS = [('Sydney', 'NSW', '2000'), ('Melbourne', 'VIC', '3000'), ('Brisbane City', 'QLD', '4000'),
           ('Perth', 'WA', '6000'), ('Adelaide', 'SA', '5000'), ('Parramatta', 'NSW', '2150'),
           ('Fitzroy', 'VIC', '3065'), ('Hobart', 'TAS', '7000'), ('Darwin City', 'NT', '0800'), ('Braddon', 'ACT', '2612')]


def spaced(d, groups):
    out, i = [], 0
    for g in groups: out.append(d[i:i + g]); i += g
    return ' '.join(out)


def person(r):
    f, l = r.choice(FIRST), r.choice(LAST)
    sub, st, pc = r.choice(SUBURBS)
    n3 = lambda: r.randrange(1000)
    phone = r.choice(['04%02d %03d %03d' % (r.randrange(100), n3(), n3()),
                      '+61 4%02d %03d %03d' % (r.randrange(100), n3(), n3()),
                      '(02) %04d %04d' % (r.randrange(10000), r.randrange(10000))])
    tfn, medicare, card = ids.tfn(r), ids.medicare(r), ids.card(r)
    return {
        'name': '%s %s' % (f, l),
        'email': '%s.%s@%s' % (f.lower(), re.sub(r'\W', '', l.lower()), r.choice(['gmail.com', 'outlook.com', 'bigpond.com', 'example.com.au'])),
        'phone': phone,
        'address': '%d %s, %s %s %s' % (r.randrange(1, 400), r.choice(STREETS), sub, st, pc),
        'dob': '%02d/%02d/%d' % (r.randrange(1, 29), r.randrange(1, 13), r.randrange(1940, 2006)),
        'tfn': spaced(tfn, (3, 3, 3)) if r.random() < .7 else tfn,
        'medicare': spaced(medicare, (4, 5, 1)) if r.random() < .7 and len(medicare) == 10 else medicare,
        'abn': spaced(ids.abn(r), (2, 3, 3, 3)),
        'card': spaced(card, (4, 4, 4, 4)) if len(card) == 16 else card,
        'bank': 'BSB %03d-%03d account %08d' % (n3(), n3(), r.randrange(10 ** 8)),
        'passport': r.choice('NPRE') + '%07d' % r.randrange(10 ** 7),
        'licence': '%08d' % r.randrange(10 ** 8),
    }


# Where agents see personal data: (template, kinds). {x} fields come from person().
TEMPLATES = [
    ('customer_id,name,email,phone\n1042,{name},{email},{phone}\n1043,{name2},{email2},{phone2}', ['name', 'email', 'phone']),
    ('{{"id": 77, "full_name": "{name}", "tfn": "{tfn}", "status": "active"}}', ['name', 'tfn']),
    ('{{"output": "member {name} medicare {medicare} verified", "exit_code": 0}}', ['name', 'medicare']),
    ('Please update the postal address for {name} to {address}.', ['name', 'address']),
    ('2026-09-30T10:12:01Z INFO payment ok card={card} customer="{name}"', ['card', 'name']),
    ('Tax file number: {tfn}\nDate of birth: {dob}', ['tfn', 'dob']),
    ('Medicare card {medicare}, expires 04/2028', ['medicare']),
    ('Refund to {bank} (account holder {name})', ['bank', 'name']),
    ('ABN {abn} registered to {name}', ['abn', 'name']),
    ('def test_lookup():\n    record = {{"name": "{name}", "email": "{email}", "dob": "{dob}"}}\n    assert lookup(record)', ['name', 'email', 'dob']),
    ('Hi, I\'m {name}, born {dob}. My mobile is {phone} and I live at {address}.', ['name', 'dob', 'phone', 'address']),
    ('row 17: {name} | {address} | {phone}', ['name', 'address', 'phone']),
    ('Passport {passport}, holder {name}', ['passport', 'name']),
    ('Driver licence no. {licence} (NSW), {name}', ['licence', 'name']),
    ('Contact: {email}', ['email']),
    ('Call me on {phone} after 5pm.', ['phone']),
    ('Employee TFN {tfn}', ['tfn']),
    ('Ship to {address}', ['address']),
    ('Dear {name},\n\nThanks for your enquiry.', ['name']),
    ('DOB {dob}', ['dob']),
]

# Synthetic decoys: things that look like identifiers but are not personal data.
def decoys(r):
    out = []
    for _ in range(60):
        out.append(('order %s shipped' % ids.invalid_like(r, ids.tfn_valid, 9), 'decoy-9digit'))
        out.append(('{"build": %s, "duration_ms": %d}' % (ids.invalid_like(r, ids.medicare_valid, 10), r.randrange(99999)), 'decoy-10digit'))
        out.append(('commit %032x merged by ci' % r.getrandbits(128), 'decoy-hash'))
        out.append(('listening on 0.0.0.0:%d (pid %d)' % (r.randrange(1024, 65535), r.randrange(10 ** 6)), 'decoy-port'))
        out.append(('ts=%d level=info msg="request done" id=%s' % (r.randrange(10 ** 12, 10 ** 13), '%08x-%04x-4%03x' % (r.getrandbits(32), r.getrandbits(16), r.getrandbits(12))), 'decoy-uuid'))
        out.append(('class %sParser:\n    def parse_address(self, line): ...' % r.choice(FIRST), 'decoy-code-name'))
        out.append(('version %d.%d.%d released %d-%02d-%02d' % (r.randrange(9), r.randrange(30), r.randrange(30), r.randrange(2019, 2027), r.randrange(1, 13), r.randrange(1, 29)), 'decoy-date'))
    return out


def recorded():
    """Real agent text from the fixed-Hermes runs: tool results and user messages. Items
    from the PII tasks are labelled from their planted seed data; the others are negatives."""
    planted = {}
    for t in ('auditkit-pii-delegate', 'custkit-pii-delegate'):
        for f in glob.glob(str(ROOT / 'bench/multiagent/tasks' / t / 'seed/data/*.csv')):
            for row in list(open(f))[1:]:
                for cell in row.strip().split(','):
                    if '@' in cell: planted[cell] = 'email'
                    elif re.fullmatch(r"[A-Z][a-z]+ [A-Z][a-z]+", cell): planted[cell] = 'name'
    seen, out = set(), []
    for f in sorted(glob.glob(str(LIVE / 'ma1-main3/*/traces.private.json')) + glob.glob(str(LIVE / 'ma1-sig/*/traces.private.json'))):
        pii_task = '-pii-' in f
        for t in json.load(open(f)):
            req = t.get('request')
            if isinstance(req, str): req = json.loads(req)
            for m in (req or {}).get('messages', []):
                c = m.get('content')
                if m.get('role') not in ('tool', 'user') or not isinstance(c, str) or len(c) < 20: continue
                c = c[:4000]
                if c in seen: continue
                seen.add(c)
                kinds = {k for v, k in planted.items() if v in c} if pii_task else set()
                if EMAIL.search(c): kinds.add('email')   # any email is personal data to the router
                kinds = sorted(kinds)
                out.append((c, kinds, 'recorded-pii-task' if pii_task else 'recorded'))
    return out


def main():
    r = random.Random(20261002)
    items = []
    for i in range(30):
        for t, kinds in TEMPLATES:
            p, q = person(r), person(r)
            fields = dict(p, name2=q['name'], email2=q['email'], phone2=q['phone'])
            items.append({'source': 'synthetic', 'text': t.format(**fields), 'kinds': kinds})
    for text, src in decoys(r):
        items.append({'source': src, 'text': text, 'kinds': []})
    for text, kinds, src in recorded():
        items.append({'source': src, 'text': text, 'kinds': kinds})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, 'w') as f:
        for i, it in enumerate(items):
            f.write(json.dumps(dict(id=i, **it)) + '\n')
    from collections import Counter
    print(len(items), 'items ->', OUT)
    print(Counter(it['source'] for it in items))
    print('positives', sum(1 for it in items if it['kinds']), Counter(k for it in items for k in it['kinds']))


if __name__ == '__main__':
    main()
