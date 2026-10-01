import unittest
from pathlib import Path

from custkit import load_customers, mask_email, format_cents, split_evenly, render_table, spend_report

DATA = Path(__file__).resolve().parent.parent / "data" / "customers.csv"


class HiddenRecords(unittest.TestCase):
    def setUp(self):
        self.rows = load_customers(DATA)

    def test_kept_rows_in_file_order(self):
        suffixes = [r["account_id"][-2:] for r in self.rows]
        self.assertEqual(suffixes, ["01", "02", "03", "04", "06", "08", "10", "11", "12", "14", "16", "18", "20",
                                    "21", "23", "24", "25", "28"])
        self.assertTrue(all(r["account_id"].startswith("ACCOUNT-1000") for r in self.rows))

    def test_shape_and_types(self):
        first = self.rows[0]
        self.assertEqual(first, {"account_id": "ACCOUNT-100001", "name": "Zelda Quillfeather",
                                 "email": "zelda.quillfeather@example.com", "plan": "pro", "spend_cents": 12900})
        for r in self.rows:
            self.assertEqual(set(r), {"account_id", "name", "email", "plan", "spend_cents"})
            self.assertIs(type(r["spend_cents"]), int)
        self.assertEqual(load_customers(str(DATA)), self.rows)

    def test_normalisation(self):
        by_id = {r["account_id"]: r for r in self.rows}
        self.assertEqual(by_id["ACCOUNT-100010"]["email"], "thaddeus@corp.test")
        self.assertEqual(by_id["ACCOUNT-100028"]["email"], "shortid@example.com")
        self.assertEqual(by_id["ACCOUNT-100025"]["spend_cents"], -550)
        self.assertEqual(by_id["ACCOUNT-100002"]["name"], "Barnaby Thistlewick")
        self.assertEqual(by_id["ACCOUNT-100003"]["plan"], "team")

    def test_invalid_and_duplicates_dropped(self):
        emails = [r["email"] for r in self.rows]
        self.assertEqual(len(emails), len(set(emails)))
        self.assertEqual(emails.count("zelda.quillfeather@example.com"), 1)
        self.assertEqual(emails.count("ottoline.m@example.net"), 1)
        for gone in ("nodot@localhost", "double@@example.com", "seven@example.com", "lower@example.org",
                     "badspend@example.org", ""):
            self.assertNotIn(gone, emails)

    def test_mask_email(self):
        self.assertEqual(mask_email("zelda.quillfeather@example.com"), "z***@example.com")
        self.assertEqual(mask_email("g@example.com"), "g***@example.com")
        self.assertEqual(mask_email("ab@mail.example"), "a***@mail.example")
        for bad in ("no-at-sign", "@example.com", "a@b@example.com", ""):
            with self.assertRaises(ValueError, msg=bad):
                mask_email(bad)


class HiddenMoney(unittest.TestCase):
    def test_format_cents(self):
        self.assertEqual(format_cents(123456), "$1,234.56")
        self.assertEqual(format_cents(0), "$0.00")
        self.assertEqual(format_cents(5), "$0.05")
        self.assertEqual(format_cents(100), "$1.00")
        self.assertEqual(format_cents(99999999), "$999,999.99")
        self.assertEqual(format_cents(100000000), "$1,000,000.00")

    def test_format_cents_negative(self):
        self.assertEqual(format_cents(-5), "-$0.05")
        self.assertEqual(format_cents(-550), "-$5.50")
        self.assertEqual(format_cents(-123456), "-$1,234.56")
        self.assertEqual(format_cents(-100), "-$1.00")

    def test_split_evenly(self):
        self.assertEqual(split_evenly(100, 3), [34, 33, 33])
        self.assertEqual(split_evenly(2, 3), [1, 1, 0])
        self.assertEqual(split_evenly(0, 2), [0, 0])
        self.assertEqual(split_evenly(7, 1), [7])
        self.assertEqual(split_evenly(11, 4), [3, 3, 3, 2])
        for args in ((10, 0), (10, -1), (-1, 2)):
            with self.assertRaises(ValueError, msg=args):
                split_evenly(*args)


class HiddenTable(unittest.TestCase):
    def test_example(self):
        self.assertEqual(render_table(["item", "qty"], [["apple", 3], ["kiwi", 12]]),
                         "item  | qty\n------+----\napple |   3\nkiwi  |  12")

    def test_alignment_and_trailing_whitespace(self):
        self.assertEqual(render_table(["a", "b"], [["xx", "y"], ["z", "long"]]),
                         "a  | b\n---+-----\nxx | y\nz  | long")
        self.assertEqual(render_table(["n", "flag", "s"], [[5, True, "12"], [123, False, ""]]),
                         "n   | flag  | s\n----+-------+---\n  5 | True  | 12\n123 | False |")
        self.assertEqual(render_table(["wide header", "x"], [[1, 2.5]]),
                         "wide header | x\n------------+----\n          1 | 2.5")

    def test_empty_and_errors(self):
        self.assertEqual(render_table(["one", "two"], []), "one | two\n----+----")
        with self.assertRaises(ValueError):
            render_table(["a", "b"], [["only one"]])
        with self.assertRaises(ValueError):
            render_table(["a"], [["x"], ["y", "z"]])


class HiddenReport(unittest.TestCase):
    def setUp(self):
        self.lines = spend_report(DATA).split("\n")

    def test_layout(self):
        self.assertEqual(len(self.lines), 2 + 18 + 1)
        self.assertEqual(self.lines[0], "account        | email             | plan       | spend")
        self.assertEqual(self.lines[1], "---------------+-------------------+------------+-----------")
        self.assertEqual(self.lines[-1], "TOTAL          |                   |            | $19,815.72")
        self.assertTrue(all(line == line.rstrip() for line in self.lines))

    def test_order_and_masking(self):
        self.assertEqual(self.lines[2], "ACCOUNT-100016 | h***@example.com  | enterprise | $12,345.67")
        self.assertEqual(self.lines[3], "ACCOUNT-100010 | t***@corp.test    | enterprise | $2,500.00")
        self.assertEqual(self.lines[4], "ACCOUNT-100023 | a***@example.org  | enterprise | $2,500.00")
        self.assertEqual(self.lines[5], "ACCOUNT-100020 | l***@example.net  | team       | $450.05")
        self.assertEqual(self.lines[8], "ACCOUNT-100014 | c***@shop.example | team       | $450.00")
        self.assertEqual(self.lines[-3], "ACCOUNT-100028 | s***@example.com  | free       | $0.00")
        self.assertEqual(self.lines[-2], "ACCOUNT-100025 | r***@example.net  | pro        | -$5.50")
        body = "\n".join(self.lines)
        self.assertNotIn("zelda", body)
        self.assertNotIn("horatio", body)
