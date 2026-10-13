# 04. 모니터링 대시보드 구성

## 목적

`slow_digest_daily` · `tuning_ticket` · `cmdb_cluster` 만 읽어 **오늘 무엇이 느린지, 추세가 어떤지, 티켓이 실제로 효과를 냈는지**를 한 화면에서 봅니다. 대시보드 JSON 은 손으로 편집하지 않고 `make_dashboard.py` 로 생성합니다.

## 관련 파일

| 파일 | 내용 |
|---|---|
| [lab/grafana/make_dashboard.py](../lab/grafana/make_dashboard.py) | 변수 9개 · 패널 8개 정의, JSON 출력 |
| [lab/grafana/dashboards/slowquery.json](../lab/grafana/dashboards/slowquery.json) | 생성 결과 (uid `lab-slowquery`) |

## 동작 상세

### 공통 필터 FILT

```python
FILT = ("d.cluster IN (${cluster:sqlstring}) AND c.realm IN (${realm:sqlstring}) "
        "AND c.tag IN (${tag:sqlstring}) AND d.avg_sec >= ${min_sec} AND d.exec_cnt >= ${min_q}")
BASE = f"FROM slow_digest_daily d JOIN cmdb_cluster c ON c.cluster = d.cluster WHERE {FILT}"
```

