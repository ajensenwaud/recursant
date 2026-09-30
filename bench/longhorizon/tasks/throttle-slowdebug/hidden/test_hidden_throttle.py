import random
import unittest
from throttle import Bucket, Registry


def exact_allowed(rate, burst, events):
    scale = 1000
    tokens, last, allowed = burst * scale, events[0][0] if events else 0, []
    for t, cost in events:
        tokens = min(burst * scale, tokens + (t - last) * rate)
        last = t
        ok = tokens >= cost * scale
        if ok:
            tokens -= cost * scale
        allowed.append(ok)
    return allowed


class HiddenThrottleTests(unittest.TestCase):
    def test_burst_is_the_cap(self):
        b = Bucket(rate=5, burst=3, now_ms=0)
        self.assertEqual([b.allow(10 ** 6) for _ in range(5)], [True, True, True, False, False])

    def test_no_float_drift_over_long_run(self):
        # rate 3/s, one request every 333 ms: exact model allows each only when 1000 milli-tokens accrued
        b = Bucket(rate=3, burst=1, now_ms=0)
        events = [(i * 333, 1) for i in range(200000)]
        got = [b.allow(t, c) for t, c in events]
        self.assertEqual(got, exact_allowed(3, 1, events))

    def test_randomised_against_exact_model(self):
        rnd = random.Random(424242)
        for trial in range(400):
            rate, burst = rnd.randint(1, 97), rnd.randint(1, 9)
            t, events = 0, []
            for _ in range(rnd.randint(20, 300)):
                t += rnd.choice([0, 1, 9, 11, 101, 333, rnd.randint(0, 3000)])
                events.append((t, rnd.choice([1, 1, 2, 5])))
            b = Bucket(rate, burst, events[0][0])
            self.assertEqual([b.allow(x, c) for x, c in events], exact_allowed(rate, burst, events), trial)

    def test_eviction_drops_bucket_state(self):
        r = Registry(rate=1, burst=1, idle_ms=500)
        self.assertTrue(r.allow("a", 0)); self.assertFalse(r.allow("a", 0))
        self.assertTrue(r.allow("z", 501))
        self.assertTrue(r.allow("a", 502))
        self.assertLessEqual(len(getattr(r, "buckets", {})), 2)

    def test_no_clock_reads_and_validation(self):
        import inspect, throttle.bucket, throttle.registry
        src = inspect.getsource(throttle.bucket) + inspect.getsource(throttle.registry)
        self.assertNotIn("time.", src)
        with self.assertRaises(ValueError):
            Bucket(0, 1, 0)
        with self.assertRaises(ValueError):
            Bucket(1, 0, 0)
