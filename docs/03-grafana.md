# 03. Grafana 구성

## 목적

저장소(`dba`)를 읽는 Grafana 를 **코드로만** 구성합니다. 데이터 소스와 대시보드를 provisioning 파일로 올려, 띄우자마자 로그인 없이 대시보드를 볼 수 있게 합니다.

## 관련 파일

| 파일 | 내용 |
|---|---|
| [lab/docker-compose.yml](../lab/docker-compose.yml) | `grafana` 서비스 |
| [lab/native.sh](../lab/native.sh) | Homebrew Grafana 기동 · 경로 치환 |
| [lab/grafana/provisioning/datasources/mysql.yml](../lab/grafana/provisioning/datasources/mysql.yml) | MySQL 데이터 소스 `lab-dba` |
| [lab/grafana/provisioning/dashboards/lab.yml](../lab/grafana/provisioning/dashboards/lab.yml) | 대시보드 파일 provider |
| [lab/grafana/dashboards/slowquery.json](../lab/grafana/dashboards/slowquery.json) | 대시보드 JSON (생성물) |
| [lab/grafana/make_dashboard.py](../lab/grafana/make_dashboard.py) | 위 JSON 생성기 ([04 문서](04-dashboard.md)) |

## 동작 상세

### 1) 컨테이너 (Docker)

- 이미지 `grafana/grafana:11.2.0`, 컨테이너 `lab-grafana`, 포트 `127.0.0.1:3000:3000` ([docker-compose.yml:26-29](../lab/docker-compose.yml#L26)).
- **익명 보기 허용**: `GF_AUTH_ANONYMOUS_ENABLED: "true"`, `GF_AUTH_ANONYMOUS_ORG_ROLE: Viewer` ([docker-compose.yml:30-32](../lab/docker-compose.yml#L30)). 로그인 없이 Viewer 권한으로 대시보드를 봅니다. 편집하려면 관리자 로그인이 필요합니다(compose 주석에 `admin / admin` — [docker-compose.yml:2](../lab/docker-compose.yml#L2)).
- 마운트([docker-compose.yml:33-35](../lab/docker-compose.yml#L33)):
  - `./grafana/provisioning` → `/etc/grafana/provisioning` (읽기 전용)
  - `./grafana/dashboards` → `/var/lib/grafana/dashboards` (읽기 전용)
- `depends_on: [shop-db]` ([docker-compose.yml:36](../lab/docker-compose.yml#L36)).

### 2) 데이터 소스 provisioning

[mysql.yml](../lab/grafana/provisioning/datasources/mysql.yml):

| 항목 | 값 | 줄 |
|---|---|---|
| name · uid | `lab-dba` | [L3-4](../lab/grafana/provisioning/datasources/mysql.yml#L3) |
| type | `mysql` | [L5](../lab/grafana/provisioning/datasources/mysql.yml#L5) |
| url | `shop-db:3306` (compose 서비스 이름) | [L6](../lab/grafana/provisioning/datasources/mysql.yml#L6) |
| user | `lab_grafana` (`dba.*` SELECT 만 — [02_dba.sql:95-96](../lab/mysql/init/02_dba.sql#L95)) | [L7](../lab/grafana/provisioning/datasources/mysql.yml#L7) |
| database | `dba` | [L9](../lab/grafana/provisioning/datasources/mysql.yml#L9) |
| password | `lab-grafana-pw` (secureJsonData, 실습 전용) | [L11](../lab/grafana/provisioning/datasources/mysql.yml#L11) |
| isDefault | true | [L12](../lab/grafana/provisioning/datasources/mysql.yml#L12) |

대시보드의 모든 패널 · 변수는 이 uid 로 데이터 소스를 가리킵니다([make_dashboard.py:4](../lab/grafana/make_dashboard.py#L4)).

### 3) 대시보드 provisioning

[lab.yml](../lab/grafana/provisioning/dashboards/lab.yml): provider `lab`, 폴더 `슬로우 쿼리 실습`, `type: file`, `path: /var/lib/grafana/dashboards` ([lab.yml:3-7](../lab/grafana/provisioning/dashboards/lab.yml#L3)). 이 경로에 마운트된 `slowquery.json` (uid `lab-slowquery`)이 올라갑니다.

### 4) native.sh 의 경로 치환

Docker 가 아닐 때는 compose 서비스 이름과 컨테이너 경로가 없으므로 `sed` 로 복사본을 만들어 씁니다([native.sh:37-39](../lab/native.sh#L37)).

| 원본 | 치환 | 결과 파일 |
|---|---|---|
| `shop-db:3306` | `127.0.0.1:3306` | `.data/grafana/prov/datasources/mysql.yml` |
| `/var/lib/grafana/dashboards` | `<lab 절대 경로>/grafana/dashboards` | `.data/grafana/prov/dashboards/lab.yml` |

그다음 `GF_PATHS_PROVISIONING` · `GF_PATHS_DATA` · `GF_PATHS_LOGS` 를 `.data/grafana` 아래로 두고, Docker 와 같은 익명 Viewer 설정 + `GF_SERVER_HTTP_ADDR=127.0.0.1` 로 `grafana server` 를 백그라운드로 띄웁니다([native.sh:40-43](../lab/native.sh#L40)). 로그는 `.data/grafana.out`.

## 실행 방법

```bash
cd lab
docker compose up -d grafana      # 전체 기동 시 함께 뜸
# 또는
./native.sh up                    # brew install mysql@8.0 grafana 필요
```

## 확인 방법

- 브라우저에서 http://localhost:3000 → 로그인 없이 `슬로우 쿼리 실습` 폴더의 `슬로우 쿼리 운영 대시보드 (실습)` 이 보이면 정상입니다.
- 바로 가기: http://localhost:3000/d/lab-slowquery (티켓 알림 본문의 링크도 이 형식 — [publish.py:10](../lab/scripts/publish.py#L10)).
- 패널이 "No data" 면 아직 수집 데이터가 없는 것입니다. `simulate.py` 를 먼저 돌립니다([05 문서](05-slow-query-generation.md)).
- 데이터 소스 오류면 `lab_grafana` 계정과 `dba` 스키마가 shop-db 에 있는지 확인합니다.

## 주의 · 운영 팁

- 포트 3000 이 이미 쓰이면 compose 의 포트를 `127.0.0.1:3001:3000` 으로 바꿔도 됩니다(스크립트는 Grafana 포트를 쓰지 않음, 단 `publish.py` 의 링크 문자열은 3000 고정).
- provisioning 디렉터리는 읽기 전용 마운트라 UI 에서 대시보드를 고쳐 저장해도 파일에 남지 않습니다. 변경은 `make_dashboard.py` 에서 하고 JSON 을 다시 만듭니다.
- 운영에서는 Grafana 계정에 저장소 SELECT 만 주고(`lab_grafana` 와 같은 방식), 익명 접근 범위는 조직 정책에 맞춥니다.

## 다음 단계

→ [04. 모니터링 대시보드 구성](04-dashboard.md)
