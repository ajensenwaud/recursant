import csv
import re

_ACCOUNT = re.compile(r"ACCOUNT-[0-9]{6}")
_SPEND = re.compile(r"-?[0-9]+")
FIELDS = ("account_id", "name", "email", "plan", "spend_cents")


def _valid_email(email):
    if email.count("@") != 1 or any(ch.isspace() for ch in email):
        return False
    local, domain = email.split("@")
    if not local or "." not in domain:
        return False
    return not (domain.startswith(".") or domain.endswith("."))


def load_customers(path):
    out, seen = [], set()
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rec = {k: (row.get(k) or "").strip() for k in FIELDS}
            rec["email"] = rec["email"].lower()
            if not _ACCOUNT.fullmatch(rec["account_id"]):
                continue
            if not _valid_email(rec["email"]):
                continue
            if not _SPEND.fullmatch(rec["spend_cents"]):
                continue
            if rec["email"] in seen:
                continue
            seen.add(rec["email"])
            rec["spend_cents"] = int(rec["spend_cents"])
            out.append(rec)
    return out


def mask_email(email):
    if email.count("@") != 1:
        raise ValueError("expected exactly one at-sign")
    local, domain = email.split("@")
    if not local:
        raise ValueError("empty local part")
    return local[0] + "***@" + domain
