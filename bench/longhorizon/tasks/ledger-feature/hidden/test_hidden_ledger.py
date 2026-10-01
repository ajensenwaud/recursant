import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from ledger import Ledger
from ledger import errors
from ledger.migrate import migrate
from ledger.cli import main


class HiddenLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "l.json"

    def tearDown(self):
        self.tmp.cleanup()

    def v1(self):
        self.path.write_text(json.dumps({"accounts": {"a": {"balance": 12.34}, "b": {"balance": 0.1}},
                                         "log": [["deposit", "a", 12.34, 12.34], ["deposit", "b", 0.1, 0.1]]}))

    def test_migration_to_v2_and_idempotent(self):
        self.v1()
        d = migrate(self.path)
        self.assertEqual(d["version"], 2)
        self.assertEqual(d["accounts"]["a"]["balance_cents"] if "balance_cents" in d["accounts"]["a"] else None, 1234)
        self.assertEqual(d["accounts"]["b"]["currency"], "AUD")
        first = self.path.read_text()
        migrate(self.path)
        self.assertEqual(json.loads(first), json.loads(self.path.read_text()))

    def test_transparent_load_of_v1(self):
        self.v1()
        led = Ledger(self.path)
        self.assertEqual(led.balance("a"), 1234)
        self.assertEqual(led.balance("b"), 10)
        self.assertEqual(json.loads(self.path.read_text()).get("version"), 2)

    def test_currency_mismatch_and_same_currency_transfer(self):
        led = Ledger(self.path)
        led.open_account("x", "USD"); led.open_account("y", "EUR"); led.open_account("z", "USD")
        led.deposit("x", 500)
        with self.assertRaises(errors.CurrencyMismatch):
            led.transfer("x", "y", 100)
        self.assertTrue(issubclass(errors.CurrencyMismatch, Exception))
        led.transfer("x", "z", 200)
        self.assertEqual((led.balance("x"), led.balance("z")), (300, 200))
        with self.assertRaises(errors.InsufficientFunds):
            led.transfer("x", "z", 301)

    def test_statement_shape_and_order(self):
        led = Ledger(self.path)
        led.open_account("a"); led.open_account("b")
        led.deposit("a", 1000); led.withdraw("a", 250); led.transfer("a", "b", 100)
        self.assertEqual(led.statement("a"), [
            {"kind": "deposit", "amount_cents": 1000, "balance_cents": 1000},
            {"kind": "withdrawal", "amount_cents": 250, "balance_cents": 750},
            {"kind": "transfer_out", "amount_cents": 100, "balance_cents": 650}])
        self.assertEqual(led.statement("b"), [{"kind": "transfer_in", "amount_cents": 100, "balance_cents": 100}])
        self.assertIsInstance(led.balance("a"), int)

    def test_default_currency_and_cli(self):
        cwd = Path(self.tmp.name) / "cli.json"
        main(["open", "c", "USD"], path=str(cwd))
        main(["deposit", "c", "12.34"], path=str(cwd))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["balance", "c"], path=str(cwd))
        self.assertEqual(buf.getvalue().strip(), "12.34 USD")
        main(["open", "d"], path=str(cwd))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["balance", "d"], path=str(cwd))
        self.assertEqual(buf.getvalue().strip(), "0.00 AUD")
