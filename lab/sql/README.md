# lab/sql — 7~14강 실습 SQL

강의마다 했던 실험(인덱스 만들기 → EXPLAIN · 측정 → 인덱스 지우기)을 **파일 하나씩** 담았습니다. `scripts/sqlrun.py` 로 흘려 넣으면 강의 화면과 같은 순서로 결과가 나옵니다.

## 파일

| 파일 | 주제 | 언제 쓰나 |
|---|---|---|
| `lesson07.sql` | EXPLAIN 컬럼 한 번에 정리 (const · ALL · filesort) | 7강 |
| `lesson08.sql` | EXPLAIN ANALYZE 로 실제 시간 보기 (쿼리를 실제로 실행) | 8강 |
| `lesson09.sql` | 풀 스캔 · filesort · temporary 가 나오는 이유 | 9강 |
| `lesson10.sql` | 조인 순서와 옵티마이저의 선택 | 10강 |
| `lesson11.sql` | 복합 인덱스 컬럼 순서 (세 가지를 하나씩 만들고 지우며 비교) | 11강 |
| `lesson12.sql` | 커버링 인덱스와 정렬 · 그룹핑 | 12강 |
| `lesson13.sql` | 인덱스를 못 타는 7가지 패턴 | 13강 |
| `lesson14.sql` | 서브쿼리 → 조인, OFFSET → 키셋 페이징 | 14강 |
| `reset.sql` | 실습이 중간에 끊겨 남은 임시 인덱스 정리 + 확인 쿼리 | 오류 · 중단 뒤, 사례 실습 뒤 |

파일 안의 `-- @` 로 시작하는 줄은 화면용 설명이라 `sqlrun.py` 가 그대로 출력합니다. 15강(N+1)은 SQL 이 아니라 `scripts/nplus1.py` 입니다.

## 준비물

- MySQL 두 대가 떠 있고 `lab/.venv` 가 준비된 상태 ([lab/README.md](../README.md) 1장)
- 시작 상태: `orders` · `users` 에 PRIMARY 만 있는 상태(simulate 직후). 37~39강 사례 실습을 했다면 먼저 `reset.sql` 로 반영한 인덱스를 지웁니다.

## 따라 하기

1. **`lab` 폴더에서** 강의 번호에 맞는 파일을 흘려 넣습니다.

   ```bash
   cd lab
   .venv/bin/python scripts/sqlrun.py < sql/lesson07.sql
   ```

   정상이면 설명 줄 → `mysql> 문장` → 결과 표 → `(행 수, 초)` 순으로 나옵니다.

   ```
   ===== 7강 EXPLAIN 컬럼 한 번에 정리 =====
   시작 상태: orders 에 PRIMARY 만 있다 (simulate.py 실행 직후)
   [s2] 기본 키로 한 건 → type const
   mysql> EXPLAIN SELECT * FROM orders WHERE order_id = 1001;
   id  select_type  table   partitions  type   possible_keys  key      ...
   1   SIMPLE       orders  NULL        const  PRIMARY        PRIMARY  ...
   (1 rows, 0.001 sec)
   ```

2. 다른 강의도 같은 방법입니다: `sql/lesson08.sql` ~ `sql/lesson14.sql`. 8강처럼 `EXPLAIN ANALYZE` 가 있는 파일은 쿼리를 실제로 실행하므로 몇 초씩 걸립니다.

3. **옵션** (`sqlrun.py`): `--port`(기본 3306, 검증 DB 는 3307) · `--db`(기본 `shop`) · `--user`(기본 `root`) · `--password` · `--keep-going`(오류가 나도 다음 문장 계속).

4. **끊겨서 임시 인덱스가 남았을 때**

   ```bash
   .venv/bin/python scripts/sqlrun.py --keep-going < sql/reset.sql               # shop-db
   .venv/bin/python scripts/sqlrun.py --port 3307 --keep-going < sql/reset.sql   # 검증 DB(order-db)
   ```

   없는 인덱스는 `(건너뜀: Can't DROP 'ix_tmp_user'; check that column/key exists)` 처럼 건너뜁니다. 마지막 확인 쿼리 결과가 **0행**이면 깨끗한 상태입니다.

## 자주 막히는 곳

| 증상 | 원인 · 해결 |
|---|---|
| `Duplicate key name 'ix_…'` 로 멈춤 | 이전 실습의 인덱스가 남아 있습니다. 4단계 `reset.sql` 후 다시 |
| 실행 계획이 강의 화면과 다르다 (type · key) | 다른 인덱스가 남아 있으면 옵티마이저가 그것을 고릅니다. `reset.sql` 로 정리. rows 숫자는 통계 추정치라 조금 달라도 정상 |
| 시간이 강의와 다르다 | PC 성능 차이입니다. 전후 **비율**과 계획 모양을 비교하세요 |

## 다음 단계

- 이 SQL 들이 다루는 느린 쿼리의 출처: [docs/05-slow-query-generation.md](../../docs/05-slow-query-generation.md)
- 자동화 스크립트로 돌아가기: [scripts/README.md](../scripts/README.md)
- 전체 순서도: [docs/GETTING_STARTED.md](../../docs/GETTING_STARTED.md)
