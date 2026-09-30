import unittest
import report

SAMPLE = """# header comment
north,apple,3,1.50
south,apple,2,1.50
north,pear,1,2.05
bad line
"""


class ReportTests(unittest.TestCase):
    def test_total(self):
        self.assertIn("Total revenue: $9.55", report.build(SAMPLE))

    def test_skipped(self):
        self.assertIn("Skipped lines: 1", report.build(SAMPLE))


if __name__ == "__main__":
    unittest.main()
