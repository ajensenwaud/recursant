class Bucket:
    """Token bucket. `rate` tokens are added per 1000 ms, up to `burst`. Starts full."""

    def __init__(self, rate, burst, now_ms):
        if rate <= 0 or burst <= 0:
            raise ValueError("rate and burst must be positive")
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.last = now_ms

    def _refill(self, now_ms):
        elapsed = now_ms - self.last
        if elapsed > 0:
            self.tokens = min(self.burst + 1, self.tokens + elapsed * self.rate / 1000.0)
            self.last = now_ms

    def allow(self, now_ms, cost=1):
        self._refill(now_ms)
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False
