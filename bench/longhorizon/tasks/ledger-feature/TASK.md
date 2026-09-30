The `ledger` package in /workspace stores bank-style transactions in a JSON file (`ledger/store.py`) and exposes
a small service layer (`ledger/service.py`) and a CLI (`ledger/cli.py`).

Add multi-currency support across the whole package:
1. Each account has a currency (ISO code, three uppercase letters). `open_account(name, currency="AUD")`.
2. Amounts are stored as integer minor units (cents). The existing store format stores floats in dollars; write a
   migration `ledger/migrate.py` with `migrate(path)` that upgrades a v1 file (no "version" key) to v2
   (`"version": 2`, integer cents, every account currency "AUD"). Migration must be idempotent.
3. `transfer(src, dst, amount_cents)` between accounts of different currencies must raise `CurrencyMismatch`
   (a new exception in `ledger/errors.py`). Same-currency transfers work as before. Overdrafts raise `InsufficientFunds`.
4. `balance(name)` returns integer cents. `statement(name)` returns a list of dicts with keys
   `kind` ("deposit"|"withdrawal"|"transfer_in"|"transfer_out"), `amount_cents`, `balance_cents`, in order.
5. The CLI gains `open NAME [CURRENCY]` and prints balances as e.g. `12.34 USD`.
6. The store must load v1 files by migrating them transparently on first load.

Update and extend the tests in `tests/`. Run them with `python -m unittest discover -s tests` from /workspace.
Use your file tools to edit files on disk.
