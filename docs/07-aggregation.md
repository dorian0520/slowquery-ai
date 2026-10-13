# 07. 집계

## 목적

스냅숏 두 개의 차이로 **하루치 실행분**을 구해 `slow_digest_daily`(일자 × 클러스터 × 지문)에 쌓고, 그 위에서 **검출 규칙**(기준초과 · 신규 · 악화 · 급증)을 적용합니다. 분석 · AI 전달 전에 쿼리 원문 값을 지우는 마스킹도 이 단계에서 다룹니다.

## 관련 파일

| 파일 | 내용 |
|---|---|
| [lab/scripts/collector.py](../lab/scripts/collector.py) | `aggregate()` — 차이 계산 · 일자 집계 |
| [lab/mysql/init/02_dba.sql](../lab/mysql/init/02_dba.sql) | `slow_digest_daily` |
| [lab/scripts/detect.py](../lab/scripts/detect.py) | 실습 검출 규칙 (SQL 한 문장) |
| [skeleton/slowq/detect.py](../skeleton/slowq/detect.py) | 스켈레톤 검출 규칙 (Python) |
| [skeleton/config.example.ini](../skeleton/config.example.ini) | 운영 기준값 `[rules]` |
| [lab/scripts/mask.py](../lab/scripts/mask.py) · [skeleton/slowq/mask.py](../skeleton/slowq/mask.py) | 리터럴 마스킹 |

## 동작 상세

### 1) 스냅숏 차이 → slow_digest_daily

