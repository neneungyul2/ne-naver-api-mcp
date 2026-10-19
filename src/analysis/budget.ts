export const DEFAULT_MAX_CALLS = 30;

export class BudgetExceededError extends Error {
  constructor(
    public readonly estimated: number,
    public readonly maxCalls: number
  ) {
    super(
      `예상 API 호출 수 ${estimated}회가 상한 ${maxCalls}회를 넘습니다. 진행하려면 confirm: true를 지정하거나 maxCalls를 늘리세요. (dryRun: true로 호출 없이 예상 수만 볼 수 있습니다.)`
    );
    this.name = "BudgetExceededError";
  }
}

/** 예상 호출 수가 상한을 넘고 confirm이 없으면 던진다. */
export function checkBudget(opts: {
  estimated: number;
  maxCalls?: number;
  confirm?: boolean;
}): void {
  const maxCalls = opts.maxCalls ?? DEFAULT_MAX_CALLS;
  if (opts.estimated > maxCalls && opts.confirm !== true) {
    throw new BudgetExceededError(opts.estimated, maxCalls);
  }
}
