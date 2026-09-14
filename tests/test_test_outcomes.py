from harness.test_outcomes import resolve_test_outcome


def test_exact_match_returns_its_own_outcome():
    results = {"com.example.FooTest::testBar": True}
    assert resolve_test_outcome(results, "com.example.FooTest::testBar") is True


def test_parameterized_variants_all_passing_counts_as_passing():
    results = {
        "com.example.FooTest::testBar(String)[1]": True,
        "com.example.FooTest::testBar(String)[2]": True,
    }
    assert resolve_test_outcome(results, "com.example.FooTest::testBar") is True


def test_parameterized_variants_any_failing_counts_as_failing():
    results = {
        "com.example.FooTest::testBar(String)[1]": True,
        "com.example.FooTest::testBar(String)[2]": False,
    }
    assert resolve_test_outcome(results, "com.example.FooTest::testBar") is False


def test_missing_test_id_counts_as_failing():
    assert resolve_test_outcome({}, "com.example.FooTest::testBar") is False
