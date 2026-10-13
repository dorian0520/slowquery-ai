# lab/tests — 실습 코드 테스트

실습 스크립트 중 **운영 반영 · 리포트 · 검증의 판단 로직**과 **수집기**가 의도대로 동작하는지 확인하는 테스트입니다. 코드를 고친 뒤 "되던 게 깨지지 않았나" 를 볼 때 돌립니다.

## 파일

| 파일 | 무엇을 확인하나 | DB 필요 | 개수 |
|---|---|---|---|
| `test_ops.py` | `apply_fix` 계획 · 사전 점검 · 중복 인덱스 판정, `report` 주간 집계 · 과거 시점 상태, `verify` 의 되돌릴 수 있는 DDL 판정 | 아니오 | 18 |
| `test_collector_it.py` | 같은 지문이 여러 스키마에 있을 때 · 같은 날 두 번 수집할 때 집계가 맞는지 (실제로 만난 장애의 재현) | **예** (order-db 3307) | 2 |

## 준비물

- `lab/.venv` (테스트가 `pymysql` 을 쓰는 스크립트를 불러옵니다)
- 통합 테스트만: 실습 MySQL 이 떠 있을 것

## 따라 하기

1. **단위 테스트** — `lab` 폴더에서 (DB 없이 됩니다):

   ```bash
   cd lab
   .venv/bin/python -m unittest discover -s tests
   ```

   ```
   ss..................
   ----------------------------------------------------------------------
   Ran 20 tests in 0.020s

   OK (skipped=2)
   ```

   `s` 와 `skipped=2` 는 아래 통합 테스트 2개가 꺼져 있어서입니다. 정상입니다.

2. **수집기 통합 테스트** — `lab` 폴더에서. order-db 에 임시 스키마를 만들고 테스트 쿼리를 실행한 뒤 지웁니다. performance_schema 집계가 늘어나므로 **37~39강 사례 실습을 마친 뒤** 실행하세요.

   ```bash
   LAB_IT=1 .venv/bin/python -m unittest tests.test_collector_it
   ```

   끝에 `OK` 가 나오면 통과입니다.

## 자주 막히는 곳

| 증상 | 원인 · 해결 |
|---|---|
| `ModuleNotFoundError: No module named 'pymysql'` | 가상 환경의 python(`.venv/bin/python`)으로 실행합니다 |
| `ImportError: Start directory is not importable` · 테스트 0개 | `lab` 폴더가 아닌 곳에서 실행했습니다. `cd lab` 후 다시 |
| 통합 테스트가 접속 오류 | order-db(3307)가 떠 있는지 `docker compose ps` 로 확인 |

## 다음 단계

- 스켈레톤 테스트: [skeleton/tests/README.md](../../skeleton/tests/README.md)
- 스크립트 사용법: [scripts/README.md](../scripts/README.md)
- 전체 순서도: [docs/GETTING_STARTED.md](../../docs/GETTING_STARTED.md)
