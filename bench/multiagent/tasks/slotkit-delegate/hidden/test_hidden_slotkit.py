import unittest
from slotkit import merge, to_minutes, to_hhmm, free_slots, find_free


class HiddenMerge(unittest.TestCase):
    def test_overlap_touch_contain(self):
        self.assertEqual(merge([(5, 8), (1, 3), (2, 4)]), [(1, 4), (5, 8)])
        self.assertEqual(merge([(1, 3), (3, 5)]), [(1, 5)])
        self.assertEqual(merge([(1, 10), (2, 3), (4, 5)]), [(1, 10)])
        self.assertEqual(merge([(1, 2), (3, 4)]), [(1, 2), (3, 4)])
        self.assertEqual(merge([]), [])

    def test_types_and_no_mutation(self):
        data = [[7, 9], [1, 2], [8, 12]]
        out = merge(data)
        self.assertEqual(out, [(1, 2), (7, 12)])
        self.assertTrue(all(isinstance(p, tuple) for p in out))
        self.assertEqual(data, [[7, 9], [1, 2], [8, 12]])
        self.assertEqual(merge([(-5, -1), (-2, 0)]), [(-5, 0)])

    def test_errors(self):
        for bad in ([(3, 3)], [(4, 2)], [(1, 5), (9, 9)]):
            with self.assertRaises(ValueError, msg=bad):
                merge(bad)


class HiddenClock(unittest.TestCase):
    def test_to_minutes(self):
        self.assertEqual(to_minutes("00:00"), 0)
        self.assertEqual(to_minutes("09:30"), 570)
        self.assertEqual(to_minutes("23:59"), 1439)
        self.assertEqual(to_minutes("24:00"), 1440)

    def test_to_minutes_errors(self):
        for bad in ("9:30", "09:60", "24:01", "25:00", "0930", " 09:30", "09:30 ", "", "09:3", "ab:cd",
                    "09-30", "09:30:00", "-1:30", "09:30\n", "٠٩:30"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                to_minutes(bad)

    def test_to_hhmm(self):
        self.assertEqual(to_hhmm(0), "00:00")
        self.assertEqual(to_hhmm(65), "01:05")
        self.assertEqual(to_hhmm(1439), "23:59")
        self.assertEqual(to_hhmm(1440), "24:00")
        for bad in (-1, 1441):
            with self.assertRaises(ValueError, msg=bad):
                to_hhmm(bad)


class HiddenGaps(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(free_slots([(2, 4), (6, 8)], 0, 10), [(0, 2), (4, 6), (8, 10)])
        self.assertEqual(free_slots([], 3, 9), [(3, 9)])
        self.assertEqual(free_slots([(0, 10)], 0, 10), [])
        self.assertEqual(free_slots([(0, 3), (3, 5), (9, 10)], 0, 10), [(5, 9)])

    def test_clipping(self):
        self.assertEqual(free_slots([(-5, 2), (8, 20)], 0, 10), [(2, 8)])
        self.assertEqual(free_slots([(-9, -3), (4, 5), (12, 15)], 0, 10), [(0, 4), (5, 10)])
        self.assertEqual(free_slots([(-5, 50)], 0, 10), [])
        self.assertEqual(free_slots([(10, 12)], 0, 10), [(0, 10)])

    def test_min_len(self):
        busy = [(2, 4), (5, 8)]
        self.assertEqual(free_slots(busy, 0, 10, min_len=2), [(0, 2), (8, 10)])
        self.assertEqual(free_slots(busy, 0, 10, min_len=3), [])
        self.assertEqual(free_slots([], 0, 4, min_len=5), [])
        self.assertEqual(free_slots(busy, 0, 10, 1), [(0, 2), (4, 5), (8, 10)])

    def test_errors(self):
        for args in (([], 5, 5), ([], 6, 5), ([], 0, 5, 0)):
            with self.assertRaises(ValueError, msg=args):
                free_slots(*args)


class HiddenPlanner(unittest.TestCase):
    BUSY = [("13:00", "14:00"), ("09:30", "10:15"), ("10:00", "11:00"), ("16:45", "18:00"), ("11:00", "11:20")]

    def test_find_free(self):
        self.assertEqual(find_free(self.BUSY), ["09:00-09:30", "11:20-13:00", "14:00-16:45"])
        self.assertEqual(find_free(self.BUSY, min_minutes=31), ["11:20-13:00", "14:00-16:45"])
        self.assertEqual(find_free(self.BUSY, "10:00", "13:30", 1), ["11:20-13:00"])

    def test_whole_day_and_errors(self):
        self.assertEqual(find_free([], "00:00", "24:00"), ["00:00-24:00"])
        self.assertEqual(find_free([("00:00", "23:45")], "00:00", "24:00", 15), ["23:45-24:00"])
        with self.assertRaises(ValueError):
            find_free([("9:00", "10:00")])
        with self.assertRaises(ValueError):
            find_free([("11:00", "10:00")])
        with self.assertRaises(ValueError):
            find_free([], "17:00", "09:00")
