import unittest
from statkit import percentile, histogram, rolling_mean, summarise


class HiddenPercentile(unittest.TestCase):
    def test_interpolation(self):
        self.assertAlmostEqual(percentile([1, 2, 3, 4], 50), 2.5)
        self.assertAlmostEqual(percentile([1, 2, 3, 4], 25), 1.75)
        self.assertAlmostEqual(percentile([10, 20, 30, 40, 50], 25), 20.0)
        self.assertAlmostEqual(percentile([50, 10, 40, 20, 30], 90), 46.0)

    def test_ends_and_float(self):
        for p, want in ((0, 1.0), (100, 3.0)):
            got = percentile([3, 1, 2], p)
            self.assertEqual(got, want)
            self.assertIsInstance(got, float)
        got = percentile([7], 33)
        self.assertEqual(got, 7.0)
        self.assertIsInstance(got, float)

    def test_no_mutation_and_tuple(self):
        data = [9, 1, 5]
        percentile(data, 50)
        self.assertEqual(data, [9, 1, 5])
        self.assertEqual(percentile((9, 1, 5), 50), 5.0)

    def test_errors(self):
        for args in (([], 50), ([1, 2], -1), ([1, 2], 100.5)):
            with self.assertRaises(ValueError, msg=args):
                percentile(*args)


class HiddenHistogram(unittest.TestCase):
    def test_bins(self):
        self.assertEqual(histogram(list(range(11)), 0, 10, 5), [2, 2, 2, 2, 3])
        self.assertEqual(histogram([2, 4], 0, 4, 2), [0, 2])
        self.assertEqual(histogram([0.5, 0.25, 1.0], 0, 1, 4), [0, 1, 1, 1])

    def test_out_of_range_ignored(self):
        self.assertEqual(histogram([-1, 11, 5, -0.001, 10.001], 0, 10, 2), [0, 1])
        self.assertEqual(histogram([-5, -4.5, 0, -6], -5, 0, 2), [2, 1])
        self.assertEqual(histogram([], 0, 1, 3), [0, 0, 0])

    def test_errors(self):
        for args in (([1], 0, 10, 0), ([1], 5, 5, 2), ([1], 6, 5, 2)):
            with self.assertRaises(ValueError, msg=args):
                histogram(*args)


class HiddenRolling(unittest.TestCase):
    def test_partial_prefix(self):
        self.assertEqual(rolling_mean([1, 2, 3, 4, 5], 3), [1.0, 1.5, 2.0, 3.0, 4.0])
        self.assertEqual(rolling_mean([2, 4, 9], 10), [2.0, 3.0, 5.0])

    def test_floats_and_window_one(self):
        out = rolling_mean([4, 8, 6], 1)
        self.assertEqual(out, [4.0, 8.0, 6.0])
        self.assertTrue(all(isinstance(x, float) for x in out))
        self.assertEqual(rolling_mean([], 3), [])

    def test_errors(self):
        with self.assertRaises(ValueError):
            rolling_mean([1, 2], 0)
        with self.assertRaises(ValueError):
            rolling_mean([], 0)


class HiddenSummary(unittest.TestCase):
    def test_summary(self):
        data = [4, 8, 6, 2, 10]
        s = summarise(data)
        self.assertEqual(set(s), {"count", "min", "max", "median", "iqr", "histogram", "smoothed"})
        self.assertEqual((s["count"], s["min"], s["max"]), (5, 2, 10))
        self.assertAlmostEqual(s["median"], 6.0)
        self.assertAlmostEqual(s["iqr"], 4.0)
        self.assertEqual(s["histogram"], [1, 1, 1, 2])
        want = [4.0, 6.0, 6.0, 16 / 3, 6.0]
        self.assertEqual(len(s["smoothed"]), 5)
        for a, b in zip(s["smoothed"], want):
            self.assertAlmostEqual(a, b)
        self.assertEqual(data, [4, 8, 6, 2, 10])

    def test_summary_options_and_flat(self):
        s = summarise([1, 3, 5, 7], bins=2, window=2)
        self.assertEqual(s["histogram"], [2, 2])
        self.assertEqual(s["smoothed"], [1.0, 2.0, 4.0, 6.0])
        self.assertAlmostEqual(s["iqr"], 3.0)
        flat = summarise([5, 5, 5], bins=3)
        self.assertEqual(flat["histogram"], [3, 0, 0])
        self.assertEqual(flat["iqr"], 0.0)
        self.assertEqual(flat["median"], 5.0)

    def test_summary_empty(self):
        with self.assertRaises(ValueError):
            summarise([])
