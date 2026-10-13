# lab/scripts — 부하 · 수집 · 검출 · 티켓 · 반영 · 리포트 스크립트

슬로우 쿼리 자동화의 **하루 일과**를 하나씩 손으로 돌려 보는 파이썬 스크립트 모음입니다. 모두 실습 DB(`shop-db` 3306 · `order-db` 3307)와 저장소 `dba` 에 맞춰져 있습니다.

## 파일

| 파일 | 역할 | 언제 쓰나 |
|---|---|---|
| `common.py` | 접속 정보(`CLUSTERS` · `STORE = "shop-db"`)와 `connect()` | 직접 실행하지 않음 — 다른 스크립트가 불러 씀 |
| `simulate.py` | 14일치 운영 상황 재현 (부하 → 수집 → 발행 → 추적을 14번, 9일차 인덱스 추가 · 12일차 삭제) | **환경을 띄운 직후 한 번** |
| `workload.py` | 느린 쿼리 6종 + 빠른 쿼리 1종을 섞어 실행 (`--cluster` · `--scale` · `--only`) | 부하를 더 주고 싶을 때 (출력 없음) |
| `collector.py` | performance_schema digest 스냅숏 → 직전 스냅숏과의 차이 → 일자 집계 (`--log-date`) | 수집 단계를 따로 볼 때 |
| `detect.py` | 검출 규칙 4종(기준초과 · 신규 · 악화 · 급증) 결과 출력 (`--log-date`) | 그날 무엇이 걸렸는지 볼 때 (DB 를 바꾸지 않음) |
| `mask.py` | 쿼리 원문 속 값을 `?` 로 지운 전후 비교 | 마스킹 확인 (19강) |
| `tickets.py` | `issue` 티켓 발행(중복 방지 · CMDB 담당자) · `track` 해결 · 재발 판정 (`--log-date`) | 발행 · 추적 단계 |
| `publish.py` | `attach` AI 분석 · 실측 검증 결과를 티켓에 첨부 · `payload` Jira/Slack 본문 미리보기(dry-run) | AI 분석 뒤 · 알림 본문 확인 |
| `apply_fix.py` | `plan` 변경 계획 출력 · `apply` 온라인 DDL 반영 + 반영 중 조회 지연 측정 (`--ticket` · `--log-date`) | 운영 반영 실습 (37~39강) |
| `next_day.py` | 하루 진행: 부하 → 수집 → 발행 → 추적 (`--log-date` 필수) | 반영 다음 날 결과를 볼 때 |
| `report.py` | 주간 리포트 (`--end` · `--days`, 기본 7일) | 한 주 정리 |
| `sqlrun.py` | `sql/*.sql` 을 읽어 표로 출력하는 실행기 | 7~14강 실습 SQL ([sql/README.md](../sql/README.md)) |
| `nplus1.py` | N+1 쿼리와 한 번에 읽기 비교 | 15강 |

## 준비물

- [lab/README.md](../README.md) 1장대로 MySQL 두 대가 떠 있고, `lab/.venv` 에 `requirements.txt` 가 설치돼 있어야 합니다.
- 어디서 실행하든 됩니다. 두 가지 방법 중 하나를 고르세요.
  - `lab` 폴더에서: `.venv/bin/python scripts/collector.py …`
  - `lab/scripts` 폴더에서: `../.venv/bin/python collector.py …`
  - 아래 예는 모두 **`lab` 폴더**에서 칩니다.

## 따라 하기

1. **14일 운영 상황 재현** (수 분)

   ```bash
   cd lab
   .venv/bin/python scripts/simulate.py
   ```

   중간에 `== 인덱스 추가`, `== 인덱스 삭제(재발 상황)` 와 날짜별 수집 · 발행 줄이 지나가고, 끝에 이런 표가 나옵니다.

   ```
   강의 날짜 → 내 날짜
     2026-09-29 → 2026-09-30  (1일차 · 첫 티켓 발행)
     ...
     2026-10-12 → 2026-10-13  (14일차 · 마지막 날)
     2026-10-13 → 2026-10-14  (다음 날 · 37~39강 사례 실습)
   ```

   **오른쪽 날짜**가 내 환경의 날짜입니다. 아래 명령에 쓰기 쉽게 셸 변수로 담아 둡니다(값은 내 표의 오른쪽 날짜로).

   ```bash
   LAST=2026-10-13   # 「마지막 날」 오른쪽 날짜
   NEXT=2026-10-14   # 「다음 날」 오른쪽 날짜
   ```

2. **그날 무엇이 걸렸나 보기** (DB 를 바꾸지 않음)

   ```bash
   .venv/bin/python scripts/detect.py --log-date $LAST
   ```

   ```
   [2026-10-13] 검출 3건
     shop-db  5e9245c3  기준초과         오늘   44회 0.269s  | 기준 40.3회 · 직전일 0.2701s  SELECT order_id , amount , status , orde
     ...
   ```

