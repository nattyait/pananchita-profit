from app.domain.allocation import split_proportionally


def test_sum_is_exact_and_leftover_goes_to_largest():
    shares = split_proportionally(1000, {"a": 1, "b": 1, "c": 1})
    assert sum(shares.values()) == 1000
    assert sorted(shares.values()) == [333, 333, 334]


def test_zero_weights_are_skipped_and_all_zero_returns_empty():
    assert split_proportionally(500, {"a": 0, "b": 5}) == {"b": 500}
    assert split_proportionally(500, {"a": 0}) == {}
    assert split_proportionally(500, {}) == {}


def test_negative_total_still_sums():
    shares = split_proportionally(-301, {"a": 2, "b": 1})
    assert sum(shares.values()) == -301
