# skeleton/tests — 스켈레톤 테스트

`slowq` 패키지가 의도대로 동작하는지 확인하는 테스트입니다. 내 환경에 맞게 코드를 고쳤다면 **고친 뒤 반드시 한 번** 돌려서 기존 동작이 깨지지 않았는지 봅니다.

## 파일

| 파일 | 무엇을 확인하나 | DB 필요 | 개수 |
|---|---|---|---|
| `test_unit.py` | 수집 차이 계산(재시작 감지 포함) · 검출 규칙 · 마스킹 · 티켓 상태 전이 · AI 출력 JSON 파싱 · `claude` 명령 옵션 · 검증 판정 등 순수 로직 | 아니오 | 34 |
| `test_integration.py` | 실습 DB 에서 수집 → 검출 → 발행 → 추적 파이프라인 · 하루 발행 상한 · 저장소 스키마 제외 · `daily` 명령 전체 · 같은 초에 두 번 수집 | **예** (order-db 3307) | 5 |

통합 테스트는 order-db 에 별도 스키마 `slowq_it` 를 만들고 끝나면 지웁니다.

## 준비물

- `skeleton/requirements.txt` 설치 (`pymysql` · `cryptography`). 실습 환경이 있다면 `lab/.venv` 를 그대로 써도 됩니다.
- 통합 테스트만: [lab/README.md](../../lab/README.md) 1장의 실습 MySQL 이 떠 있을 것

## 따라 하기

1. **단위 테스트** — `skeleton` 폴더에서 (DB 없이 됩니다):

   ```bash
   cd skeleton
   python -m unittest discover -s tests
   ```

   ```
   sssss..................................
   ----------------------------------------------------------------------
   Ran 39 tests in 0.000s

   OK (skipped=5)
   ```

   `s` 다섯 개(`skipped=5`)는 통합 테스트가 꺼져 있어서입니다. 정상입니다.

2. **통합 테스트** — `skeleton` 폴더에서, 실습 DB 가 떠 있을 때:

   ```bash
   SLOWQ_IT=1 python -m unittest discover -s tests
   ```

   끝에 `Ran 39 tests` · `OK` 가 나오면 통과입니다. root 비밀번호가 실습 값(`lab-root-pw`)과 다르면 `SLOWQ_IT_PASSWORD=…` 를 함께 줍니다.

## 자주 막히는 곳

| 증상 | 원인 · 해결 |
|---|---|
| `ModuleNotFoundError: No module named 'slowq'` | `skeleton` 폴더 밖에서 실행했습니다. `cd skeleton` 후 다시 |
| `No module named 'pymysql'` | `pip install -r requirements.txt` 또는 `../lab/.venv/bin/python -m unittest discover -s tests` |
| 통합 테스트 접속 오류 | order-db(3307)가 떠 있는지 `lab` 에서 `docker compose ps` 로 확인 |
| 통합 테스트가 중간에 끊겨 `slowq_it` 스키마가 남음 | 3307 에 root 로 접속해 `DROP DATABASE slowq_it;` |

## 다음 단계

- 스켈레톤 설치 · 매일 실행: [skeleton/README.md](../README.md)
- 실습 코드 테스트: [lab/tests/README.md](../../lab/tests/README.md)
- 전체 순서도: [docs/GETTING_STARTED.md](../../docs/GETTING_STARTED.md)
