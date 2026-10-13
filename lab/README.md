# 실습 환경 (lab)

강의 「AI를 활용한 데이터베이스 쿼리 튜닝 자동화 — Claude Code로 매일 슬로우 쿼리를 찾고, 분석하고, 검증하는 MySQL 운영 시스템」의 실습 코드입니다.
모든 데이터는 강의용으로 만든 합성 데이터입니다.

## 처음이라면 — 이 폴더 사용법

이 폴더 하나로 **MySQL 두 대 + Grafana + 자동화 스크립트**가 내 PC 에서 돌아갑니다. 처음 받은 분은 아래 순서만 따라오면 됩니다.

1. 아래 **1장 띄우기** → **2장 14일 운영 상황 재현** 까지 하면 Grafana 에 2주치 데이터가 보입니다.
2. 그다음은 **3장 표**를 보고 "어느 폴더에서 어떤 명령을 치는지" 확인하며 진행합니다.
3. 전체 여정을 한 장으로 보고 싶으면 [전체 순서도 (GETTING_STARTED)](../docs/GETTING_STARTED.md) 를 먼저 보세요.

| 하위 폴더 | 무엇이 들어 있나 | 안내 |
|---|---|---|
| `mysql/` | MySQL 설정 · 샘플 데이터 · 저장소(`dba`) 스키마 | [mysql/README.md](mysql/README.md) |
| `scripts/` | 부하 · 수집 · 검출 · 티켓 · 발행 · 반영 · 리포트 스크립트 | [scripts/README.md](scripts/README.md) |
| `ai/` | Claude Code 분석 규칙 · 읽기 전용 MCP 서버 · 실측 검증 | [ai/README.md](ai/README.md) |
| `sql/` | 7~14강 실습 SQL · 남은 인덱스 정리용 `reset.sql` | [sql/README.md](sql/README.md) |
| `grafana/` | 대시보드 JSON 과 생성기 · 데이터 소스 설정 | [grafana/README.md](grafana/README.md) |
| `tests/` | 운영 반영 · 리포트 로직 테스트 · 수집기 통합 테스트 | [tests/README.md](tests/README.md) |

잘 됐는지 3가지만 확인하면 됩니다: `docker compose ps` 에 컨테이너 3개(`lab-shop-db` · `lab-order-db` · `lab-grafana`)가 보이고, `simulate.py` 끝에 **강의 날짜 → 내 날짜** 표가 나오고, http://localhost:3000/d/lab-slowquery 에 그래프가 그려지면 준비 끝입니다.

## 1. 띄우기

준비물: Docker, **Python 3.10 이상**(macOS 기본 python3 는 3.9 → `brew install python@3.12` 후 `python3.12` 사용, Ubuntu 는 `sudo apt install python3-venv`), Claude Code(23강부터 · 처음 한 번 `claude` 를 실행해 로그인).

```bash
cd lab
docker compose up -d            # MySQL 두 대(3306 shop-db · 3307 order-db) + Grafana(3000)
python3.12 -m venv .venv        # 3.10 이상이면 어떤 버전이든
.venv/bin/pip install -r requirements.txt
source .venv/bin/activate       # 강의 화면의 python · python3 는 이 가상 환경
```

- 3306 · 3307 이 이미 쓰이면 포트를 바꾸지 말고(스크립트가 이 포트를 씁니다) 기존 MySQL 을 멈추세요: `brew services stop mysql` / `sudo systemctl stop mysql`. Grafana 3000 은 `127.0.0.1:3001:3000` 으로 바꿔도 됩니다.
- mysql 클라이언트가 없으면 `docker exec -it lab-shop-db mysql -uroot -plab-root-pw shop` (order-db 는 `lab-order-db`). 3강부터의 `mysql>` 명령은 **root** 로 접속합니다(SET GLOBAL 등).

