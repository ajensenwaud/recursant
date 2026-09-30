import re
from .errors import UnknownAccount, InsufficientFunds, CurrencyMismatch
from .store import Store


class Ledger:
    def __init__(self, path):
        self.store = Store(path)

    def _acct(self, name):
        try:
            return self.store.data["accounts"][name]
        except KeyError:
            raise UnknownAccount(name) from None

    def open_account(self, name, currency="AUD"):
        if not re.fullmatch(r"[A-Z]{3}", currency or ""):
            raise ValueError("currency")
        self.store.data["accounts"].setdefault(name, {"balance_cents": 0, "currency": currency})
        self.store.save()

    def currency(self, name):
        return self._acct(name)["currency"]

    def _log(self, kind, name, amount, bal):
        self.store.data["log"].append([kind, name, amount, bal])

    def deposit(self, name, amount_cents):
        a = self._acct(name)
        a["balance_cents"] += int(amount_cents)
        self._log("deposit", name, int(amount_cents), a["balance_cents"])
        self.store.save()

    def withdraw(self, name, amount_cents):
        a = self._acct(name)
        if amount_cents > a["balance_cents"]:
            raise InsufficientFunds(name)
        a["balance_cents"] -= int(amount_cents)
        self._log("withdrawal", name, int(amount_cents), a["balance_cents"])
        self.store.save()

    def transfer(self, src, dst, amount_cents):
        s, d = self._acct(src), self._acct(dst)
        if s["currency"] != d["currency"]:
            raise CurrencyMismatch(f"{s['currency']}->{d['currency']}")
        if amount_cents > s["balance_cents"]:
            raise InsufficientFunds(src)
        s["balance_cents"] -= int(amount_cents)
        d["balance_cents"] += int(amount_cents)
        self._log("transfer_out", src, int(amount_cents), s["balance_cents"])
        self._log("transfer_in", dst, int(amount_cents), d["balance_cents"])
        self.store.save()

    def balance(self, name):
        return self._acct(name)["balance_cents"]

    def statement(self, name):
        self._acct(name)
        return [dict(kind=k, amount_cents=amt, balance_cents=bal) for k, n, amt, bal in self.store.data["log"] if n == name]
