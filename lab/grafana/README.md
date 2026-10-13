# lab/grafana — 슬로우 쿼리 운영 대시보드

저장소 `dba` 의 일자 집계 · 티켓을 그래프로 보여 주는 Grafana 대시보드와, 그것을 자동으로 등록하는 설정이 있습니다. `docker compose up -d` 를 하면 따로 할 일 없이 대시보드가 올라옵니다.

## 파일

| 파일 | 역할 | 언제 쓰나 |
|---|---|---|
| `dashboards/slowquery.json` | 대시보드 본체 (uid `lab-slowquery`, 변수 9개 · 패널 8개) | Grafana 가 자동으로 읽음 · AWS 버전도 같은 파일을 씀 |
| `make_dashboard.py` | 위 JSON 을 만드는 생성기. 패널 SQL 을 바꿀 때는 JSON 이 아니라 이 파일을 고침 | 대시보드를 고칠 때 |
| `provisioning/datasources/mysql.yml` | 데이터 소스 `lab-dba` — `shop-db:3306` 의 `dba`, 읽기 전용 계정 `lab_grafana` | 자동 적용 |
| `provisioning/dashboards/lab.yml` | `dashboards/` 폴더의 JSON 을 「슬로우 쿼리 실습」 폴더로 등록 | 자동 적용 |

`native.sh` 로 띄우면 이 두 yml 의 주소 · 경로만 바꾼 사본을 `lab/.data/grafana/prov/` 에 만들어 씁니다.

## 준비물

- Grafana 가 떠 있을 것: Docker 는 `docker compose up -d`(컨테이너 `lab-grafana`), Homebrew 는 `./native.sh up`
- 데이터: [scripts/README.md](../scripts/README.md) 1단계 `simulate.py` 를 한 번 돌려야 그래프가 생깁니다.

## 따라 하기

1. 브라우저에서 http://localhost:3000/d/lab-slowquery 를 엽니다. 로그인 없이(익명 Viewer) 보입니다.
   목록으로 찾으려면 http://localhost:3000 → Dashboards → `슬로우 쿼리 실습` 폴더 → `슬로우 쿼리 운영 대시보드 (실습)`.

2. **매일 보는 순서** — 화면 위 변수에서 `일자` 를 고르고 위에서 아래로 봅니다.

   | 패널 | 보는 것 |
   |---|---|
   | 검출된 슬로우 쿼리 · 총 부하 (초) · 열린 티켓 · 해결 확인된 티켓 | 오늘 상태 한눈에 |
   | 슬로우 쿼리 순위 | 그날 무엇이 무거웠나 (정렬은 `정렬` 변수) |
   | 총 부하 상위 5개 쿼리 추이 | 최근 `기간(일)` 동안 늘었나 줄었나 — 9일차 해결 · 12일차 재발이 보임 |
   | 선택한 쿼리 평균 실행 시간 | `쿼리` 변수로 고른 지문 하나의 추이 |
   | 티켓 추적 — 개선 효과 | 티켓별 기준 → 현재 |

3. **대시보드를 고치고 싶으면** — `make_dashboard.py` 를 고친 뒤 `lab/grafana` 폴더에서:

   ```bash
   cd lab/grafana
   ../.venv/bin/python make_dashboard.py
   ```

   ```
   written dashboards/slowquery.json
   ```

   Grafana 가 파일을 다시 읽을 때까지 잠시 기다린 뒤 브라우저를 새로 고칩니다. 바로 안 바뀌면 `lab` 에서 `docker compose restart grafana`.

## 자주 막히는 곳

| 증상 | 원인 · 해결 |
|---|---|
| 모든 패널이 `No data` | 아직 수집 데이터가 없습니다. `simulate.py` 를 먼저 |
| 추이 그래프가 비었거나 짧다 | 추이 패널은 **오늘** 기준 최근 N일입니다. 시뮬레이션 뒤 시간이 지났으면 `기간(일)` 을 30 으로 |
| 데이터 소스 오류 (접속 실패 · Access denied) | shop-db 가 아직 적재 중이거나 `lab_grafana` 계정이 없습니다. [mysql/README.md](../mysql/README.md) 2 · 4단계 확인 |
| UI 에서 고쳐 저장했는데 재시작하면 원래대로 | provisioning 대시보드라 파일이 기준입니다. `make_dashboard.py` 에서 고칩니다 |
| 3000 포트가 이미 사용 중 | `docker-compose.yml` 의 Grafana 포트를 `127.0.0.1:3001:3000` 으로 바꾸고 http://localhost:3001 로 접속 (알림 본문 링크는 3000 고정) |

## 다음 단계

- 변수 · 패널 SQL 상세: [docs/04-dashboard.md](../../docs/04-dashboard.md)
- 데이터 소스 · provisioning 상세: [docs/03-grafana.md](../../docs/03-grafana.md)
- 전체 순서도: [docs/GETTING_STARTED.md](../../docs/GETTING_STARTED.md)
