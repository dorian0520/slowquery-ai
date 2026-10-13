# slowq — 슬로우 쿼리 자동 검출 · 티켓 · 추적 워킹 스켈레톤

강의 40강의 아키텍처를 **내 환경에 옮겨 심는 최소 동작 프로그램**입니다. 실습 코드(`lab/`)를 일반화했습니다.
- 수집 대상은 CMDB 가 정합니다.
- 비밀번호는 환경 변수로만 받습니다.
- 알림은 dry-run 이 기본입니다.

```
운영 MySQL ×N ──(performance_schema 읽기)──▶ collect ──▶ 저장소(slowq)
      ▲                                                  │ digest_snapshot → slow_digest_daily
  cmdb_cluster (대상 · 담당 · 채널)                       ▼
                                   detect(규칙) ─▶ tickets.issue(중복 방지 · 담당자) ─▶ publish(dry-run)
                                        │                     │
                    analyze(Claude Code · 선택) ─▶ verify(검증 DB) ─▶ recommendation
                                                              ▼
                                         tickets.track(해결 · 재발) ─▶ Grafana(저장소 조회)
```

## 처음이라면 — 이 폴더 사용법

- **언제 쓰나**: `lab/` 실습을 한 번 끝까지 돌려 본 뒤, 같은 흐름(수집 → 검출 → 발행 → 추적)을 **내 MySQL 에 붙일 때** 씁니다. 실습만 할 거라면 이 폴더는 건너뛰어도 됩니다.
- **명령은 모두 `skeleton` 폴더에서** 칩니다. `python -m slowq` 는 현재 폴더의 `slowq/` 패키지를 찾고, `--config` 기본값 `config.ini` 도 현재 폴더 기준입니다.
- **순서**: 아래 1장(설치 · 설정 · `init-schema` · CMDB 등록) → 2장(`daily` 를 두 번 — 첫 번째는 기준 스냅숏만) → cron 등록. 실습 DB 로 먼저 연습하려면 1장의 「강의 실습 환경에서 돌려 보기」를 따릅니다.
- **정상 출력 예** (숫자는 환경마다 다릅니다)

  ```
  $ python -m slowq --config config.ini init-schema
  스키마 적용 완료
  $ python -m slowq --config config.ini daily --date 2026-10-12
  수집 order-db: 0개 지문          ← 첫 실행은 기준 스냅숏만 남겨 0개가 정상
  수집 shop-db: 0개 지문
  검출 0건
  신규 티켓 0건 · 상태 변경 0건
  ```

  두 번째 실행부터 `수집 shop-db: 27개 지문` 처럼 숫자가 생기고, 티켓이 발행되면 `# dry-run (보내지 않음) {...}` 줄이 함께 찍힙니다.
- **자주 막히는 곳**: `비밀번호가 없습니다 (… ) — password_env 환경 변수를 확인하세요` → `export SLOWQ_STORE_PASSWORD=… SLOWQ_TARGET_PASSWORD=…` 를 같은 터미널에서 했는지 확인. `FileNotFoundError: config.ini` → `cp config.example.ini config.ini` 를 `skeleton` 에서 했는지 확인. `No module named slowq` → `skeleton` 폴더 밖에서 실행한 것입니다.

`slowq/` 패키지의 파일 안내 (모듈별 하는 일은 아래 3장 표):

| 파일 | 역할 | 언제 보나 |
|---|---|---|
| `slowq/__main__.py` · `cli.py` | `python -m slowq` 진입점 · `daily` / `init-schema` 명령과 옵션(`--config`, `--date`) | 명령이 무엇을 순서대로 부르는지 볼 때 |
| `slowq/config.py` | ini 읽기 · `password_env` 가 가리키는 환경 변수에서 비밀번호 읽기 | 설정 값이 안 먹을 때 |
| `slowq/db.py` | 접속 · `schema.sql` 적용 | 접속 오류 · 스키마 적용 문제 |
| `slowq/collect.py` · `detect.py` · `tickets.py` · `publish.py` | `daily` 가 부르는 4단계 | 동작을 바꾸고 싶을 때 (3장 표) |
| `slowq/analyze.py` · `verify.py` · `mask.py` | AI 분석 · 실측 검증 · 마스킹 (선택 모듈, `daily` 에 연결돼 있지 않음) | 진단 단계를 붙일 때 |

테스트 사용법은 [tests/README.md](tests/README.md), 전체 여정은 [docs/GETTING_STARTED.md](../docs/GETTING_STARTED.md) 를 보세요.

