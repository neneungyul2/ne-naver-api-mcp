// 라이브 테스트 실행기: .env를 읽고 NAVER_LIVE_TEST=1 을 설정해 tests/live 를 돌린다.
import { spawnSync } from "node:child_process";

const result = spawnSync(
  process.execPath,
  ["--env-file=.env", "--test", "tests/live/*.test.js"],
  { stdio: "inherit", env: { ...process.env, NAVER_LIVE_TEST: "1" } }
);
process.exit(result.status ?? 1);
