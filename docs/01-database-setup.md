# 01. 데이터베이스 설정

## 목적

운영 클러스터 두 개를 흉내 내는 **MySQL 8.0 서버 두 대**를 띄우고, 슬로우 쿼리 수집에 필요한 설정(슬로우 로그 · performance_schema)과 자동화용 저장소 · 계정을 만듭니다.

| 서버 | 접속 | 역할 |
|---|---|---|
| shop-db | `127.0.0.1:3306` | "서비스 A" DB. 부하 대상 + **저장소(`dba`)가 있는 DB** ([common.py:9](../lab/scripts/common.py#L9)) |
| order-db | `127.0.0.1:3307` | "서비스 B" DB. 다중 클러스터 실습 + **실측 검증 DB** ([verify.py:10](../lab/ai/verify.py#L10)) |

## 관련 파일

| 파일 | 내용 |
|---|---|
| [lab/docker-compose.yml](../lab/docker-compose.yml) | Docker 로 MySQL 두 대 + Grafana |
| [lab/native.sh](../lab/native.sh) | Docker 없이 Homebrew `mysql@8.0` 두 대 + Grafana |
| [lab/mysql/my.cnf](../lab/mysql/my.cnf) | Docker 용 서버 설정 |
| [lab/mysql/init/01_shop.sql](../lab/mysql/init/01_shop.sql) | 샘플 스키마 · 데이터 ([02 문서](02-sample-data.md)) |
| [lab/mysql/init/02_dba.sql](../lab/mysql/init/02_dba.sql) | 저장소 스키마 · CMDB · 계정 |
| [lab/scripts/common.py](../lab/scripts/common.py) | 스크립트가 쓰는 접속 정보 |
| [lab/requirements.txt](../lab/requirements.txt) | `pymysql` · `cryptography` · `mcp` |

## 동작 상세

### 1) Docker 경로

- 이미지 `mysql:8.0` 두 개, 컨테이너 이름 `lab-shop-db` · `lab-order-db` ([docker-compose.yml:4-24](../lab/docker-compose.yml#L4)).
- 포트는 `127.0.0.1` 에만 바인딩합니다 — `127.0.0.1:3306:3306`, `127.0.0.1:3307:3306` ([docker-compose.yml:9](../lab/docker-compose.yml#L9), [docker-compose.yml:20](../lab/docker-compose.yml#L20)).
- 두 서버 모두 같은 `my.cnf` 를 `/etc/mysql/conf.d/lab.cnf` 로, 같은 `mysql/init` 을 `/docker-entrypoint-initdb.d` 로 마운트합니다([docker-compose.yml:11-12](../lab/docker-compose.yml#L11)). 그래서 **두 서버에 똑같이** `shop` 데이터와 `dba` 저장소 · 계정이 만들어집니다. 스크립트가 실제로 쓰는 저장소는 shop-db 쪽뿐입니다.
- 데이터는 named volume `shop-data` · `order-data` 에 남습니다([docker-compose.yml:38-40](../lab/docker-compose.yml#L38)).
- root 비밀번호는 `MYSQL_ROOT_PASSWORD: lab-root-pw` ([docker-compose.yml:8](../lab/docker-compose.yml#L8)).

### 2) my.cnf 설정 (Docker)

| 설정 | 값 | 코드 | 쓰임 |
|---|---|---|---|
| `slow_query_log` | 1 | [my.cnf:3](../lab/mysql/my.cnf#L3) | 슬로우 로그 켜기 |
| `long_query_time` | 0.5 | [my.cnf:4](../lab/mysql/my.cnf#L4) | 0.5초 이상만 슬로우 로그에 기록 |
| `log_output` | FILE | [my.cnf:5](../lab/mysql/my.cnf#L5) | |
| `slow_query_log_file` | `/var/lib/mysql/slow.log` | [my.cnf:6](../lab/mysql/my.cnf#L6) | `docker cp lab-shop-db:/var/lib/mysql/slow.log .` 로 꺼냄 |
| `log_queries_not_using_indexes` | 0 | [my.cnf:7](../lab/mysql/my.cnf#L7) | |
| `performance_schema` | ON | [my.cnf:9](../lab/mysql/my.cnf#L9) | 수집 원천 `events_statements_summary_by_digest` |
| `performance-schema-consumer-events-statements-history-long` | ON | [my.cnf:10](../lab/mysql/my.cnf#L10) | `mask.py` 데모가 원문 SQL 을 읽는 곳 ([mask.py:24](../lab/scripts/mask.py#L24)) |
| `event_scheduler` | ON | [my.cnf:12](../lab/mysql/my.cnf#L12) | 16강에서 수집 방법의 하나로 소개 (코드에서 이벤트를 만들지는 않음) |
| `innodb_buffer_pool_size` | 512M | [my.cnf:13](../lab/mysql/my.cnf#L13) | |

> digest 길이(`performance_schema_max_digest_length` · `max_digest_length`)는 **설정하지 않았습니다** — MySQL 기본값을 씁니다.
> 수집은 슬로우 로그가 아니라 performance_schema 를 읽으므로, `long_query_time` 보다 빠른 쿼리도 집계에 들어갑니다([06 문서](06-collection.md)).

### 3) native.sh 경로 (Homebrew)

- `$(brew --prefix)/opt/mysql@8.0/bin` 에 `mysqld` 가 없으면 설치 안내 후 종료합니다([native.sh:7-8](../lab/native.sh#L7)).
- 데이터 디렉터리는 `lab/.data/<이름>` 입니다. 처음이면 `--initialize-insecure` 로 초기화합니다([native.sh:13-17](../lab/native.sh#L13)).
- `my.cnf` 를 읽지 않고(`--no-defaults`) **같은 의미의 옵션을 명령줄로** 줍니다([native.sh:18-22](../lab/native.sh#L18)):
  `--slow-query-log=1 --long-query-time=0.5 --slow-query-log-file=$dir/slow.log --performance-schema=ON --performance-schema-consumer-events-statements-history-long=ON --event-scheduler=ON --innodb-buffer-pool-size=512M --bind-address=127.0.0.1`, 소켓은 `/tmp/lab-<이름>.sock`, `--mysqlx=OFF`.
  (`log_output` · `log_queries_not_using_indexes` 는 지정하지 않습니다.)
- 첫 기동이면 `mysql/init/*.sql` 을 순서대로 적재하고, root 비밀번호를 `lab-root-pw` 로 바꾸며 `root@127.0.0.1` 을 만듭니다([native.sh:24-29](../lab/native.sh#L24)).
- `up` 은 shop-db 3306 → order-db 3307 → Grafana 순서([native.sh:34-45](../lab/native.sh#L34)), `down` 은 `mysqladmin shutdown` + Grafana 프로세스 종료([native.sh:46-51](../lab/native.sh#L46)).

### 4) 계정과 권한 (02_dba.sql)

| 계정 | 권한 | 코드 | 쓰는 곳 |
|---|---|---|---|
| `lab_collector`@`%` | `performance_schema.*` SELECT · `sys.*` SELECT, EXECUTE · `*.*` SELECT, PROCESS · `dba.*` INSERT, UPDATE, SELECT, DELETE | [02_dba.sql:90-94](../lab/mysql/init/02_dba.sql#L90) | 스크립트 기본 계정 ([common.py:16-17](../lab/scripts/common.py#L16)) |
| `lab_grafana`@`%` | `dba.*` SELECT | [02_dba.sql:95-96](../lab/mysql/init/02_dba.sql#L95) | Grafana 데이터 소스 |
| `lab_ai`@`%` | `shop.*` SELECT · `dba.slow_digest_daily` SELECT | [02_dba.sql:99-101](../lab/mysql/init/02_dba.sql#L99) | MCP 서버 ([labdb_mcp.py:17](../lab/ai/labdb_mcp.py#L17)) |
| root | 전체 | [docker-compose.yml:8](../lab/docker-compose.yml#L8) | 부하 발생 · DDL · 검증 · 반영 |

- 스크립트 기본 계정은 환경 변수 `LAB_USER` · `LAB_PASSWORD` 로 바꿀 수 있습니다([common.py:16-17](../lab/scripts/common.py#L16)).
- `lab_collector` 는 실습 편의상 대상 읽기와 저장소 쓰기를 한 계정에 묶었습니다(주석 [02_dba.sql:89](../lab/mysql/init/02_dba.sql#L89)). 스켈레톤은 수집 · 저장소 · 검증 계정을 나눕니다([skeleton/README.md](../skeleton/README.md) 1장, [config.example.ini](../skeleton/config.example.ini)).

## 실행 방법

```bash
cd lab
docker compose up -d                 # 또는 ./native.sh up
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # Python 3.10 이상
```

처음부터 다시: `docker compose down -v && docker compose up -d` 또는 `./native.sh down && rm -rf .data && ./native.sh up`.

## 확인 방법

1. 기동 완료: `docker compose logs -f shop-db order-db` 에서 **두 서버 모두** `port: 3306` 이 붙은 `ready for connections` 가 보이면 준비 완료입니다(적재 중 임시 서버는 `port: 0` 으로 같은 문구를 찍습니다). native 는 `[shop-db] 127.0.0.1:3306 준비 완료` 출력([native.sh:30](../lab/native.sh#L30)).
2. 설정 값:

```sql
SHOW VARIABLES WHERE Variable_name IN
 ('slow_query_log','long_query_time','performance_schema','event_scheduler','innodb_buffer_pool_size');
SELECT * FROM performance_schema.setup_consumers WHERE NAME = 'events_statements_history_long';  -- ENABLED = YES
```

3. 저장소 · 계정:

```sql
SHOW TABLES FROM dba;           -- cmdb_cluster, cmdb_instance, digest_snapshot, slow_digest_daily, ticket_event, tuning_ticket
SELECT cluster, collect FROM dba.cmdb_cluster;   -- shop-db 1 · order-db 1
SHOW GRANTS FOR 'lab_ai'@'%';
```

## 주의 · 운영 팁

- 3306 · 3307 이 이미 쓰이면 포트를 바꾸지 말고 기존 MySQL 을 멈춥니다. 스크립트 곳곳에 포트가 고정돼 있습니다([common.py:5-8](../lab/scripts/common.py#L5), [labdb_mcp.py:16](../lab/ai/labdb_mcp.py#L16), [verify.py:10](../lab/ai/verify.py#L10), [nplus1.py:9](../lab/scripts/nplus1.py#L9)).
- 비밀번호는 모두 **로컬 실습 전용** 공개 값입니다. 포트를 127.0.0.1 에만 연 이유입니다.
- 운영에서는 수집 계정에 `performance_schema` SELECT 만 주고, 저장소는 대상과 다른 서버에 두는 것을 권장합니다([skeleton/README.md](../skeleton/README.md) 1장 · 5장).

## 다음 단계

→ [02. 샘플 데이터 생성](02-sample-data.md)
