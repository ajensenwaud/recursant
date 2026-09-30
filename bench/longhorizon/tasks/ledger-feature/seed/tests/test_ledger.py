import tempfile
import unittest
from pathlib import Path
from ledger import Ledger
from ledger.errors import InsufficientFunds


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.led = Ledger(Path(self.tmp.name) / "l.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_deposit_withdraw(self):
        self.led.open_account("a")
        self.led.deposit("a", 10.0)
        self.led.withdraw("a", 4.0)
        self.assertEqual(self.led.balance("a"), 6.0)

    def test_overdraft(self):
        self.led.open_account("a")
        with self.assertRaises(InsufficientFunds):
            self.led.withdraw("a", 1.0)


if __name__ == "__main__":
    unittest.main()
