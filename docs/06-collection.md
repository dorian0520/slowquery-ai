# 06. 수집

## 목적

각 대상 서버의 `performance_schema.events_statements_summary_by_digest`(쿼리 지문별 **누적** 통계)를 읽어 저장소에 **스냅숏**으로 남깁니다. 하루치 실행분은 직전 스냅숏과의 차이로 구합니다([07 문서](07-aggregation.md)). 슬로우 로그 파일을 파싱하지 않으므로 서버 접속 권한만 있으면 됩니다.

## 관련 파일

| 파일 | 내용 |
|---|---|
| [lab/scripts/collector.py](../lab/scripts/collector.py) | 실습 수집기 (스냅숏 + 집계) |
| [lab/scripts/common.py](../lab/scripts/common.py) | 대상 접속 정보 `CLUSTERS`, 저장소 `STORE` |
| [lab/mysql/init/02_dba.sql](../lab/mysql/init/02_dba.sql) | `digest_snapshot` · `cmdb_cluster` |
| [skeleton/slowq/collect.py](../skeleton/slowq/collect.py) | 스켈레톤 수집기 |
| [lab/tests/test_collector_it.py](../lab/tests/test_collector_it.py) | 수집기 통합 테스트 |

## 동작 상세

### 1) 수집 대상 = CMDB

```python
cur.execute("SELECT cluster FROM cmdb_cluster WHERE collect = 1")
targets = [r["cluster"] for r in cur.fetchall() if r["cluster"] in CLUSTERS]
```