## 1. 설치 · 설정
```bash
pip install -r requirements.txt
cp config.example.ini config.ini                       # 연 뒤 [store] 의 host · user · database, [target] 의 user 를 내 환경으로 고칩니다 (대상 host 는 CMDB)
mysql -h <저장소> -u root -p -e "CREATE DATABASE slowq" # 저장소 데이터베이스 (이름은 config 의 [store] database)
export SLOWQ_STORE_PASSWORD=... SLOWQ_TARGET_PASSWORD=...
python -m slowq --config config.ini init-schema         # 저장소에 schema.sql 적용
```

CMDB 에 수집할 클러스터를 넣습니다. 한 줄이 곧 수집 대상 · 담당자 · 알림 채널입니다.
```sql
INSERT INTO cmdb_cluster (cluster, host, port, realm, tag, owner, owner_team, slack_channel, collect)
VALUES ('order-prod', 'order-prod.cluster-xxx', 3306, 'prod', '주문', 'dev-kim', '주문개발팀', '#order-db-alert', 1);
```

권장 계정 권한은 다음과 같습니다(최소 권한).
- 수집 계정: `GRANT SELECT ON performance_schema.* TO slowq_collector;` (계정은 `CREATE USER` 로 먼저 만듭니다)
- 저장소 계정: `slowq.*` 에 대한 DML (`init-schema` 를 이 계정으로 돌리면 `CREATE` 도 필요 — 또는 스키마는 관리자 계정으로 한 번 적용)
- 검증 계정: 검증 DB 에서만 대상 테이블 `SELECT` + `ALTER` · `CREATE` · `INSERT` (인덱스 추가 · 삭제는 `ALTER TABLE` 이라 세 권한이 필요)

### 강의 실습 환경에서 돌려 보기
실습 DB 에는 `slowq_*` 계정이 없으니 root · lab_collector 로 바꿔 씁니다.
```bash
cp config.example.ini config.ini     # [store] user = root, database = slowq · [target] user = lab_collector
export SLOWQ_STORE_PASSWORD=lab-root-pw SLOWQ_TARGET_PASSWORD=lab-collector-pw
mysql -h127.0.0.1 -uroot -plab-root-pw -e "CREATE DATABASE slowq"
../lab/.venv/bin/python -m slowq --config config.ini init-schema
mysql -h127.0.0.1 -uroot -plab-root-pw slowq -e "INSERT INTO cmdb_cluster (cluster, host, port, realm, tag, owner, owner_team, slack_channel, collect) VALUES
  ('shop-db', '127.0.0.1', 3306, 'prod', '주문', 'dev-kim', '주문개발팀', '#order-db-alert', 1),
  ('order-db', '127.0.0.1', 3307, 'prod', '정산', 'dev-lee', '정산개발팀', '#settle-db-alert', 1)"
```
- `config.ini` 의 `[rules]` 는 실습 PC 기준 `min_sec = 0.2` · `min_q = 5` 로 바꿉니다(운영 기준 0.5 · 30 으로는 실습 부하가 걸리지 않습니다).
- `../lab/.venv` 는 `lab.zip` 과 `skeleton.zip` 을 **같은 폴더에 풀었을 때**의 경로입니다. `mysql` 클라이언트가 없으면 `docker exec -i lab-shop-db mysql …` 으로 같은 SQL 을 실행합니다.

## 2. 매일 실행
```bash
python -m slowq --config config.ini daily               # 수집 → 검출 → 발행(dry-run) → 추적
# cron 예 (자정 직후 → 어제 하루치): 5 0 * * *  cd /opt/slowq && python -m slowq --config config.ini daily --date $(date -d yesterday +\%F) >> daily.log 2>&1
# (macOS 의 date 는 -v-1d) · 한 클러스터라도 수집에 실패하면 종료 코드 1
```
첫 실행은 기준 스냅숏만 남깁니다. 다음 실행부터 하루치 차이가 쌓입니다.

## 3. 모듈
| 파일 | 하는 일 | 강의 |
|---|---|---|
| `slowq/collect.py` | digest 누적값 → 스냅숏 차이. FIRST_SEEN 으로 재시작 감지, 스키마별 분리, 저장소 스키마 제외 | 16 |
| `slowq/detect.py` | 기준초과 · 신규(지난 7일에 없던 지문, 이력 있는 클러스터만) · 악화(직전일 대비) · 급증 (DDL · SET · SHOW 제외) | 17 |
| `slowq/mask.py` | 리터럴 마스킹 | 19 |
| `slowq/tickets.py` | 기준초과만 발행 · CMDB 담당자 · UNIQUE 중복 방지(상한은 신규 발행분만 셈), 0.5 / 0.8 해결 · 재발 판정 | 28~32 |
| `slowq/analyze.py` | `claude -p` 실행(선택), AI JSON 엄격 파싱 | 23~25 |
| `slowq/verify.py` | 검증 DB 에서 ADD INDEX 한 절만 다시 만들어 전후 측정 · 결과 동일성(행 순서 무시) · 반드시 되돌림 | 26 |
| `slowq/publish.py` | 발행 어댑터 (dry-run 기본, Jira · Slack 은 같은 형태로 추가) | 30 |
| `schema.sql` | 저장소 스키마 | 18 |