- 첫 기동 때 주문 200만 행을 만드느라 몇 분 걸립니다. `docker compose logs -f shop-db order-db` 에서 **두 대 모두** **`port: 3306` 이 붙은** `ready for connections` 가 보이면 준비된 것입니다 (적재 중 임시 서버는 `port: 0` 으로 같은 문구를 찍습니다).
- Docker 를 쓸 수 없는 macOS 라면 `brew install mysql@8.0 grafana` 후 `./native.sh up`. mysql 클라이언트는 `export PATH="$(brew --prefix)/opt/mysql@8.0/bin:$PATH"`.

## 2. 14일 운영 상황 재현

```bash
.venv/bin/python scripts/simulate.py
```

수 분 걸립니다. 끝나면 **강의 날짜 → 내 날짜** 대응표가 출력됩니다.

```
강의 날짜 → 내 날짜
  2026-09-29 → ...  (1일차 · 첫 티켓 발행)
  2026-10-06 → ...  (8일차 · 쿠폰 급증)
  2026-10-07 → ...  (9일차 · 인덱스 추가(해결))
  2026-10-10 → ...  (12일차 · 인덱스 삭제(재발))
  2026-10-12 → ...  (14일차 · 마지막 날)
  2026-10-13 → ...  (다음 날 · 37~39강 사례 실습)
```

강의 화면의 `--log-date 2026-10-12` 같은 날짜는 촬영일 기준입니다. **이 표의 오른쪽 날짜로 바꿔 입력**하세요. `claude -p "2026-10-12 shop-db ..."` 처럼 **문장 속 날짜**도 바꿉니다.

- 표를 잃어버렸으면: `SELECT DATE(MIN(created_at)) FROM dba.tuning_ticket;` 가 강의의 2026-09-29(1일차 · 첫 티켓 발행) 입니다. 다른 날짜는 같은 일수만큼 더합니다.
- 31 · 32강 화면의 `tickets.py track --log-date 2026-10-07` · `2026-10-10` 은 **simulate 가 이미 실행한 기록**입니다. 다시 치면 1번 티켓 상태가 바뀌어 38강 실습(재발 상태에서 반영)이 막히니 실행하지 않습니다.
- simulate 가 중간에 실패했으면 다시 돌리지 말고 6장 "처음부터 다시"로 초기화합니다.
- Grafana 추이 패널은 오늘 기준 최근 14일입니다. 시뮬레이션 후 2주가 지났으면 화면 위 `기간(일)` 을 30 으로 고릅니다.
- 3강 슬로우 로그 위치: Docker 는 `docker cp lab-shop-db:/var/lib/mysql/slow.log .` 후 `mysqldumpslow -s t -t 4 slow.log`, native 는 `.data/shop-db/slow.log`.
- 16강 수집을 직접 해 보려면 `--log-date 2000-01-01` 로 실행한 뒤 5장의 DELETE 로 지웁니다(14일 데이터에 섞이지 않게).

## 3. 명령을 실행하는 위치

| 위치 | 명령 |
|---|---|
| `lab/scripts` | `collector.py` · `detect.py` · `tickets.py` · `publish.py` · `mask.py` · `sqlrun.py` · `nplus1.py` |
| `lab/ai` | `claude -p ... --mcp-config mcp.json` · `verify.py` |
| `lab/grafana` | `make_dashboard.py` |

`scripts/` 가 붙은 명령(`python scripts/report.py`)은 `lab` 에서, 붙지 않은 명령(`python3 tickets.py`, `python3 publish.py`)은 `lab/scripts` 에서 칩니다. 30강 attach 를 lab 에서 하려면 `python scripts/publish.py attach ai/run1.txt ai/verify_run1.txt --log-date …`.

`claude -p` 는 `lab/ai` 에서 실행해야 `CLAUDE.md` 와 `mcp.json` 의 상대 경로가 맞습니다. 동봉된 강사 결과 `run1.txt` · `verify_run1.txt` 는 덮어쓰지 말고, 내 결과는 `run_my.txt` 처럼 다른 이름으로 저장하세요(AI 출력이 JSON 이 아니면 verify 가 멈춥니다 — 26강).
명령 끝에 `< /dev/null` 을 붙이면 입력 대기 경고가 나오지 않습니다.

