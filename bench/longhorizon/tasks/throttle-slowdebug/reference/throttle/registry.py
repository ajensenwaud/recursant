from .bucket import Bucket


class Registry:
    """One bucket per client; buckets idle for more than `idle_ms` are evicted."""

    def __init__(self, rate, burst, idle_ms):
        self.rate, self.burst, self.idle_ms = rate, burst, idle_ms
        self.buckets = {}
        self.seen = {}

    def _evict(self, now_ms):
        for client in [c for c, t in self.seen.items() if now_ms - t > self.idle_ms]:
            del self.seen[client]
            self.buckets.pop(client, None)

    def allow(self, client, now_ms, cost=1):
        self._evict(now_ms)
        b = self.buckets.get(client)
        if b is None:
            b = self.buckets[client] = Bucket(self.rate, self.burst, now_ms)
        self.seen[client] = now_ms
        return b.allow(now_ms, cost)

    def size(self):
        return len(self.seen)
