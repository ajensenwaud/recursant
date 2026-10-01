import random
import unittest
from throttle import Bucket, Registry


def exact_allowed(rate, burst, events):
    """Reference model in exact integer arithmetic (tokens scaled by 1000)."""
    scale = 1000
    tokens, last, allowed = burst * scale, events[0][0] if events else 0, []
    for t, cost in events:
        tokens = min(burst * scale, tokens + (t - last) * rate)
        last = t
        if tokens >= cost * scale:
            tokens -= cost * scale
            allowed.append(True)
        else:
            allowed.append(False)
    return allowed


class SimulationTests(unittest.TestCase):
    def test_long_simulation_matches_exact_model(self):
        rnd = random.Random(20260929)
        for trial in range(90000):
            rate, burst = rnd.randint(1, 50), rnd.randint(1, 20)
            t, events = 0, []
            for _ in range(rnd.randint(50, 400)):
                t += rnd.choice([0, 1, 3, 7, 33, 100, 997, rnd.randint(0, 5000)])
                events.append((t, rnd.choice([1, 1, 1, 2, 3])))
            b = Bucket(rate, burst, events[0][0])
            got = [b.allow(ts, c) for ts, c in events]
            self.assertEqual(got, exact_allowed(rate, burst, events), (trial, rate, burst))

    def test_registry_eviction_resets_bucket(self):
        r = Registry(rate=1, burst=2, idle_ms=1000)
        self.assertTrue(r.allow("a", 0)); self.assertTrue(r.allow("a", 0)); self.assertFalse(r.allow("a", 0))
        self.assertEqual(r.size(), 1)
        self.assertTrue(r.allow("b", 1001))  # a evicted here
        self.assertEqual(r.size(), 1)
        # a returns: fresh full bucket
        self.assertTrue(r.allow("a", 1002)); self.assertTrue(r.allow("a", 1002))


if __name__ == "__main__":
    unittest.main()
