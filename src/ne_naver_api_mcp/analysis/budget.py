"""한 번의 실행에서 쓸 수 있는 API 호출 수 상한."""

DEFAULT_MAX_CALLS = 30


class BudgetExceededError(Exception):
    def __init__(self, estimated: int, max_calls: int) -> None:
        self.estimated = estimated
        self.max_calls = max_calls
        super().__init__(
            f"예상 API 호출 수 {estimated}회가 상한 {max_calls}회를 넘습니다. "
            "진행하려면 confirm: true를 지정하거나 maxCalls를 늘리세요. "
            "(dryRun: true로 호출 없이 예상 수만 볼 수 있습니다.)"
        )


def check_budget(estimated: int, max_calls: int | None = None, confirm: bool = False) -> None:
    """예상 호출 수가 상한을 넘고 confirm이 아니면 BudgetExceededError."""
    limit = DEFAULT_MAX_CALLS if max_calls is None else max_calls
    if estimated > limit and confirm is not True:
        raise BudgetExceededError(estimated, limit)
