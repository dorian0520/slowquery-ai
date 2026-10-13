# 09. 티켓 발행

## 목적

기준을 넘은 슬로우 쿼리를 **지문 하나당 티켓 하나**로 발행하고, 담당 팀 · 담당자 · 알림 채널을 CMDB 에서 정합니다. 외부 시스템(Jira · Slack)으로 보낼 본문은 **dry-run 으로 출력만** 합니다.

## 관련 파일

| 파일 | 내용 |
|---|---|
| [lab/scripts/tickets.py](../lab/scripts/tickets.py) | `issue` 발행 · `track` 추적 |
| [lab/scripts/publish.py](../lab/scripts/publish.py) | `payload` — Jira · Slack 본문 미리보기 (dry-run) |
| [lab/mysql/init/02_dba.sql](../lab/mysql/init/02_dba.sql) | `tuning_ticket` · `ticket_event` · `cmdb_cluster` |
| [skeleton/slowq/tickets.py](../skeleton/slowq/tickets.py) | 스켈레톤 발행 · 추적 |
| [skeleton/slowq/publish.py](../skeleton/slowq/publish.py) | `DryRunPublisher` |

## 동작 상세

### 1) 발행 기준 — 기준초과만

```sql
SELECT d.cluster, d.qhash, d.query_text, d.avg_sec, d.exec_cnt, d.total_sec,
       c.owner, c.owner_team, c.slack_channel
FROM slow_digest_daily d
JOIN cmdb_cluster c ON c.cluster = d.cluster AND c.collect = 1
LEFT JOIN tuning_ticket t ON t.cluster = d.cluster AND t.qhash = d.qhash
WHERE d.log_date = %s AND d.avg_sec >= %s AND d.exec_cnt >= %s AND t.ticket_id IS NULL
ORDER BY d.total_sec DESC LIMIT %s
```