[collector.py:32-61](../lab/scripts/collector.py#L32).

1. 같은 클러스터의 직전 스냅숏 시각 `prev = MAX(snap_at) WHERE snap_at < 이번` ([L35-37](../lab/scripts/collector.py#L35)).
2. 이번 스냅숏 `c` 와 직전 스냅숏 `p` 를 `(cluster, schema_name, digest)` 로 LEFT JOIN 하고, `JOIN LATERAL` 로 차이를 계산합니다([L44-52](../lab/scripts/collector.py#L44)):

```sql
IF(p.count_star IS NULL OR c.count_star < p.count_star, c.count_star, c.count_star - p.count_star) cnt
-- sum_timer_wait · sum_rows_examined 도 같은 규칙
```

   직전 값이 없거나(새 지문 · 첫 수집) 횟수가 줄었으면(재시작) 이번 값 전체를 씁니다. `d.cnt > 0` 인 지문만 남깁니다([L53](../lab/scripts/collector.py#L53)).
3. **스키마를 합쳐** 지문당 하루 한 행으로 만듭니다 — `GROUP BY x.cluster, x.digest` ([L55](../lab/scripts/collector.py#L55)). `schema_name` · `query_text` 는 `MIN()` 값을 씁니다.

| 컬럼 | 계산 | 단위 |
|---|---|---|
| `qhash` | `LEFT(digest, 32)` | |
| `exec_cnt` | `SUM(cnt)` | 회 |
| `total_sec` | `SUM(wait) / 1e12` (총 부하) | 초 |
| `avg_sec` | `SUM(wait) / 1e12 / SUM(cnt)` | 초 |
| `max_sec` | `MAX(c.max_timer_wait) / 1e12` | 초 |
| `rows_examined` | `SUM(rows_ex)` | 행 |

[collector.py:41-42](../lab/scripts/collector.py#L41), 피코초 상수 `PS = 1e12` ([L17](../lab/scripts/collector.py#L17)).

> `max_sec` 은 차이가 아니라 **이번 스냅숏의 누적 최댓값**(서버 기동 이후 최댓값)입니다. MAX 는 차이를 낼 수 없는 값이기 때문입니다. 그날의 최댓값으로 읽지 않도록 주의합니다. 스켈레톤 스키마에는 이 컬럼이 없습니다.

4. **같은 날 두 번 수집**하면 두 구간 실행분을 더합니다([L56-59](../lab/scripts/collector.py#L56)):

```sql
ON DUPLICATE KEY UPDATE
  exec_cnt = exec_cnt + VALUES(exec_cnt), total_sec = total_sec + VALUES(total_sec),
  avg_sec = total_sec / exec_cnt, max_sec = GREATEST(max_sec, VALUES(max_sec)),
  rows_examined = rows_examined + VALUES(rows_examined)
```

   MySQL 은 `ON DUPLICATE KEY UPDATE` 의 대입을 왼쪽부터 적용하므로 `avg_sec` 는 이미 더해진 `total_sec / exec_cnt` 로 다시 계산됩니다. 스켈레톤도 같은 방식입니다([skeleton collect.py:59-63](../skeleton/slowq/collect.py#L59)).

`slow_digest_daily` 의 PK 는 `(log_date, cluster, qhash)`, 보조 인덱스 `ix_qhash (qhash, log_date)` 로 지문 추이 조회를 받칩니다([02_dba.sql:20-33](../lab/mysql/init/02_dba.sql#L20)).

### 2) 검출 규칙 (lab detect.py)

기준값([detect.py:8-11](../lab/scripts/detect.py#L8)):

| 상수 | 값 | 뜻 |
|---|---|---|
| `MIN_SEC`, `MIN_Q` | 0.2초, 5회 | 기준 초과 (실습 PC 기준) |
| `BASE_DAYS` | 7 | 비교 기간 |
| `WORSE_RATIO` | 2.0 | 직전일 대비 평균 2배 → 악화 |
| `SPIKE_RATIO` | 2.0 | 기준 기간 평균 횟수 대비 2배 → 급증 |

SQL 구조([detect.py:13-39](../lab/scripts/detect.py#L13)):
- `today` = 그날 행, `prev` = **직전일 하루**의 평균, `base` = 직전 7일(`d-7 ≤ log_date < d`)의 `AVG(exec_cnt)` · `AVG(avg_sec)` · 일수.
- `today LEFT JOIN base LEFT JOIN prev` 후 규칙 이름을 `CONCAT_WS(',')` 로 붙이고 `HAVING rules <> ''`, 총 부하 내림차순.

| 규칙 | 조건 (SQL 그대로) | 줄 |
|---|---|---|
| 기준초과 | `t.avg_sec >= 0.2 AND t.exec_cnt >= 5` | [L29](../lab/scripts/detect.py#L29) |
| 신규 | `b.qhash IS NULL AND t.exec_cnt >= 5` (직전 7일에 한 번도 없던 지문) | [L30](../lab/scripts/detect.py#L30) |
| 악화 | `p.avg_sec > 0 AND t.avg_sec >= p.avg_sec * 2 AND t.avg_sec >= 0.2 AND t.exec_cnt >= 5` | [L31](../lab/scripts/detect.py#L31) |
| 급증 | `b.cnt > 0 AND t.exec_cnt >= b.cnt * 2 AND t.total_sec >= 1` (총 부하 1초 이상) | [L32](../lab/scripts/detect.py#L32) |
| 제외 | `query_text NOT REGEXP '^(ALTER|CREATE|DROP|TRUNCATE|SET|SHOW|ANALYZE)'` — 일회성 관리 작업 | [L36](../lab/scripts/detect.py#L36) |

- 악화는 기준초과 조건을 포함하므로, 악화로 잡힌 쿼리는 항상 기준초과이기도 합니다.
- 급증의 기준 횟수는 **실행된 날들의 평균**입니다(`AVG(exec_cnt)` 는 행이 있는 날만 셈).
- 악화의 비교 대상은 7일 평균이 아니라 직전일입니다(주석 "평균이 섞이지 않은 비교 대상" — [L17](../lab/scripts/detect.py#L17)).
- lab `detect.py` 는 결과를 **출력만** 합니다. simulate · next_day 는 이 스크립트를 부르지 않고 `tickets.issue` 가 기준초과와 같은 조건으로 따로 발행합니다([09 문서](09-ticket.md)).

### 3) 검출 규칙 (skeleton) — 운영 기준

`[rules]` 기본값: `min_sec = 0.5`, `min_q = 30`, `worse_ratio = 2.0`, `spike_ratio = 2.0`, `spike_min_total = 1.0`, `top_n = 10` ([config.example.ini:20-26](../skeleton/config.example.ini#L20)). 실습 환경에서 돌릴 때는 0.2 · 5 로 바꿉니다([skeleton/README.md](../skeleton/README.md) 1장).

lab 과 다른 점([skeleton detect.py:16-39](../skeleton/slowq/detect.py#L16)):
- 제외 패턴에 `RENAME` · `OPTIMIZE` 추가, 앞 공백 · 대소문자 무시([L4](../skeleton/slowq/detect.py#L4)).
- **신규**는 지난 7일 이력이 있는 클러스터에서만 판정합니다. 이력이 전혀 없으면(`known` 이 비면) 신규 판정을 생략합니다 — 수집 첫 주에 모든 쿼리가 신규로 쏟아지지 않게([L29](../skeleton/slowq/detect.py#L29), [L48-51](../skeleton/slowq/detect.py#L48)).
- 급증 총 부하 하한이 설정값(`spike_min_total`)입니다.
- 결과는 `reasons` 목록을 단 dict 로 돌려주고, 그대로 발행 입력이 됩니다.

### 4) 마스킹 (mask.py)

[mask.py:8-19](../lab/scripts/mask.py#L8) — 순서대로 치환합니다.

| 패턴 | 바꿈 |
|---|---|
| 작은따옴표 문자열 (이메일 · 이름 · 전화번호 포함) | `'?'` |
| 큰따옴표 문자열 | `"?"` |
| 16진수 `0x…` | `?` |
| 숫자 (컬럼 이름 속 숫자 · 백틱 이름은 제외) | `?` |

- `slow_digest_daily.query_text` 는 이미 정규화된 digest 문장이라 값이 없습니다. 마스킹은 **원문 SQL**(예: `events_statements_history_long`)을 다루거나 AI 에 넘길 때 씁니다. `python3 mask.py` 는 실습 DB 최근 이력 3건의 마스킹 전후를 보여 줍니다([mask.py:22-30](../lab/scripts/mask.py#L22)).
- MCP 서버의 `explain` 결과에는 **문자열 패턴만** 적용합니다. 숫자까지 지우면 rows · cost 근거가 사라지기 때문입니다([labdb_mcp.py:59-60](../lab/ai/labdb_mcp.py#L59)).
- 스켈레톤 `mask.py` 는 같은 패턴입니다([skeleton mask.py:4-9](../skeleton/slowq/mask.py#L4)).

## 실행 방법

```bash
cd lab/scripts
../.venv/bin/python collector.py --log-date <날짜>     # 수집 + 집계
../.venv/bin/python detect.py --log-date <날짜>        # 검출 결과 출력
../.venv/bin/python mask.py                            # 마스킹 데모
```

## 확인 방법

- `detect.py` 출력 형식([detect.py:47-50](../lab/scripts/detect.py#L47)):

```
[<날짜>] 검출 N건
  <cluster> <qhash 8자리>  <규칙,규칙>  오늘 <횟수>회 <평균>s  | 기준 <7일 평균 횟수 또는 ->회 · 직전일 <평균 또는 ->s  <쿼리 앞 40자>
```

  8일차 날짜를 주면 쿠폰 쿼리에 `급증` 이, 12일차 날짜를 주면 `user_recent_orders` 에 `악화` 가 붙는 것이 시나리오상 기대값입니다.
- 집계 검산: `SELECT SUM(exec_cnt), SUM(total_sec) FROM dba.slow_digest_daily WHERE log_date=… AND cluster='shop-db';`

## 주의 · 운영 팁

- 실습 기준 0.2초 · 5회는 실습 PC 규모에 맞춘 값입니다. 운영은 보통 0.5~1초로 두고 처음 1~2주는 dry-run 결과를 보며 조정합니다([skeleton/README.md](../skeleton/README.md) 5장).
- 신규 · 급증은 발행 대상이 아니라 **사람이 보는 검출 목록**입니다. 해결 판정이 평균 시간 기준이기 때문입니다([skeleton tickets.py:18-20](../skeleton/slowq/tickets.py#L18)).

## 다음 단계

→ [08. 진단](08-diagnosis.md)
