from pipeline.contamination import contamination_risk


def test_merge_well_before_cutoff_is_risk():
    assert contamination_risk("2023-01-01", "2024-01-01") is True


def test_merge_well_after_cutoff_is_safe():
    assert contamination_risk("2024-06-01", "2024-01-01", margin_days=90) is False


def test_merge_within_margin_after_cutoff_is_still_risk():
    # cutoff 2024-01-01, merge 2024-02-01 -- 31 days after, inside a 90-day margin
    assert contamination_risk("2024-02-01", "2024-01-01", margin_days=90) is True


def test_merge_on_cutoff_day_is_risk():
    assert contamination_risk("2024-01-01", "2024-01-01") is True


def test_zero_margin_only_flags_on_or_before_cutoff():
    assert contamination_risk("2024-01-02", "2024-01-01", margin_days=0) is False
    assert contamination_risk("2024-01-01", "2024-01-01", margin_days=0) is True
