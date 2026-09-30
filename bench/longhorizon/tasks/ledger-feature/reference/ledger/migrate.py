import json
from pathlib import Path


def _cents(x):
    return int(round(float(x) * 100))


def upgrade(data):
    if data.get("version") == 2:
        return data
    accounts = {n: {"balance_cents": _cents(a.get("balance", 0)), "currency": "AUD"}
                for n, a in data.get("accounts", {}).items()}
    log = [[k, n, _cents(amt), _cents(bal)] for k, n, amt, bal in data.get("log", [])]
    return {"version": 2, "accounts": accounts, "log": log}


def migrate(path):
    path = Path(path)
    data = json.loads(path.read_text())
    new = upgrade(data)
    if new is not data:
        path.write_text(json.dumps(new, indent=2, sort_keys=True))
    return new