## 4. 7~15강 실습 SQL

각 강의의 실험(인덱스 생성 → EXPLAIN · 측정 → 인덱스 정리)을 그대로 담았습니다. `lab` 에서 실행합니다.

```bash
.venv/bin/python scripts/sqlrun.py < sql/lesson11.sql     # 7~14강: sql/lesson07.sql ~ lesson14.sql
.venv/bin/python scripts/nplus1.py                        # 15강
```

- 시작 상태는 `orders` · `users` 에 PRIMARY 만 있는 상태(시뮬레이션 직후)입니다. 파일마다 만든 인덱스를 끝에서 지웁니다.
- 중간에 끊겨 임시 인덱스가 남았으면 `.venv/bin/python scripts/sqlrun.py --keep-going < sql/reset.sql` 로 정리합니다.
- 실행 시간은 PC 마다 다릅니다. 실행 계획의 type · key 는 강의 화면과 같아야 하고, rows 는 통계 추정치라 조금 다를 수 있습니다.

## 5. 37~39강 사례 실습 (운영 반영과 관리)

`lab` 에서 진행합니다. 티켓 번호는 PC 속도에 따라 다를 수 있으니 먼저 `SELECT ticket_id, cluster, LEFT(qhash,8) FROM dba.tuning_ticket;` 로 **shop-db 5e9245c3 = 강의의 #1, shop-db f54ce51c = #3** 에 해당하는 번호를 확인하세요. 30강의 `publish.py attach` 까지 마쳐서 티켓 #1 에 AI 분석 · 실측 검증 결과가 붙어 있어야 합니다.
날짜는 2장의 대응표대로 바꿉니다 — `report --end 2026-10-12` 는 「마지막 날」, `apply` · `next_day` · `report --end 2026-10-13` 은 「다음 날」의 오른쪽 날짜.

```bash
.venv/bin/python scripts/report.py --end 2026-10-12                       # 반영 전 주간 리포트
.venv/bin/python scripts/apply_fix.py plan  --ticket 1                    # 변경 계획 (아무것도 바꾸지 않음)
.venv/bin/python scripts/apply_fix.py apply --ticket 1 --log-date 2026-10-13
.venv/bin/python scripts/next_day.py --log-date 2026-10-13                # 부하 → 수집 → 발행 → 추적
.venv/bin/python scripts/report.py --end 2026-10-13
```

- 사례 실습 뒤 7~15강을 다시 하려면 `reset.sql` 로 반영한 인덱스(`ix_orders_user_ordered`)를 지웁니다.
- 수집이 실패했다면: 원인을 고친 뒤 기준 스냅숏을 다시 잡고 이어서 진행합니다.
  `cd scripts && ../.venv/bin/python collector.py --log-date 2000-01-01` 후 `mysql> DELETE FROM dba.slow_digest_daily WHERE log_date = '2000-01-01';`
- 운영 반영 · 관리 스크립트 테스트: `.venv/bin/python -m unittest discover -s tests` · 수집기 통합 테스트: `LAB_IT=1 .venv/bin/python -m unittest tests.test_collector_it` (order-db에 테스트 쿼리를 실행해 performance_schema 집계가 늘어나니, 사례 실습을 마친 뒤 실행)

## 6. 처음부터 다시

```bash
docker compose down -v          # 데이터까지 지운다
docker compose up -d
# native.sh 로 띄웠다면
./native.sh down && rm -rf .data && ./native.sh up
```

## 7. 접속 정보 (로컬 실습 전용)

| 계정 | 비밀번호 | 용도 |
|---|---|---|
| root | lab-root-pw | 실습 SQL 실행 |
| lab_collector | lab-collector-pw | 수집 · 티켓 |
| lab_grafana | lab-grafana-pw | Grafana 데이터 소스 (SELECT) |
| lab_ai | lab-ai-pw | MCP 서버 (SELECT) |

Grafana: http://localhost:3000 (익명 보기 허용)
