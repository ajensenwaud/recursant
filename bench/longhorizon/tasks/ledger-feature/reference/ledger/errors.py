class LedgerError(Exception):
    pass


class UnknownAccount(LedgerError):
    pass


class InsufficientFunds(LedgerError):
    pass


class CurrencyMismatch(LedgerError):
    pass
