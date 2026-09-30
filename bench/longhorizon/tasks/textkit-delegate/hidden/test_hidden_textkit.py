import datetime
import unittest
from textkit import slugify, wrap, parse_date


class HiddenSlug(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")
        self.assertEqual(slugify("  Crème Brûlée  "), "creme-brulee")
        self.assertEqual(slugify("a---b___c"), "a-b-c")
        self.assertEqual(slugify("!!!"), "n-a")
        self.assertEqual(slugify(""), "n-a")
        self.assertEqual(slugify("日本語"), "n-a")

    def test_truncation(self):
        self.assertEqual(slugify("alpha beta gamma", max_len=12), "alpha-beta")
        self.assertEqual(slugify("alpha beta gamma", max_len=10), "alpha-beta")
        self.assertEqual(slugify("alpha beta gamma", max_len=11), "alpha-beta")
        self.assertEqual(slugify("supercalifragilistic", max_len=5), "super")
        self.assertEqual(slugify("ab cd", max_len=50), "ab-cd")


class HiddenWrap(unittest.TestCase):
    def test_wrap(self):
        self.assertEqual(wrap("the quick brown fox", 10), ["the quick", "brown fox"])
        self.assertEqual(wrap("  a  b  ", 1), ["a", "b"])
        self.assertEqual(wrap("abcdefghij kl", 4), ["abcd", "efgh", "ij", "kl"])
        self.assertEqual(wrap("", 5), [])
        self.assertEqual(wrap("   \n\t ", 5), [])
        self.assertEqual(wrap("one two", 7), ["one two"])
        with self.assertRaises(ValueError):
            wrap("x", 0)


class HiddenDates(unittest.TestCase):
    def test_formats(self):
        d = datetime.date(2024, 3, 7)
        for s in ("2024-03-07", "07/03/2024", "7 Mar 2024", "7 mar 2024", "Mar 7, 2024", "MAR 07, 2024", "  2024-03-07 "):
            self.assertEqual(parse_date(s), d, s)

    def test_invalid(self):
        for s in ("31/02/2024", "2024-13-01", "2024-3-7", "7 March 2024", "Foo 7, 2024", "", "2024/03/07", "7/3/2024"):
            with self.assertRaises(ValueError, msg=s):
                parse_date(s)
        self.assertEqual(parse_date("29/02/2024"), datetime.date(2024, 2, 29))