3. **알림 본문 미리보기** (실제로 보내지 않음) — 티켓 번호는 `SELECT ticket_id, cluster, LEFT(qhash,8) FROM dba.tuning_ticket;` 로 확인합니다.

   ```bash
   .venv/bin/python scripts/publish.py payload 1 --to jira     # 또는 --to slack
   ```

   ```
   # dry-run: jira 로 보낼 내용 (실제로 보내지 않음)
   {
     "fields": {
       "project": {"key": "DBTUNE"},
       ...
   ```

4. **AI 분석 결과 첨부** — `lab/ai` 에서 분석 · 실측 검증을 마친 뒤([ai/README.md](../ai/README.md)). 강사가 남긴 결과로 먼저 해 볼 수 있습니다.

   ```bash
   .venv/bin/python scripts/publish.py attach ai/run1.txt ai/verify_run1.txt --log-date $LAST
   ```

   ```
   #1 [5e9245c3] 실측 통과
   [f54ce51c] 티켓 없음 (발행 기준 미달) — 붙이지 않음
   ...
   ```

   (번호 · 줄 수는 PC 마다 다를 수 있습니다.)

5. **운영 반영 계획 → 반영** (5e9245c3 티켓 번호로)

   ```bash
   .venv/bin/python scripts/report.py --end $LAST                       # 반영 전 주간 리포트
   .venv/bin/python scripts/apply_fix.py plan  --ticket 1               # 아무것도 바꾸지 않음
   .venv/bin/python scripts/apply_fix.py apply --ticket 1 --log-date $NEXT
   ```

   `plan` 출력 끝이 `사전 점검 : … → 반영 가능` 이면 `apply` 를 진행합니다. `apply` 는 이렇게 끝납니다.

   ```
   반영 완료 : 2.84초
   반영 중 조회 1234회 · 중앙값 0.21 ms · 최대 3.10 ms
   사후 확인 : -> Index lookup on orders using ix_orders_user_ordered (user_id=1001) (reverse) ...
   티켓 #1 → IN_PROGRESS (다음 날 추적에서 해결 여부를 판정)
   ```

6. **다음 날 진행 → 해결 확인 → 주간 리포트**

   ```bash
   .venv/bin/python scripts/next_day.py --log-date $NEXT    # 부하 → 수집 → 발행 → 추적
   .venv/bin/python scripts/report.py --end $NEXT
   ```

   `next_day` 출력에 `#1 해결 확인 0.27s → 0.00s` 가 보이고, 리포트 첫 줄이 `# 슬로우 쿼리 주간 리포트 (… ~ …)` 이면 성공입니다.

## 자주 막히는 곳

| 증상 | 원인 · 해결 |
|---|---|
| `ModuleNotFoundError: No module named 'pymysql'` | 가상 환경 밖의 python 입니다. `.venv/bin/python` 으로 실행하거나 `source .venv/bin/activate` |
| `Can't connect to MySQL server on '127.0.0.1'` | DB 가 아직 안 떴습니다. `docker compose ps` · [mysql/README.md](../mysql/README.md) 2단계 |
| simulate 가 중간에 실패 | 다시 돌리지 말고 [lab/README.md](../README.md) 6장 「처음부터 다시」로 초기화 |
| `apply_fix.py` 가 `실측 검증을 통과하지 않은 제안입니다` · `AI 분석 · 검증 결과가 없습니다` 로 멈춤 (종료 코드 2) | 4단계 `attach` 를 먼저 합니다. 탈락한 제안은 자동 반영하지 않는 것이 정상 동작입니다 |
| `apply_fix.py` 가 `이미 같은 인덱스가 있습니다` | 이미 반영했습니다. 다시 해 보려면 `.venv/bin/python scripts/sqlrun.py --keep-going < sql/reset.sql` |
| `tickets.py track` 을 지난 날짜로 다시 쳤더니 티켓 상태가 이상하다 | simulate 가 이미 실행한 날짜입니다. 지난 날짜로 `track` 을 다시 치지 않습니다([lab/README.md](../README.md) 2장) |
| `publish.py attach` 에 `the following arguments are required: --log-date` | `attach` 는 `--log-date` 가 필수입니다 |

## 다음 단계

- AI 분석 · 실측 검증: [ai/README.md](../ai/README.md)
- 결과를 그래프로: [grafana/README.md](../grafana/README.md)
- 단계별 상세 설명: [06 수집](../../docs/06-collection.md) · [07 집계](../../docs/07-aggregation.md) · [09 티켓](../../docs/09-ticket.md) · [10 추적 · 반영](../../docs/10-tracking-automation.md)
- 전체 순서도: [docs/GETTING_STARTED.md](../../docs/GETTING_STARTED.md)
