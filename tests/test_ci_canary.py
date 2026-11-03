def test_ci_canary_must_fail():
    """Deliberate failure: proves a failing test fails the CI check. Never merge."""
    assert 1 == 2
