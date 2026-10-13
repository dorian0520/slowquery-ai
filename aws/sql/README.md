# aws/sql — AWS 용 저장소 스키마

AWS 버전의 자동화 저장소 `dba` 를 만드는 SQL 한 파일이 있습니다. `skeleton/schema.sql` 과 같은 테이블 5개에, Grafana 대시보드가 읽는 열 몇 개를 더했습니다. **직접 실행하지 않아도 됩니다** — `slowq-init-db` Lambda 가 대상 DB(`shop-db`)에 적용합니다.

## 파일

| 파일 | 역할 | 언제 쓰나 |
|---|---|---|
| `02_store.sql` | `dba` 데이터베이스와 테이블 5개(`cmdb_cluster` · `digest_snapshot` · `slow_digest_daily` · `tuning_ticket` · `ticket_event`). 모두 `IF NOT EXISTS` 라 여러 번 실행해도 안전 | `init-db` 가 자동 적용 · 스키마를 확인할 때 |

skeleton 스키마와 다른 점 (파일 머리 주석 기준):

| 열 | 왜 있나 |
|---|---|
| `slow_digest_daily.max_sec` | 대시보드 순위 패널용. skeleton 수집기는 채우지 않아 `NULL` (대시보드 「최대초」 열이 비는 이유) |
| `tuning_ticket.verified` | 실측 검증 통과 여부 (Attach 단계가 기록) |
| `tuning_ticket.updated_at` | 대시보드 티켓 패널 정렬용 (자동 갱신) |

## 준비물

- 파일을 읽기만 할 때: 없음
- 적용 결과를 확인할 때: 배포 완료 + `init-db` 실행 완료 ([lambda/README.md](../lambda/README.md) 3단계)

## 따라 하기

1. **적용은 Lambda 가 합니다** — `init-db` 실행 시 `build/function.zip` 안의 `sql/02_store.sql` 이 쓰입니다. 그래서 이 파일을 고쳤다면 `aws` 에서 `scripts/build.sh` → `terraform apply` → `init-db` 다시 실행 순서로 반영합니다.

2. **어떤 테이블이 만들어지는지 보기** — 저장소 루트에서 (DB 없이):

   ```bash
   grep -n "CREATE TABLE" aws/sql/02_store.sql
   ```

   ```
   10:CREATE TABLE IF NOT EXISTS cmdb_cluster (
   22:CREATE TABLE IF NOT EXISTS digest_snapshot (
   35:CREATE TABLE IF NOT EXISTS slow_digest_daily (
   49:CREATE TABLE IF NOT EXISTS tuning_ticket (
   66:CREATE TABLE IF NOT EXISTS ticket_event (
   ```

3. **AWS 에서 적용 결과 확인** — RDS 는 프라이빗 서브넷이라 바로 접속할 수 없습니다. Grafana 대시보드에 데이터가 나오는지로 확인하는 것이 가장 쉽습니다 ([grafana/README.md](../grafana/README.md)).

## 자주 막히는 곳

| 증상 | 원인 · 해결 |
|---|---|
| 스키마를 고쳤는데 AWS 에 반영되지 않았다 | zip 을 다시 만들어야 합니다: `scripts/build.sh` → `terraform apply` → `init-db` |
| 기존 테이블에 열을 추가했는데 반영이 안 된다 | `CREATE TABLE IF NOT EXISTS` 는 이미 있는 테이블을 바꾸지 않습니다. 열 추가는 별도 `ALTER TABLE` 이 필요합니다 |
| 대시보드 「최대초」 열이 비어 있다 | 정상입니다 (`max_sec` 은 `NULL`, [aws/README.md](../README.md) 9장) |

## 다음 단계

- 이 스키마의 원본과 설명: [skeleton/README.md](../../skeleton/README.md) · [docs/00-flow.md](../../docs/00-flow.md) 4장(저장소 테이블 관계)
- `init-db` 실행: [lambda/README.md](../lambda/README.md)
- 전체 순서도: [docs/GETTING_STARTED.md](../../docs/GETTING_STARTED.md)
