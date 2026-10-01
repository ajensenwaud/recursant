import csv
import hashlib
import re

_ACCOUNT = re.compile(r"ACCOUNT-[0-9]{6}")
_STATUSES = ("active", "paused", "cancelled")
FIELDS = ("account_id", "full_name", "email", "signup_date", "status")


def load_subscribers(path):
    kept = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rec = {k: (row.get(k) or "").strip() for k in FIELDS}
            rec["email"] = rec["email"].lower()
            rec["status"] = rec["status"].lower()
            if not _ACCOUNT.fullmatch(rec["account_id"]) or rec["status"] not in _STATUSES:
                continue
            kept[rec["account_id"]] = rec  # dict keeps the position of the first insertion
    return list(kept.values())


def domain_counts(records):
    counts = {}
    for rec in records:
        domain = rec["email"].split("@", 1)[1]
        counts[domain] = counts.get(domain, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def pseudonym(account_id, salt):
    digest = hashlib.sha256(("%s:%s" % (salt, account_id)).encode("utf-8")).hexdigest()
    return "sub_" + digest[:12]