[collector.py:67-69](../lab/scripts/collector.py#L67). CMDB 의 `collect = 1` 이면서 `common.py` 에 접속 정보가 있는 클러스터만 수집합니다. 스켈레톤은 CMDB 의 `host` · `port` 로 바로 접속합니다([cli.py:15-18](../skeleton/slowq/cli.py#L15)).

### 2) 읽는 SQL과 제외 스키마

```sql
SELECT DIGEST, IFNULL(SCHEMA_NAME, ''), DIGEST_TEXT, COUNT_STAR, SUM_TIMER_WAIT, MAX_TIMER_WAIT, SUM_ROWS_EXAMINED
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
  AND SCHEMA_NAME NOT IN ('performance_schema', 'mysql', 'sys', 'dba')
```

[collector.py:9-16](../lab/scripts/collector.py#L9). `dba` 를 빼는 이유는 수집기 · 티켓 스크립트 자신의 쿼리가 섞이지 않게 하기 위해서입니다. `DIGEST_TEXT` 는 리터럴이 `?` 로 바뀐 정규화 문장이라 값이 저장되지 않습니다([02_dba.sql:25](../lab/mysql/init/02_dba.sql#L25)).

> `SCHEMA_NAME NOT IN (...)` 은 `SCHEMA_NAME` 이 NULL(기본 DB 없이 실행한 쿼리)이면 참이 아니므로, **lab 수집기는 기본 DB 없는 쿼리를 수집하지 않습니다.** 스켈레톤은 `IFNULL(SCHEMA_NAME, '')` 로 비교해 이 쿼리도 `''` 스키마로 수집합니다([skeleton collect.py:11-12](../skeleton/slowq/collect.py#L11)).

### 3) digest_snapshot 테이블

| 컬럼 | 의미 |
|---|---|
| `snap_at` | 수집 시각 (lab 은 초 단위 — [collector.py:65](../lab/scripts/collector.py#L65)) |
| `cluster` · `schema_name` · `digest` | 지문 식별 (64자 digest) |
| `digest_text` | 정규화 쿼리 |
| `count_star` · `sum_timer_wait` · `max_timer_wait` · `sum_rows_examined` | 누적값 (시간은 피코초) |

PK 는 `(snap_at, cluster, schema_name, digest)` — 같은 지문도 스키마별로 따로 집계되기 때문입니다([02_dba.sql:6-17](../lab/mysql/init/02_dba.sql#L6)). 저장은 `executemany` 한 번입니다([collector.py:20-29](../lab/scripts/collector.py#L20)).

### 4) 기준 스냅숏

차이를 구하려면 직전 스냅숏이 있어야 합니다.

- **lab**: 직전 스냅숏이 없으면(`prev` 가 NULL) 이번 누적값 **전체**를 그날 실행분으로 기록합니다([collector.py:49-51](../lab/scripts/collector.py#L49)). 그래서 `simulate.py` 는 시작 전날 날짜로 한 번 수집해 그 누적분을 1일차와 분리합니다([simulate.py:24](../lab/scripts/simulate.py#L24)). 직접 처음 수집할 때는 `--log-date 2000-01-01` 로 실행한 뒤 그 날짜 행을 지우라고 안내합니다([lab/README.md](../lab/README.md) 2장 · 5장).
- **skeleton**: 첫 실행은 기준 스냅숏만 남기고 일자 집계를 하지 않습니다(`return 0`) — [skeleton collect.py:56-57](../skeleton/slowq/collect.py#L56).

### 5) 재시작 처리

performance_schema 누적값은 서버 재시작이나 `TRUNCATE` 로 0 부터 다시 셉니다.

- **lab**: 현재 `count_star` 가 직전보다 작으면 리셋으로 보고 현재 값을 그대로 씁니다(`c.count_star < p.count_star`) — [collector.py:49-51](../lab/scripts/collector.py#L49).
- **skeleton**: 위 조건에 더해 `FIRST_SEEN` 이 바뀌어도 리셋으로 봅니다. 재시작 후 이미 직전 횟수를 넘어선 경우도 잡기 위해서입니다([skeleton collect.py:20-25](../skeleton/slowq/collect.py#L20)). 이를 위해 `digest_snapshot.first_seen` 컬럼이 있습니다([schema.sql:22](../skeleton/schema.sql#L22)).

### 6) lab 과 skeleton 차이 요약

| 항목 | lab collector.py | skeleton collect.py |
|---|---|---|
| 제외 스키마 | `performance_schema`, `mysql`, `sys`, `dba` (고정) | `mysql`, `sys`, `performance_schema`, `information_schema` + **저장소 DB 이름**(config `[store] database`) — [cli.py:29](../skeleton/slowq/cli.py#L29) |
| NULL 스키마 | 제외됨 | `''` 로 수집 |
| 첫 실행 | 누적값 전체를 그날로 기록 | 기준만 남김 |
| 리셋 감지 | 횟수 감소 | 횟수 감소 + `FIRST_SEEN` 변경 |
| `snap_at` | 초 단위 | 마이크로초 (`DATETIME(6)`, 같은 초 2회 실행 대비 — [L39](../skeleton/slowq/collect.py#L39)) |
| 차이 계산 위치 | SQL 한 문장 (LATERAL) | Python `delta_rows` |
| `max_timer_wait` | 저장 · `max_sec` 로 집계 | 수집하지 않음 |
| 실패 처리 | 예외가 나면 중단 | 클러스터 단위로 격리, 끝에 실패 목록 + 종료 코드 1 ([cli.py:26-35](../skeleton/slowq/cli.py#L26), [cli.py:67-68](../skeleton/slowq/cli.py#L67)) |

## 실행 방법

```bash
cd lab/scripts
../.venv/bin/python collector.py --log-date 2026-10-12     # 기본값은 오늘
```

스켈레톤: `python -m slowq --config config.ini daily --date <어제>` (수집이 daily 의 첫 단계).

## 확인 방법

- 출력: 클러스터마다 `2026-10-12 shop-db: digest N개 수집, 일자 집계 M건` 형식([collector.py:73](../lab/scripts/collector.py#L73)).
- 스냅숏 확인:

```sql
SELECT snap_at, cluster, COUNT(*) FROM dba.digest_snapshot GROUP BY snap_at, cluster ORDER BY snap_at DESC LIMIT 4;
```

- 통합 테스트(order-db 에 테스트 쿼리를 실행합니다): `LAB_IT=1 .venv/bin/python -m unittest tests.test_collector_it` — 같은 지문이 두 스키마에 있을 때와 같은 날 두 번 수집할 때를 검사합니다([test_collector_it.py:48](../lab/tests/test_collector_it.py#L48), [test_collector_it.py:67](../lab/tests/test_collector_it.py#L67)).

## 주의 · 운영 팁

- **스케줄링**: lab 에는 cron 설정이 없습니다(simulate · next_day 가 직접 호출). 운영은 스켈레톤 README 의 cron 예처럼 **자정 직후 하루 한 번, 어제 날짜로** 실행합니다 — `5 0 * * * ... daily --date $(date -d yesterday +\%F)` ([skeleton/README.md](../skeleton/README.md) 2장). 같은 날 두 번 수집해도 두 구간의 실행분이 더해지므로([07 문서](07-aggregation.md)) 중복 집계는 아닙니다.
- `my.cnf` 의 `event_scheduler = ON` 은 DB 안 이벤트로 수집하는 방법을 소개하기 위한 설정이며, 이 저장소에 수집용 이벤트 정의는 없습니다.
- `digest_snapshot` 은 금방 커집니다. 보관 기간을 짧게, `slow_digest_daily` 는 길게 둡니다([skeleton/README.md](../skeleton/README.md) 5장). 이 저장소에 삭제 작업 코드는 없습니다.
- 수집이 실패했다면 원인을 고친 뒤 기준 스냅숏을 다시 잡고 이어 갑니다(`--log-date 2000-01-01` 후 그 날짜 행 삭제).

## 다음 단계

→ [07. 집계](07-aggregation.md)