## 4. 테스트
```bash
python -m unittest discover -s tests                    # 단위 테스트 34개 (DB 불필요, 통합 5개는 건너뜀)
SLOWQ_IT=1 python -m unittest discover -s tests         # + 통합 테스트 5개 (강의 실습 환경 order-db 3307 필요, slowq_it 스키마를 만들고 지움)
```

## 5. 운영에 붙이기 전 체크
- `rules.min_sec` 은 운영 기준(보통 0.5~1초)으로 정하고, 처음 1~2주는 dry-run 결과를 보고 조정합니다.
- 저장소는 수집 대상과 다른 서버에 두는 것을 권장합니다. 같은 서버여도 저장소 스키마의 쿼리는 수집에서 제외됩니다.
- `daily` 는 수집 · 검출 · 발행 · 추적만 묶습니다. AI 분석(`analyze`)과 실측 검증(`verify`)은 선택 모듈로, 검증 결과를 `tuning_ticket.recommendation` 에 붙이는 단계는 각 조직 흐름에 맞게 추가합니다.
- 스켈레톤이 다루는 범위는 **수집 → 검출 → 발행 → 추적**입니다. 반영 · 관리 단계는 실습 코드(`lab/`)에서 가져와 붙입니다.

  lab 코드는 실습 환경에 맞춘 예제입니다 — 클러스터 `shop-db` · `order-db`, 서비스 스키마 `shop`, 저장소 DB `dba`, 실습 계정이 파일 안에 박혀 있어 그대로는 붙지 않습니다. `common.py` 의 접속 정보(`CLUSTERS` · `STORE` · 기본 계정)는 스켈레톤의 `config.ini` · `db.connect` 로 바꿉니다. 아래 「바꿀 것」은 파일마다 찾은 실습 고정값과 스키마 차이이고, 옮긴 뒤에는 **검증 DB 에서 끝까지 한 번 돌려 본 다음** 운영에 붙입니다.

  | 단계 | 가져올 파일 (`lab/`) | 옮길 때 바꿀 것 |
  |---|---|---|
  | AI 분석 규칙 · 도구 | `ai/CLAUDE.md` · `ai/labdb_mcp.py` · `ai/mcp.json` (`analyze.py` 가 이 셋을 씁니다) + `labdb_mcp.py` 가 불러오는 `scripts/mask.py` · `scripts/common.py` | `mcp==2.3.0` 설치(`lab/requirements.txt` — 스켈레톤 requirements 에는 없음) · 저장소 DB `dba` · 서비스 스키마 `shop` · 클러스터 이름 · 읽기 전용 계정 · `mcp.json` 의 상대 경로 `../.venv` |
  | 분석 · 검증 결과 첨부 | `scripts/publish.py attach` + `scripts/common.py` | 저장소 클러스터(`common.py` 의 `STORE = "shop-db"`) · DB 이름 `dba` · 티켓 조회의 `cluster='shop-db'` · 입력 형식(lab `verify.py` 의 텍스트 출력을 읽음, 스켈레톤 `verify()` 는 dict 를 돌려줌) |
  | 실제 Jira / Slack 전송 | `scripts/publish.py payload` (dry-run 본문) | 대시보드 링크(`localhost:3000/d/lab-slowquery`) · Jira 프로젝트 키 `DBTUNE` · 전송 코드 · 토큰은 비밀 저장소 |
  | 운영 반영 (변경 계획 · 온라인 DDL) | `scripts/apply_fix.py` + `scripts/common.py` | 저장소 `dba` · 서비스 스키마 `shop` · root 계정 · 대상 접속(실습 CMDB 에는 host · port 컬럼이 없음) · 반영 중 측정 쿼리(`orders` · `order_id`)와 사후 확인 쿼리(`orders` · `user_id = 1001`). 사후 확인이 실패하면 인덱스는 반영됐는데 APPLIED 기록이 남지 않으니 특히 먼저 검증 DB 에서 확인 |
  | 주간 리포트 | `scripts/report.py` + `scripts/common.py` | 저장소 클러스터 · DB 이름 `dba` |
  | 대시보드 | `grafana/make_dashboard.py` | 데이터소스 · DB 이름 · 대시보드 uid `lab-slowquery` · 순위 패널의 `max_sec` 과 티켓 패널의 `updated_at` 정렬 (스켈레톤 스키마에 없는 열) |
- `digest_snapshot` 은 보관 기간을 짧게, `slow_digest_daily` 는 길게 둡니다.
- AI 분석은 읽기 전용 계정 + 허용 도구만 쓰고, `verify` 결과를 함께 티켓에 붙이고, 통과한 제안만 반영합니다.
