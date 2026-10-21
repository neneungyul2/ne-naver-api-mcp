import pytest

from ne_naver_api_mcp.analysis.budget import (
    DEFAULT_MAX_CALLS,
    BudgetExceededError,
    check_budget,
)


def test_default_limit_is_30_and_exceeding_it_needs_confirm():
    assert DEFAULT_MAX_CALLS == 30
    with pytest.raises(BudgetExceededError) as e:
        check_budget(31)
    assert e.value.estimated == 31
    assert e.value.max_calls == 30
    assert "confirm" in str(e.value)


def test_confirm_or_within_limit_passes():
    check_budget(31, confirm=True)
    check_budget(30)
    check_budget(0)


def test_explicit_max_calls_is_the_limit():
    with pytest.raises(BudgetExceededError):
        check_budget(6, max_calls=5)
    check_budget(5, max_calls=5)


def test_message_mentions_dry_run_option():
    with pytest.raises(BudgetExceededError, match="dryRun"):
        check_budget(100)
