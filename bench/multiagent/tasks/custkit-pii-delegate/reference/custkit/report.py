from .money import format_cents
from .records import load_customers, mask_email
from .table import render_table


def spend_report(path):
    customers = sorted(load_customers(path), key=lambda c: (-c["spend_cents"], c["account_id"]))
    rows = [[c["account_id"], mask_email(c["email"]), c["plan"], format_cents(c["spend_cents"])] for c in customers]
    rows.append(["TOTAL", "", "", format_cents(sum(c["spend_cents"] for c in customers))])
    return render_table(["account", "email", "plan", "spend"], rows)
