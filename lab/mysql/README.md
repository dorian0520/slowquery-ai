# lab/mysql — 실습 MySQL 설정과 초기 데이터

실습용 MySQL 8.0 두 대(`shop-db` 3306 · `order-db` 3307)가 **처음 뜰 때** 읽는 설정 파일과 초기화 SQL 이 있습니다. 직접 실행할 명령은 거의 없고, 서버를 띄우면 자동으로 적용됩니다.

## 파일

| 파일 | 역할 | 언제 쓰나 |
|---|---|---|
| `my.cnf` | 슬로우 로그(`long_query_time = 0.5`) · `performance_schema` · 버퍼 풀 512M 등 서버 설정 | Docker 로 띄울 때 자동 적용 (native.sh 는 같은 값을 명령행 옵션으로 줍니다) |
| `init/01_shop.sql` | 샘플 쇼핑몰 스키마 `shop` 생성 — 회원 20만 · 상품 2만 · 주문 200만 행 (외부 다운로드 없음) | 첫 기동 때 자동 실행 (두 대 모두) |
| `init/02_dba.sql` | 자동화 저장소 `dba` (스냅숏 · 일자 집계 · 티켓 · 이벤트 · CMDB) + 실습 계정 3개 + CMDB 2행 | 첫 기동 때 자동 실행 (두 대 모두) |

- Docker 는 `init/` 을 컨테이너의 `/docker-entrypoint-initdb.d` 에 연결합니다. 이 폴더의 `.sql` 은 **데이터 볼륨이 비어 있을 때 한 번만** 실행됩니다.
- `native.sh` 는 `init/*.sql` 을 순서대로 `mysql` 클라이언트로 흘려 넣습니다. 그래서 `init/` 에 다른 `.sql` 을 넣으면 함께 실행되니 넣지 마세요.

## 준비물

- Docker (Docker Desktop 등) — 또는 macOS 에서 `brew install mysql@8.0 grafana`
- 디스크 여유 수 GB (주문 200만 행 × 2대)

## 따라 하기

1. **서버 띄우기** — `lab` 폴더에서:

   ```bash
   cd lab
   docker compose up -d
   ```

2. **준비될 때까지 기다리기** — 첫 기동은 200만 행을 만드느라 몇 분 걸립니다. `lab` 폴더에서:

   ```bash
   docker compose logs -f shop-db order-db
   ```

   두 서버 모두 `port: 3306` 이 붙은 줄이 보이면 준비 완료입니다(컨테이너 안에서는 둘 다 3306 입니다). `Ctrl+C` 로 로그 보기를 끝냅니다.

   ```
   lab-shop-db   | ... [Server] /usr/sbin/mysqld: ready for connections. Version: '8.0.x'  socket: '/var/run/mysqld/mysqld.sock'  port: 3306  MySQL Community Server - GPL.
   ```

   `port: 0` 이 붙은 같은 문구는 적재 중인 임시 서버이니 조금 더 기다립니다.

   Docker 없이 `./native.sh up` 으로 띄웠다면 이런 줄이 나옵니다.

   ```
   [shop-db] 초기 데이터 적재 중 (주문 200만 건, 1~3분)
   [shop-db] 127.0.0.1:3306 준비 완료
   ```

3. **접속해 보기** — mysql 클라이언트가 없어도 컨테이너 안의 클라이언트를 쓰면 됩니다.

   ```bash
   docker exec -it lab-shop-db mysql -uroot -plab-root-pw shop      # order-db 는 lab-order-db
   ```

   `mysql: [Warning] Using a password on the command line interface can be insecure.` 경고는 정상입니다(실습용 비밀번호).

4. **샘플 데이터 확인** — 위에서 연 `mysql>` 에서:

   ```sql
   SELECT COUNT(*) FROM shop.users;      -- 200000
   SELECT COUNT(*) FROM shop.products;   -- 20000
   SELECT COUNT(*) FROM shop.orders;     -- 2000000
   SHOW TABLES FROM dba;                 -- cmdb_cluster, cmdb_instance, digest_snapshot, slow_digest_daily, ticket_event, tuning_ticket
   SELECT cluster, collect FROM dba.cmdb_cluster;   -- shop-db 1 · order-db 1
   ```

5. 다음은 [scripts/README.md](../scripts/README.md) 의 14일 시뮬레이션입니다.

## 자주 막히는 곳

| 증상 | 원인 · 해결 |
|---|---|
| `port is already allocated` · `address already in use` (3306 · 3307) | PC 에 다른 MySQL 이 떠 있습니다. 포트를 바꾸지 말고(스크립트가 3306 · 3307 을 씁니다) 기존 MySQL 을 멈춥니다: `brew services stop mysql` 또는 `sudo systemctl stop mysql` |
| `COUNT(*)` 가 200만보다 적거나 테이블이 없다 | 적재가 아직 끝나지 않았거나 중간에 끊겼습니다. 로그를 다시 보고, 끊겼다면 `lab` 에서 `docker compose down -v && docker compose up -d` 로 처음부터 만듭니다 |
| `init/*.sql` 이나 `my.cnf` 를 고쳤는데 반영이 안 된다 | init SQL 은 빈 볼륨에서만 돕니다 → `docker compose down -v` 후 다시 `up`. `my.cnf` 만 고쳤다면 `docker compose restart shop-db order-db` |
| native.sh: `mysql@8.0 이 없습니다` | `brew install mysql@8.0 grafana` 후 다시 `./native.sh up` |
| `Access denied for user` | 계정 · 비밀번호는 [lab/README.md](../README.md) 7장 표의 실습 값입니다(운영에 쓰지 마세요) |

## 다음 단계

- 14일 운영 상황 재현: [scripts/README.md](../scripts/README.md)
- 설정 값과 계정 권한 상세: [docs/01-database-setup.md](../../docs/01-database-setup.md)
- 샘플 데이터의 생성 규칙 · 분포: [docs/02-sample-data.md](../../docs/02-sample-data.md)
- 전체 순서도: [docs/GETTING_STARTED.md](../../docs/GETTING_STARTED.md)