[make_dashboard.py:5-6](../lab/grafana/make_dashboard.py#L5), [make_dashboard.py:28](../lab/grafana/make_dashboard.py#L28). `BASE`(=FILT) 를 쓰는 패널은 **1 · 2 · 5 · 6** 입니다. 그래서 상단 `최소 평균(초)` · `최소 횟수` 를 바꾸면 이 네 패널이 함께 바뀝니다.

### 변수 9개

정의: [make_dashboard.py:69-79](../lab/grafana/make_dashboard.py#L69).

| # | name | 화면 이름 | 종류 | 값 / 쿼리 | 기본값 |
|---|---|---|---|---|---|
| 1 | `realm` | 환경 | query, 다중 · All | `SELECT DISTINCT realm FROM cmdb_cluster` | All |
| 2 | `tag` | 업무 | query, 다중 · All | `realm` 에 속한 `tag` | All |
| 3 | `cluster` | 클러스터 | query, 다중 · All | `realm` · `tag` 에 속한 `cluster` | All |
| 4 | `log_date` | 일자 | query, 단일 | `slow_digest_daily` 의 날짜 내림차순 | (첫 값) |
| 5 | `min_sec` | 최소 평균(초) | custom | `0,0.1,0.2,0.5,1` | 0.2 |
| 6 | `min_q` | 최소 횟수 | custom | `1,5,10,30` | 5 |
| 7 | `sort` | 정렬 | custom | `load : d.total_sec`, `count : d.exec_cnt`, `avg : d.avg_sec` | load |
| 8 | `days` | 기간(일) | custom | `7,14,30` | 14 |
| 9 | `qhash` | 쿼리 | query, 단일 | 선택 일자의 총 부하 상위 20개 `qhash` | (첫 값) |

- 1→2→3 은 CMDB 를 따라 연쇄 필터됩니다. 다중 선택값은 `${var:sqlstring}` 으로 따옴표가 붙어 `IN (...)` 에 들어갑니다.
- `min_sec` 0.2 · `min_q` 5 기본값은 실습 발행 기준([tickets.py:9-10](../lab/scripts/tickets.py#L9))과 같습니다.
- query 변수는 `refresh: 1` (대시보드 로드 시 갱신) — [make_dashboard.py:10](../lab/grafana/make_dashboard.py#L10).

### 패널 8개

정의: [make_dashboard.py:29-64](../lab/grafana/make_dashboard.py#L29). 배치는 24칸 그리드 기준 `(x, y, w, h)`.

| id | 제목 | 종류 · 위치 | SQL 이 하는 일 | 쓰는 변수 |
|---|---|---|---|---|
| 1 | 검출된 슬로우 쿼리 | stat (0,0,6,4) | 선택 일자에 필터를 통과한 지문 수 `COUNT(*)` — [L30](../lab/grafana/make_dashboard.py#L30) | FILT, log_date |
| 2 | 총 부하 (초) | stat (6,0,6,4) | 같은 범위의 `SUM(total_sec)` — [L31](../lab/grafana/make_dashboard.py#L31) | FILT, log_date |
| 3 | 열린 티켓 | stat (12,0,6,4) | `status IN ('OPEN','IN_PROGRESS','REOPENED')` 수 — [L32-34](../lab/grafana/make_dashboard.py#L32) | cluster |
| 4 | 해결 확인된 티켓 | stat (18,0,6,4) | `status='RESOLVED'` 수 — [L35-36](../lab/grafana/make_dashboard.py#L35) | cluster |
| 5 | 슬로우 쿼리 순위 | table (0,4,24,10) | 클러스터 · 업무 · qhash · 실행횟수 · 총부하 · 평균 · 최대 · 읽은 행 · 티켓 상태 · 담당팀 · 쿼리 앞 120자, `ORDER BY ${sort} DESC LIMIT 50`. `tuning_ticket` 을 LEFT JOIN 해 티켓이 없으면 `-` — [L37-44](../lab/grafana/make_dashboard.py#L37) | FILT, log_date, sort |
| 6 | 총 부하 상위 5개 쿼리 추이 | timeseries (0,14,12,9) | 최근 `days` 일 동안 `SUM(total_sec)` 상위 5개 지문의 일자별 총 부하 — [L45-51](../lab/grafana/make_dashboard.py#L45) | FILT, days |
| 7 | 선택한 쿼리 평균 실행 시간 | timeseries (12,14,12,9) | 선택한 `qhash` 의 일자별 `avg_sec`, 클러스터별 선 — [L52-55](../lab/grafana/make_dashboard.py#L52) | qhash, days |
| 8 | 티켓 추적 — 개선 효과 | table (0,23,24,9) | 티켓별 상태 · 담당자 · 기준 평균 · **선택 일자의** 평균 · 개선율(`RESOLVED` 일 때 `100*(1 - after/baseline)`) · 발행일 · 해결일, `updated_at` 최신순 — [L56-63](../lab/grafana/make_dashboard.py#L56) | cluster, log_date |

세부 동작:
- 패널 6 의 상위 5개 선정 서브쿼리는 FILT 없이 **전체 클러스터** 기준으로 고르고, 바깥 쿼리에서 FILT 를 적용합니다([L48-50](../lab/grafana/make_dashboard.py#L48)).
- 패널 7 은 클러스터 필터를 쓰지 않습니다. 같은 지문이 두 클러스터에 있으면 선이 두 개 나옵니다.
- 패널 3 · 4 는 **현재 상태**를 셉니다(선택 일자 기준이 아님). 특정 날짜 시점의 상태는 주간 리포트가 이벤트로 되짚습니다([10 문서](10-tracking-automation.md)).
- 패널 8 의 `현재평균초` 는 해결 당시 값이 아니라 선택한 일자 값입니다(주석 [L60](../lab/grafana/make_dashboard.py#L60)).
- 기간 패널(6 · 7)은 Grafana 시간 범위가 아니라 `CURDATE() - INTERVAL ${days} DAY` 로 자릅니다. 대시보드 시간 범위는 `now-14d ~ now` 로 저장돼 있지만([L68](../lab/grafana/make_dashboard.py#L68)) 쿼리에서 시간 매크로를 쓰지 않습니다.

## 실행 방법 — JSON 다시 만들기

```bash
cd lab/grafana
python3 make_dashboard.py        # → written dashboards/slowquery.json
```

[make_dashboard.py:82-84](../lab/grafana/make_dashboard.py#L82). 절대 경로 대신 상대 경로만 출력합니다. 파일이 바뀌면 Grafana 의 파일 provider 가 다시 읽습니다(바로 반영되지 않으면 Grafana 를 재시작).

## 확인 방법 — 매일 보는 순서

1. **일자**를 어제(수집한 날)로 고릅니다.
2. 상단 stat: `검출된 슬로우 쿼리` · `총 부하` 가 평소보다 큰지 봅니다. `열린 티켓` 이 줄지 않고 쌓이면 처리 지연입니다.
3. **순위 표(패널 5)**: 기본 정렬 `load`(총 부하)로 상위부터 봅니다. `티켓` 열이 `-` 인데 상위에 있는 쿼리는 발행 기준(평균 · 횟수) 밑이거나 하루 상한(TOP_N 10)에 밀린 것입니다. `정렬` 을 `count` 로 바꾸면 급증, `avg` 로 바꾸면 1회당 느린 쿼리가 위로 옵니다.
4. **추이(패널 6)**: 특정 날 튀는 선이 있으면 그 지문을 `쿼리` 변수로 골라 **패널 7** 에서 평균 시간이 같이 올랐는지(악화) 횟수만 늘었는지(급증) 구분합니다.
5. **티켓 추적(패널 8)**: `RESOLVED` 의 개선율, `REOPENED` 로 되돌아온 티켓을 확인합니다.

시뮬레이션 데이터 기준으로는 8일차 쿠폰 쿼리 급증, 9일차 인덱스 추가 후 `user_recent_orders` 평균 급감, 12일차 인덱스 삭제 후 재발이 패널 6 · 7 · 8 에 보입니다([05 문서](05-slow-query-generation.md)).

## 주의 · 운영 팁

- 시뮬레이션 후 2주가 지나면 추이 패널이 비어 보입니다. `기간(일)` 을 30 으로 바꿉니다.
- 운영 기준이 다르면 `custom("min_sec", ...)` 기본값(0.2)과 선택지를 운영 기준에 맞게 바꿉니다(스켈레톤 운영 기준 예: 0.5초 · 30회 — [config.example.ini:21-22](../skeleton/config.example.ini#L21)).
- 스켈레톤 스키마로 옮길 때: `slow_digest_daily.max_sec` 와 `tuning_ticket.updated_at` 이 없으므로 패널 5 의 `최대초` 와 패널 8 의 정렬을 고쳐야 합니다([skeleton/README.md](../skeleton/README.md) 5장).

## 다음 단계

→ [05. 슬로우 쿼리 발생](05-slow-query-generation.md)
