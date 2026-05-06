"""Tests for load balancing algorithms."""

import pytest

from runtime.sidecar.load_balancer import (
    ConsistentHashBalancer,
    LeastRequestsBalancer,
    RandomBalancer,
    RoundRobinBalancer,
    WeightedBalancer,
    create_load_balancer,
)


DESTINATIONS = [
    ("http://a:8443", "agent-a"),
    ("http://b:8443", "agent-b"),
    ("http://c:8443", "agent-c"),
]


class TestRoundRobinBalancer:
    def test_cycles_through_destinations(self):
        lb = RoundRobinBalancer()
        results = []
        for _ in range(6):
            ordered = lb.select(list(DESTINATIONS))
            results.append(ordered[0][1])

        # Should cycle: a, b, c, a, b, c
        assert results == ["agent-a", "agent-b", "agent-c", "agent-a", "agent-b", "agent-c"]

    def test_single_destination_unchanged(self):
        lb = RoundRobinBalancer()
        dests = [("http://a:8443", "agent-a")]
        assert lb.select(dests) == dests

    def test_empty_destinations(self):
        lb = RoundRobinBalancer()
        assert lb.select([]) == []


class TestRandomBalancer:
    def test_returns_all_destinations(self):
        lb = RandomBalancer()
        result = lb.select(list(DESTINATIONS))
        assert sorted(result) == sorted(DESTINATIONS)

    def test_varies_over_many_calls(self):
        lb = RandomBalancer()
        first_choices = set()
        for _ in range(50):
            result = lb.select(list(DESTINATIONS))
            first_choices.add(result[0][1])
        # Should see multiple different first choices
        assert len(first_choices) > 1

    def test_single_destination_unchanged(self):
        lb = RandomBalancer()
        dests = [("http://a:8443", "agent-a")]
        assert lb.select(dests) == dests


class TestLeastRequestsBalancer:
    def test_sorts_by_active_count(self):
        lb = LeastRequestsBalancer()
        lb.increment("http://a:8443")
        lb.increment("http://a:8443")
        lb.increment("http://b:8443")
        # c has 0, b has 1, a has 2
        result = lb.select(list(DESTINATIONS))
        assert result[0][1] == "agent-c"
        assert result[1][1] == "agent-b"
        assert result[2][1] == "agent-a"

    def test_decrement_updates_count(self):
        lb = LeastRequestsBalancer()
        lb.increment("http://a:8443")
        lb.increment("http://a:8443")
        lb.decrement("http://a:8443")
        # a has 1 now
        result = lb.select(list(DESTINATIONS))
        # b and c have 0, so they come first
        assert result[0][1] in ("agent-b", "agent-c")

    def test_decrement_never_below_zero(self):
        lb = LeastRequestsBalancer()
        lb.decrement("http://a:8443")
        result = lb.select(list(DESTINATIONS))
        assert len(result) == 3  # Still works


class TestConsistentHashBalancer:
    def test_stable_for_same_key(self):
        lb = ConsistentHashBalancer(hash_key="source_agent")
        ctx = {"source_agent": "agent-x"}
        result1 = lb.select(list(DESTINATIONS), ctx)
        result2 = lb.select(list(DESTINATIONS), ctx)
        assert result1[0] == result2[0]

    def test_different_keys_may_differ(self):
        lb = ConsistentHashBalancer(hash_key="source_agent")
        results = set()
        for i in range(20):
            ctx = {"source_agent": f"agent-{i}"}
            result = lb.select(list(DESTINATIONS), ctx)
            results.add(result[0][1])
        # With 20 different keys and 3 destinations, should see multiple
        assert len(results) > 1

    def test_single_destination(self):
        lb = ConsistentHashBalancer()
        dests = [("http://a:8443", "agent-a")]
        assert lb.select(dests, {"source_agent": "x"}) == dests


class TestWeightedBalancer:
    def test_weights_distribute_correctly(self):
        weights = {"agent-a": 90, "agent-b": 10}
        lb = WeightedBalancer(weights)
        dests = [("http://a:8443", "agent-a"), ("http://b:8443", "agent-b")]

        counts = {"agent-a": 0, "agent-b": 0}
        for _ in range(1000):
            result = lb.select(list(dests))
            counts[result[0][1]] += 1

        # agent-a should get ~90% (allow wide margin for randomness)
        assert counts["agent-a"] > 700
        assert counts["agent-b"] > 20

    def test_zero_weight_never_primary(self):
        weights = {"agent-a": 100, "agent-b": 0}
        lb = WeightedBalancer(weights)
        dests = [("http://a:8443", "agent-a"), ("http://b:8443", "agent-b")]

        for _ in range(100):
            result = lb.select(list(dests))
            # agent-b should never be first (weight=0 not included)
            assert result[0][1] == "agent-a"

    def test_equal_weights_distribute_evenly(self):
        weights = {"agent-a": 50, "agent-b": 50}
        lb = WeightedBalancer(weights)
        dests = [("http://a:8443", "agent-a"), ("http://b:8443", "agent-b")]

        counts = {"agent-a": 0, "agent-b": 0}
        for _ in range(1000):
            result = lb.select(list(dests))
            counts[result[0][1]] += 1

        # Should be roughly even (within 200 of 500)
        assert abs(counts["agent-a"] - 500) < 200
        assert abs(counts["agent-b"] - 500) < 200

    def test_single_destination(self):
        weights = {"agent-a": 100}
        lb = WeightedBalancer(weights)
        dests = [("http://a:8443", "agent-a")]
        assert lb.select(dests) == dests


class TestCreateLoadBalancer:
    def test_round_robin(self):
        lb = create_load_balancer("round-robin")
        assert isinstance(lb, RoundRobinBalancer)

    def test_random(self):
        lb = create_load_balancer("random")
        assert isinstance(lb, RandomBalancer)

    def test_least_requests(self):
        lb = create_load_balancer("least-requests")
        assert isinstance(lb, LeastRequestsBalancer)

    def test_consistent_hash(self):
        lb = create_load_balancer("consistent-hash", consistent_hash_key="skill")
        assert isinstance(lb, ConsistentHashBalancer)

    def test_unknown_algorithm_raises(self):
        with pytest.raises(ValueError, match="Unknown"):
            create_load_balancer("invalid-algo")
