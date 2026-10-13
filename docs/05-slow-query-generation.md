# 05. 슬로우 쿼리 발생

## 목적

인덱스가 없는 `shop` 데이터에 **느린 쿼리 6종 + 빠른 대조군 1종**을 섞어 실행하고, 14일치 운영 상황(평소 · 행사 급증 · 인덱스 추가로 해결 · 인덱스 삭제로 재발)을 몇 분 안에 재현합니다. 이 데이터로 수집 · 검출 · 티켓 · 추적 · 대시보드를 실습합니다.

## 관련 파일

| 파일 | 내용 |
|---|---|
| [lab/scripts/workload.py](../lab/scripts/workload.py) | 부하 발생기 (쿼리 7종) |
| [lab/scripts/simulate.py](../lab/scripts/simulate.py) | 14일 시나리오 |
| [lab/scripts/next_day.py](../lab/scripts/next_day.py) | 하루 진행 (사례 실습) |
| [lab/scripts/nplus1.py](../lab/scripts/nplus1.py) | N+1 재현과 해결 비교 (15강) |
| [lab/scripts/sqlrun.py](../lab/scripts/sqlrun.py) | 실습 SQL 실행기 |
| [lab/sql/](../lab/sql/) | 7~14강 실험 SQL · `reset.sql` |

## 동작 상세

### 1) workload.py — 쿼리 7종

