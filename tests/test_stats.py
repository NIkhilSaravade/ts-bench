import pytest

from pipeline.stats import pass_at_k


def test_pass_at_k_matches_hand_calculation():
    # C(3,2)/C(5,2) = 3/10 -> pass@2 = 1 - 3/10 = 0.7
    assert pass_at_k(n=5, c=2, k=2) == pytest.approx(0.7)


def test_pass_at_1_reduces_to_plain_resolved_rate():
    assert pass_at_k(n=10, c=3, k=1) == pytest.approx(0.3)


def test_pass_at_k_is_one_when_fewer_failures_than_k():
    assert pass_at_k(n=5, c=5, k=3) == 1.0
    assert pass_at_k(n=5, c=4, k=2) == 1.0  # only 1 failure -- can't fill a 2-subset with zero successes


def test_pass_at_k_is_zero_with_no_successes():
    assert pass_at_k(n=5, c=0, k=3) == 0.0


def test_k_greater_than_n_raises():
    with pytest.raises(ValueError):
        pass_at_k(n=3, c=1, k=5)
