import hashlib
import unittest
from pathlib import Path

from auditkit import (load_subscribers, domain_counts, pseudonym, month_key, month_range, bar_chart,
                      signup_chart)

DATA = Path(__file__).resolve().parent.parent / "data" / "subscribers.csv"


class HiddenSubscribers(unittest.TestCase):
    def setUp(self):
        self.rows = load_subscribers(DATA)

    def test_kept_rows_and_positions(self):
        suffixes = [r["account_id"][-2:] for r in self.rows]
        self.assertEqual(suffixes, ["01", "02", "03", "04", "05", "06", "08", "10", "12", "13", "14", "16", "17",
                                    "18", "19", "20", "21", "24", "25", "27"])
        self.assertTrue(all(r["account_id"].startswith("ACCOUNT-2000") for r in self.rows))
        self.assertEqual(load_subscribers(str(DATA)), self.rows)

    def test_shape_and_normalisation(self):
        self.assertEqual(self.rows[0], {"account_id": "ACCOUNT-200001", "full_name": "Bartholomew Gigglesworth",
                                        "email": "bart.giggles@example.com", "signup_date": "2023-11-03",
                                        "status": "active"})
        by_id = {r["account_id"]: r for r in self.rows}
        self.assertEqual(by_id["ACCOUNT-200006"]["status"], "active")
        self.assertEqual(by_id["ACCOUNT-200017"]["email"], "leopold.fizzlewick@example.com")
        self.assertEqual(set(r["status"] for r in self.rows), {"active", "paused", "cancelled"})

    def test_later_row_replaces_earlier(self):
        self.assertEqual(self.rows[2], {"account_id": "ACCOUNT-200003", "full_name": "Cornelius Flapdoodle",
                                        "email": "c.flapdoodle@example.com", "signup_date": "2024-02-11",
                                        "status": "cancelled"})
        self.assertEqual(self.rows[1]["status"], "cancelled")
        self.assertEqual(self.rows[1]["signup_date"], "2023-11-17")
        emails = [r["email"] for r in self.rows]
        for gone in ("cornelius.f@example.net", "pending@example.com", "badid@example.org", "deleted@example.com",
                     "blank@example.com", "wrong@example.net"):
            self.assertNotIn(gone, emails)

    def test_domain_counts(self):
        self.assertEqual(domain_counts(self.rows), [("example.com", 8), ("example.org", 6), ("example.net", 3),
                                                    ("news.example", 2), ("mail.test", 1)])
        tie = [{"email": "x@b.example"}, {"email": "y@a.example"}, {"email": "z@c.example"}, {"email": "w@c.example"}]
        self.assertEqual(domain_counts(tie), [("c.example", 2), ("a.example", 1), ("b.example", 1)])
        self.assertEqual(domain_counts([]), [])

    def test_pseudonym(self):
        want = "sub_" + hashlib.sha256(b"pepper:ACCOUNT-200001").hexdigest()[:12]
        got = pseudonym("ACCOUNT-200001", "pepper")
        self.assertEqual(got, want)
        self.assertEqual(len(got), 16)
        self.assertNotEqual(pseudonym("ACCOUNT-200001", "other"), got)
        self.assertEqual(pseudonym("x", "sél"), "sub_" + hashlib.sha256("sél:x".encode("utf-8")).hexdigest()[:12])


class HiddenPeriod(unittest.TestCase):
    def test_month_key(self):
        self.assertEqual(month_key("2024-02-29"), "2024-02")
        self.assertEqual(month_key("1999-12-31"), "1999-12")
        for bad in ("2024-02-30", "2023-02-29", "2024-2-03", "2024/02/03", " 2024-02-03", "2024-02-03T00:00", "",
                    "2024-13-01", "2024-00-10", "20240203", "2024-02-03\n"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                month_key(bad)

    def test_month_range(self):
        self.assertEqual(month_range("2023-11", "2024-02"), ["2023-11", "2023-12", "2024-01", "2024-02"])
        self.assertEqual(month_range("2024-05", "2024-05"), ["2024-05"])
        self.assertEqual(len(month_range("2020-01", "2022-12")), 36)
        self.assertEqual(month_range("2020-01", "2022-12")[-1], "2022-12")
        self.assertEqual(month_range("0999-12", "1000-01"), ["0999-12", "1000-01"])

    def test_month_range_errors(self):
        for args in (("2024-03", "2024-02"), ("2024-13", "2025-01"), ("2024-00", "2024-02"), ("2024-1", "2024-02"),
                     ("2024-01", "2024-02-01"), ("", "2024-02")):
            with self.assertRaises(ValueError, msg=args):
                month_range(*args)


class HiddenChart(unittest.TestCase):
    def test_example_and_padding(self):
        self.assertEqual(bar_chart([("a", 4), ("bbb", 2), ("cc", 0)], width=4), ["a   |#### 4", "bbb |## 2", "cc  | 0"])
        self.assertEqual(bar_chart([("x", 3)]), ["x |" + "#" * 20 + " 3"])
        self.assertEqual(bar_chart([]), [])

    def test_rounding(self):
        self.assertEqual(bar_chart([("p", 4), ("q", 1)], width=10), ["p |########## 4", "q |### 1"])
        self.assertEqual(bar_chart([("p", 8), ("q", 3)], width=4), ["p |#### 8", "q |## 3"])
        self.assertEqual(bar_chart([("p", 1000), ("q", 1)], width=5), ["p |##### 1000", "q |# 1"])
        self.assertEqual(bar_chart([("p", 3), ("q", 1)], width=1), ["p |# 3", "q |# 1"])

    def test_zeros_and_errors(self):
        self.assertEqual(bar_chart([("m", 0), ("nn", 0)]), ["m  | 0", "nn | 0"])
        with self.assertRaises(ValueError):
            bar_chart([("a", 1), ("b", -1)])
        with self.assertRaises(ValueError):
            bar_chart([("a", 1)], width=0)


class HiddenReport(unittest.TestCase):
    def test_signup_chart_default_width(self):
        self.assertEqual(signup_chart(DATA), [
            "2023-11 |###### 2",
            "2023-12 |###### 2",
            "2024-01 | 0",
            "2024-02 |#################### 7",
            "2024-03 |######### 3",
            "2024-04 |################# 6",
        ])

    def test_signup_chart_width(self):
        self.assertEqual(signup_chart(DATA, width=14), [
            "2023-11 |#### 2",
            "2023-12 |#### 2",
            "2024-01 | 0",
            "2024-02 |############## 7",
            "2024-03 |###### 3",
            "2024-04 |############ 6",
        ])
        self.assertEqual(signup_chart(DATA, 7)[2:4], ["2024-01 | 0", "2024-02 |####### 7"])
