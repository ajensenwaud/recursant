class Bucket:
    """Token bucket. `rate` tokens are added per 1000 ms, up to `burst`. Starts full.
    Tokens are kept as integer milli-tokens to avoid float drift."""

    SCALE = 1000

    def __init__(self, rate, burst, now_ms):
        if rate <= 0 or burst <= 0:
            raise ValueError("rate and burst must be positive")
        self.rate = rate
        self.burst = burst
        self.milli = burst * self.SCALE
        self.last = now_ms

    @property
    def tokens(self):
        return self.milli / self.SCALE

    def _refill(self, now_ms):
        elapsed = now_ms - self.last
        if elapsed > 0:
            self.milli = min(self.burst * self.SCALE, self.milli + elapsed * self.rate)
            self.last = now_ms

    def allow(self, now_ms, cost=1):
        self._refill(now_ms)
        if self.milli >= cost * self.SCALE:
            self.milli -= cost * self.SCALE
            return True
        return False
