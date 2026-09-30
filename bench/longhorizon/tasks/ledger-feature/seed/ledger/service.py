from .errors import UnknownAccount, InsufficientFunds
from .store import Store


class Ledger:
    def __init__(self, path):
        self.store = Store(path)

    def _acct(self, name):
        try:
            return self.store.data["accounts"][name]
        except KeyError:
            raise UnknownAccount(name) from None

    def open_account(self, name):
        self.store.data["accounts"].setdefault(name, {"balance": 0.0})
        self.store.save()

    def deposit(self, name, amount):
        a = self._acct(name)
        a["balance"] += amount
        self.store.data["log"].append(["deposit", name, amount, a["balance"]])
        self.store.save()

    def withdraw(self, name, amount):
        a = self._acct(name)
        if amount > a["balance"]:
            raise InsufficientFunds(name)
        a["balance"] -= amount
        self.store.data["log"].append(["withdrawal", name, amount, a["balance"]])
        self.store.save()

    def transfer(self, src, dst, amount):
        s, d = self._acct(src), self._acct(dst)
        if amount > s["balance"]:
            raise InsufficientFunds(src)
        s["balance"] -= amount
        d["balance"] += amount
        self.store.data["log"].append(["transfer_out", src, amount, s["balance"]])
        self.store.data["log"].append(["transfer_in", dst, amount, d["balance"]])
        self.store.save()

    def balance(self, name):
        return self._acct(name)["balance"]

    def statement(self, name):
        self._acct(name)
        return [dict(kind=k, amount=amt, balance=bal) for k, n, amt, bal in self.store.data["log"] if n == name]