[tickets.py:22-30](../lab/scripts/tickets.py#L22). 상수: `MIN_SEC = 0.2`, `MIN_Q = 5`, `TOP_N = 10` ([tickets.py:9-11](../lab/scripts/tickets.py#L9)).

- 조건은 검출 규칙의 **기준초과**와 같습니다(평균 ≥ 0.2초 **그리고** 하루 ≥ 5회). 악화는 기준초과 조건을 포함하므로 악화 쿼리도 발행됩니다. **신규 · 급증만으로는 발행하지 않습니다** — 해결 판정이 평균 시간 기준이라, 평균이 빠른 쿼리에 티켓을 열면 닫을 기준이 없기 때문입니다([skeleton tickets.py:18-20](../skeleton/slowq/tickets.py#L18)).
- lab 은 이 SQL 자체가 조건을 갖고, 스켈레톤은 검출 결과의 `reasons` 에 `기준초과` 가 있는지로 고릅니다(`issuable` — [skeleton tickets.py:18-20](../skeleton/slowq/tickets.py#L18)).

### 2) 담당자 매핑 — CMDB

`cmdb_cluster` 와 조인해 `owner`(기본 담당자) · `owner_team` · `slack_channel` 을 가져옵니다. `collect = 0` 이거나 CMDB 에 없는 클러스터는 발행하지 않습니다([tickets.py:26](../lab/scripts/tickets.py#L26), [skeleton tickets.py:34-38](../skeleton/slowq/tickets.py#L34)). 실습 매핑: shop-db → 주문개발팀 / dev-kim / `#order-db-alert`, order-db → 정산개발팀 / dev-lee / `#settle-db-alert` ([02_dba.sql:83-84](../lab/mysql/init/02_dba.sql#L83)).

### 3) 중복 방지

- 스키마: `UNIQUE KEY uk_target (cluster, qhash)` — 같은 지문은 티켓 하나([02_dba.sql:50](../lab/mysql/init/02_dba.sql#L50)).
- lab: 조회 단계에서 `LEFT JOIN tuning_ticket ... AND t.ticket_id IS NULL` 로 이미 티켓이 있는 지문을 뺀 뒤 `LIMIT TOP_N` 을 겁니다. 그래서 이미 티켓이 있는 쿼리는 상한을 차지하지 않습니다.
- 스켈레톤: INSERT 를 시도해 `IntegrityError 1062`(UNIQUE 중복)만 건너뛰고 다른 오류는 그대로 올립니다. 상한은 **새로 발행한 건수만** 셉니다([skeleton tickets.py:27-51](../skeleton/slowq/tickets.py#L27)).
- 해결된 티켓의 쿼리가 다시 느려지면 새 티켓이 아니라 **같은 티켓을 REOPENED** 로 엽니다([10 문서](10-tracking-automation.md)).

### 4) 저장 내용

| 항목 | 값 | 코드 |
|---|---|---|
| `title` | `[슬로우쿼리] <cluster> <qhash 8자리> 평균 <avg>s × <횟수>회` | [tickets.py:33](../lab/scripts/tickets.py#L33) |
| `owner` | CMDB `owner` | [tickets.py:36](../lab/scripts/tickets.py#L36) |
| `baseline_avg_sec` | 발행일 평균 — 이후 해결 · 재발 판정의 기준 | [tickets.py:36](../lab/scripts/tickets.py#L36) |
| `created_at` | `<log_date> 09:00:00` | [tickets.py:36](../lab/scripts/tickets.py#L36) |
| `status` | 기본 `OPEN` | [02_dba.sql:41](../lab/mysql/init/02_dba.sql#L41) |
| `ticket_event` | `CREATED`, note `총 부하 Ns · 담당 팀/담당자 · 알림 채널` | [tickets.py:37-39](../lab/scripts/tickets.py#L37) |

스켈레톤의 `CREATED` note 는 검출 사유 목록 + 팀/담당자입니다([skeleton tickets.py:49](../skeleton/slowq/tickets.py#L49)).

### 5) 외부 발행 본문 — dry-run

`publish.py payload <ticket_id> --to jira|slack` 은 티켓 · CMDB · 쿼리 원문 · 분석 결과를 모아 **요청 본문을 출력만** 합니다. 첫 줄에 `# dry-run: jira 로 보낼 내용 (실제로 보내지 않음)` 이 찍힙니다([publish.py:79-80](../lab/scripts/publish.py#L79)). **HTTP 요청 · 토큰 처리 코드는 이 저장소에 없습니다.**

Jira 본문 구조([publish.py:61-74](../lab/scripts/publish.py#L61)):

| 필드 | 값 |
|---|---|
| `project.key` | `DBTUNE` (예시 키) |
| `issuetype.name` | `Task` |
| `summary` | 티켓 `title` |
| `labels` | `slow-query`, `<cluster>`, `qhash-<8자리>` — 같은 지문 중복 검색용 |
| `assignee.name` | 티켓 `owner` |
| `description` | 쿼리(마스킹 · 정규화 문장) · 기준 평균 · 담당 팀 · 원인(AI) · 근거 2개 · 제안 · 실측 검증(통과 / 탈락 · 사람 검토 / 없음) · 대시보드 링크 |

Slack 본문([publish.py:75-78](../lab/scripts/publish.py#L75)): `channel` = CMDB `slack_channel`, `text` = `[상태] 제목 → 팀 담당자`, 제안, 대시보드 링크. 대시보드 링크는 `http://localhost:3000/d/lab-slowquery?var-qhash=<qhash>` 로 패널 7 의 쿼리 변수를 채웁니다([publish.py:10](../lab/scripts/publish.py#L10)).

스켈레톤 `daily` 는 새로 발행한 티켓마다 `DryRunPublisher.publish()` 를 불러 `# dry-run (보내지 않음) {...}` 한 줄을 남깁니다([skeleton publish.py:5-12](../skeleton/slowq/publish.py#L5), [cli.py:39-41](../skeleton/slowq/cli.py#L39)).

### 6) 실제 전송을 붙이려면 (미구현 — 개요만)

> 아래는 **이 저장소에 구현되지 않은** 내용이며, 붙일 자리만 정리한 것입니다.

- 스켈레톤은 `publish(ticket)` 하나만 가진 어댑터 형태입니다. 같은 메서드를 가진 Jira · Slack 어댑터 클래스를 추가하고 `cli.daily` 의 `DryRunPublisher(out)` 를 바꿔 끼우는 구조를 의도합니다([skeleton publish.py:1](../skeleton/slowq/publish.py#L1)).
- 본문은 lab `publish.py payload` 의 구조를 출발점으로 쓰고, 옮길 때 대시보드 링크 · 프로젝트 키 `DBTUNE` 을 바꾸고 토큰은 비밀 저장소에 둡니다([skeleton/README.md](../skeleton/README.md) 5장 표).
- 중복 발행을 막으려면 외부 이슈 생성 전에 `qhash-<8자리>` 라벨로 기존 이슈를 찾는 단계가 필요합니다(라벨을 붙이는 이유 — [publish.py:65](../lab/scripts/publish.py#L65)).
- 처음 1~2주는 dry-run 결과로 기준을 조정한 뒤 전송을 켭니다.

## 실행 방법

```bash
cd lab/scripts
../.venv/bin/python tickets.py issue --log-date <날짜>
../.venv/bin/python publish.py payload 1 --to jira
../.venv/bin/python publish.py payload 1 --to slack
```

## 확인 방법

- `issue` 출력: 티켓마다 `발행: [슬로우쿼리] … → 주문개발팀`, 마지막에 `<날짜>: 신규 티켓 N건` ([tickets.py:40-41](../lab/scripts/tickets.py#L40)). 같은 날짜로 다시 실행하면 `신규 티켓 0건` 이어야 합니다(중복 방지).
- 저장 확인:

```sql
SELECT ticket_id, cluster, LEFT(qhash,8), status, owner, baseline_avg_sec, created_at FROM dba.tuning_ticket;
SELECT * FROM dba.ticket_event ORDER BY ticket_id, at;
```

- `payload` 출력이 `# dry-run: …` 다음 JSON 이면 정상. 분석 전 티켓은 원인 `분석 전`, 실측 검증 `없음` 으로 나옵니다.

## 주의 · 운영 팁

- 사례 실습의 티켓 번호는 PC 속도에 따라 다를 수 있습니다. `SELECT ticket_id, cluster, LEFT(qhash,8) FROM dba.tuning_ticket;` 로 shop-db `5e9245c3` 가 몇 번인지 먼저 확인합니다([lab/README.md](../lab/README.md) 5장).
- 하루 상한 `TOP_N = 10` 에 밀린 쿼리는 다음 날 다시 후보가 됩니다(티켓이 없으므로).
- 운영 기준은 보통 평균 0.5~1초, 하루 30회 이상입니다([config.example.ini:21-22](../skeleton/config.example.ini#L21)).

## 다음 단계

→ [10. 성능 추적 관리 자동화](10-tracking-automation.md)