정의: [workload.py:9-32](../lab/scripts/workload.py#L9). `(이름, SQL, 값 생성 함수, 기본 실행 횟수)`.

| 이름 | 기본 횟수 | 쿼리 요지 | 왜 느린가 |
|---|---|---|---|
| `user_recent_orders` | 40 | `WHERE user_id = ? ORDER BY ordered_at DESC LIMIT 20` | `user_id` 인덱스가 없어 200만 행 전체 스캔 + 정렬(filesort) |
| `coupon_usage` | 15 | `COUNT(*), SUM(amount) WHERE coupon_code = ?` (`CPN0`~`CPN499`) | `coupon_code` 인덱스 없음 → 전체 스캔 |
| `daily_status_count` | 10 | 하루 범위 `ordered_at` 조건 + `GROUP BY status` | `ordered_at` 인덱스 없음 → 전체 스캔 + 임시 테이블 |
| `deep_offset_paging` | 6 | `ORDER BY ordered_at DESC LIMIT {100000·300000·500000}, 20` | 정렬 인덱스 없음 + 깊은 OFFSET 만큼 읽고 버림 |
| `vip_monthly_sales` | 4 | `orders JOIN users WHERE grade='VIP' AND ordered_at >= ?` | 조인 · 조건 컬럼 인덱스 없음 |
| `email_search` | 20 | `email LIKE '%1234@%' LIMIT 10` | 앞쪽 `%` LIKE 는 인덱스를 쓸 수 없음 (users 20만 행 스캔) |
| `order_by_pk` | 300 | `WHERE order_id = ?` | **빠른 대조군** (PRIMARY 조회) |

`run(cluster, scale, only)` 는 root 로 접속해 각 쿼리를 `max(1, int(n * scale))` 번 실행합니다([workload.py:35-44](../lab/scripts/workload.py#L35)). `only` 로 특정 쿼리만 돌릴 수 있습니다.

> 실제로 어느 쿼리가 `평균 0.2초 · 5회` 발행 기준을 넘는지는 PC 성능에 따라 다릅니다. 동봉된 분석 결과([run1.txt](../lab/ai/run1.txt))에서는 마지막 날 shop-db 총 부하 상위가 `user_recent_orders`(평균 0.2692초) · `deep_offset_paging`(0.5463초) · `coupon_usage`(0.1774초) 였습니다.

### 2) simulate.py — 14일 시나리오

[simulate.py:22-43](../lab/scripts/simulate.py#L22).

- 시작일 `start = 오늘 - 13일`. 시작 전날 날짜로 `collector.main` 을 한 번 돌려 **기준 스냅숏**을 잡습니다([L24](../lab/scripts/simulate.py#L24)).
- 하루마다 순서: (DDL) → 부하 → 수집 → 발행 → 추적([L25-37](../lab/scripts/simulate.py#L25)).

| 일차 (`i`) | shop-db 부하 | 추가 동작 | 기대 결과 |
|---|---|---|---|
| 1~14일 (0~13) | `1.0 + 0.1 * (i % 3)` → 1.0 · 1.1 · 1.2 반복 | order-db 매일 0.5 | |
| 1일차 (0) | | | 첫 티켓 발행 |
| 8일차 (7) | | `coupon_usage` 만 scale 3.0 추가 실행 ([L32-33](../lab/scripts/simulate.py#L32)) | 행사 급증 → 급증 규칙 |
| 9일차 (8) | | `ALTER TABLE orders ADD INDEX ix_user_ordered (user_id, ordered_at)` ([L13](../lab/scripts/simulate.py#L13), [L27-28](../lab/scripts/simulate.py#L27)) | `user_recent_orders` 평균 급감 → RESOLVED |
| 12일차 (11) | | `ALTER TABLE orders DROP INDEX ix_user_ordered` ([L14](../lab/scripts/simulate.py#L14), [L29-30](../lab/scripts/simulate.py#L29)) | 평균 원복 → REOPENED |

`int(n * scale)` 때문에 예를 들어 1.1배 날에는 `user_recent_orders` 44회 · `coupon_usage` 16회이고, 8일차 쿠폰은 16 + 45 = 61회입니다. 이는 [run1.txt:9](../lab/ai/run1.txt#L9) 의 `exec_cnt=44`, [run1.txt:40](../lab/ai/run1.txt#L40) 의 `exec_cnt=61` 과 같습니다.

**날짜 대응표** — 강의 화면 날짜(2026-09-29 시작)를 내 날짜로 바꿔 쓰도록 마지막에 출력합니다([L38-43](../lab/scripts/simulate.py#L38)).

```
강의 날짜 → 내 날짜
  2026-09-29 → …  (1일차 · 첫 티켓 발행)
  2026-10-06 → …  (8일차 · 쿠폰 급증)
  2026-10-07 → …  (9일차 · 인덱스 추가(해결))
  2026-10-10 → …  (12일차 · 인덱스 삭제(재발))
  2026-10-12 → …  (14일차 · 마지막 날)
  2026-10-13 → …  (다음 날 · 37~39강 사례 실습)
```

표를 잃어버렸으면 `SELECT DATE(MIN(created_at)) FROM dba.tuning_ticket;` 가 1일차입니다.

`--help` 는 DB 를 건드리지 않고 도움말만 출력하며, 알 수 없는 인자는 거부합니다([L47](../lab/scripts/simulate.py#L47), 테스트 [test_ops.py:154-167](../lab/tests/test_ops.py#L154)).

### 3) next_day.py — 하루 진행

`workload.run("shop-db", 1.0)` → `workload.run("order-db", 0.5)` → `collector.main` → `tickets.issue` → `tickets.track` ([next_day.py:12-16](../lab/scripts/next_day.py#L12)). `--log-date` 가 필수입니다. 운영 반영 후 다음 날 효과를 보는 사례 실습에서 씁니다([10 문서](10-tracking-automation.md)).

### 4) nplus1.py — N+1 (15강)

VIP 회원 100명의 최근 주문 3건을 가져오는 두 방식을 비교합니다([nplus1.py](../lab/scripts/nplus1.py)).
- 시작 시 임시 인덱스 `ix_tmp_user_ordered (user_id, ordered_at)` 생성, 끝에서 삭제([L12](../lab/scripts/nplus1.py#L12), [L44](../lab/scripts/nplus1.py#L44)).
- ① N+1: 회원 목록 1번 + 회원마다 주문 1번 = 101번. performance_schema 의 해당 digest `COUNT_STAR` 증가량도 출력([L21-30](../lab/scripts/nplus1.py#L21)).
- ② 한 번에: `IN (...)` + `ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY ordered_at DESC)` 로 2번([L32-42](../lab/scripts/nplus1.py#L32)).

N+1 은 쿼리 하나하나가 빨라 평균 기준으로는 잘 안 잡히고, **실행 횟수(digest 증가량)** 로 드러난다는 점을 보여 줍니다.

### 5) lab/sql — 강의 실험 SQL

`sqlrun.py` 가 `;` 로 끝나는 줄 단위로 실행하고, `-- @` 로 시작하는 줄은 화면용 주석으로 출력합니다([sqlrun.py:31-55](../lab/scripts/sqlrun.py#L31)). 파일마다 만든 인덱스를 끝에서 지웁니다.

| 파일 | 실험 |
|---|---|
| [lesson07.sql](../lab/sql/lesson07.sql) | EXPLAIN type: const · ALL + filesort · ref · range · index |
| [lesson08.sql](../lab/sql/lesson08.sql) | EXPLAIN ANALYZE 로 실제 시간 (쿠폰 집계, 주문 목록, `user_id` 인덱스 전후) |
| [lesson09.sql](../lab/sql/lesson09.sql) | 풀 스캔 · filesort · temporary 가 나오는 이유 |
| [lesson10.sql](../lab/sql/lesson10.sql) | 조인 순서, `(user_id, ordered_at)` 인덱스, STRAIGHT_JOIN |
| [lesson11.sql](../lab/sql/lesson11.sql) | 복합 인덱스 컬럼 순서 `(ordered_at,user_id)` · `(user_id)` · `(user_id,ordered_at)` |
| [lesson12.sql](../lab/sql/lesson12.sql) | 커버링 인덱스 `(coupon_code, amount)`, 하루치 status 집계 인덱스 비교 |
| [lesson13.sql](../lab/sql/lesson13.sql) | 인덱스를 못 타는 7가지 패턴 |
| [lesson14.sql](../lab/sql/lesson14.sql) | 깊은 OFFSET → 키셋 페이징, 상관 서브쿼리 → 조인 |
| [reset.sql](../lab/sql/reset.sql) | 남은 임시 · 반영 · 검증 인덱스 일괄 삭제 + 남은 인덱스 확인 |

## 실행 방법

```bash
cd lab
.venv/bin/python scripts/simulate.py                        # 14일 재현 (수 분)
.venv/bin/python scripts/workload.py --cluster shop-db --scale 1.0 --only coupon_usage   # 부하만 따로
.venv/bin/python scripts/next_day.py --log-date <다음 날>
.venv/bin/python scripts/sqlrun.py < sql/lesson11.sql
.venv/bin/python scripts/nplus1.py
.venv/bin/python scripts/sqlrun.py --keep-going < sql/reset.sql   # 검증 DB 는 --port 3307
```

## 확인 방법

- simulate 출력: 날마다 `<날짜> shop-db: digest N개 수집, 일자 집계 M건`([collector.py:73](../lab/scripts/collector.py#L73)), `발행: [슬로우쿼리] ...`, `#1 해결 확인 ...`, `#1 재발 → 다시 열림` 등이 나오고 마지막에 날짜 대응표가 나오면 정상입니다.
- 결과 확인:

```sql
SELECT log_date, exec_cnt, ROUND(avg_sec,4) FROM dba.slow_digest_daily
 WHERE cluster='shop-db' AND qhash LIKE '5e9245c3%' ORDER BY log_date;   -- 9~11일차만 평균이 크게 낮음
SELECT ticket_id, cluster, LEFT(qhash,8), status FROM dba.tuning_ticket;
```

(`5e9245c3…` 는 동봉 결과에서 `user_recent_orders` 의 지문입니다 — [verify.py:13-14](../lab/ai/verify.py#L13).)

## 주의 · 운영 팁

- simulate 는 실습 DB 에 씁니다. 중간에 실패하면 다시 돌리지 말고 처음부터 다시(`docker compose down -v`) 초기화합니다. 끊겨서 `ix_user_ordered` 가 남았으면 `reset.sql` 로 지웁니다([reset.sql:5](../lab/sql/reset.sql#L5)).
- simulate 가 이미 9 · 12일차 `track` 을 실행했습니다. 강의 화면의 같은 `track` 명령을 다시 치면 티켓 상태가 바뀌어 사례 실습이 막힐 수 있습니다([lab/README.md](../lab/README.md) 2장).
- 실습 SQL 의 실행 시간은 PC 마다 다릅니다. EXPLAIN 의 type · key 는 같아야 하고 rows 는 통계 추정치라 조금 다를 수 있습니다.

## 다음 단계

→ [06. 수집](06-collection.md)
