# 02. 샘플 데이터 생성

## 목적

외부 다운로드 없이 **재귀 CTE 로 합성 쇼핑몰 데이터**(회원 20만 · 상품 2만 · 주문 200만)를 만들고, 일부러 인덱스를 최소로 두어 느린 쿼리가 생기게 합니다. 자동화 저장소의 CMDB 에는 클러스터 두 개를 시드합니다.

## 관련 파일

| 파일 | 내용 |
|---|---|
| [lab/mysql/init/01_shop.sql](../lab/mysql/init/01_shop.sql) | `shop` 스키마 · 테이블 · 데이터 |
| [lab/mysql/init/02_dba.sql](../lab/mysql/init/02_dba.sql) | `dba.cmdb_cluster` · `dba.cmdb_instance` 시드 |

## 동작 상세

### 테이블과 인덱스

| 테이블 | 컬럼 | 인덱스 | 코드 |
|---|---|---|---|
| `users` | `user_id INT`, `email VARCHAR(100)`, `grade VARCHAR(10)`, `joined_at DATETIME` | PRIMARY(`user_id`) 만 | [01_shop.sql:6-11](../lab/mysql/init/01_shop.sql#L6) |
| `products` | `product_id INT`, `category VARCHAR(20)`, `name VARCHAR(100)`, `price INT` | PRIMARY(`product_id`) 만 | [01_shop.sql:12-17](../lab/mysql/init/01_shop.sql#L12) |
| `orders` | `order_id BIGINT`, `user_id INT`, `product_id INT`, `status VARCHAR(12)`, `amount INT`, `coupon_code VARCHAR(20) NULL`, `ordered_at DATETIME` | PRIMARY(`order_id`) 만 | [01_shop.sql:19-27](../lab/mysql/init/01_shop.sql#L19) |

"일부러 인덱스를 최소로 둔다: 강의에서 느린 쿼리를 찾고 고치는 대상" ([01_shop.sql:18](../lab/mysql/init/01_shop.sql#L18)). 외래 키도 없습니다.

### 행 생성 규칙

200만 행 재귀를 위해 `cte_max_recursion_depth = 2000001` 로 올립니다([01_shop.sql:29](../lab/mysql/init/01_shop.sql#L29)). `n` 은 1부터 시작하는 일련번호입니다.

**users (20만 행)** — [01_shop.sql:31-36](../lab/mysql/init/01_shop.sql#L31)

| 컬럼 | 식 | 결과 분포 |
|---|---|---|
| `user_id` | `n` | 1 ~ 200,000 |
| `email` | `CONCAT('user', n, '@example.com')` | `user1@example.com` … |
| `grade` | `ELT(1 + n % 4, 'BRONZE','SILVER','GOLD','VIP')` | 네 등급 각 50,000명 (VIP = `n % 4 = 3`) |
| `joined_at` | `'2020-01-01' + INTERVAL (n * 7) MINUTE` | 2020-01-01 00:07 ~ 2022-08-30 05:20 |

**products (2만 행)** — [01_shop.sql:38-42](../lab/mysql/init/01_shop.sql#L38)

| 컬럼 | 식 | 결과 분포 |
|---|---|---|
| `category` | `ELT(1 + n % 8, 'TOP','BOTTOM','OUTER','SHOES','BAG','ACC','BEAUTY','LIFE')` | 8개 분류 각 2,500개 |
| `name` | `CONCAT('상품 ', n)` | |
| `price` | `5000 + (n * 37) % 195000` | 5,007 ~ 199,990 |

**orders (200만 행)** — [01_shop.sql:44-51](../lab/mysql/init/01_shop.sql#L44)

| 컬럼 | 식 | 결과 분포 |
|---|---|---|
| `order_id` | `n` | 1 ~ 2,000,000 |
| `user_id` | `1 + (n * 7919) % 200000` | 7919 와 200000 이 서로소라 **회원마다 정확히 10건** |
| `product_id` | `1 + (n * 104729) % 20000` | 상품마다 정확히 100건 |
| `status` | `ELT(1 + n % 5, 'PAID','PAID','SHIPPED','DONE','CANCEL')` | PAID 40% · SHIPPED 20% · DONE 20% · **CANCEL 20%** (값 4종) |
| `amount` | `5000 + (n * 31) % 300000` | 5,000 ~ 304,999 |
| `coupon_code` | `IF(n % 9 = 0, CONCAT('CPN', n % 500), NULL)` | 222,222행(약 11%)만 값, 나머지 NULL. 코드 `CPN0` ~ `CPN499` 500종, 코드당 444~445건 |
| `ordered_at` | `'2025-01-01' + INTERVAL (n * 15) SECOND` | 2025-01-01 00:00:15 ~ 2025-12-14 05:20:00, `order_id` 와 같은 순서 |

> 위 분포 수치(등급 · 상태 비율, 회원당 10건, 쿠폰 행 수, 날짜 범위)는 식을 그대로 계산한 값입니다. 실습 SQL 의 "10건을 찾으려고 200만 행"([lesson08.sql:5](../lab/sql/lesson08.sql#L5)), "값이 4종류뿐인 status"([lesson13.sql:24](../lab/sql/lesson13.sql#L24)) 와 일치합니다.

### CMDB 시드 (02_dba.sql)

| cluster | engine | realm | tag | service | owner_team | owner | slack_channel | collect |
|---|---|---|---|---|---|---|---|---|
| shop-db | MySQL 8.0 | prod | 주문 | order-api | 주문개발팀 | dev-kim | #order-db-alert | 1 |
| order-db | MySQL 8.0 | prod | 정산 | settle-api | 정산개발팀 | dev-lee | #settle-db-alert | 1 |

[02_dba.sql:82-84](../lab/mysql/init/02_dba.sql#L82). 인스턴스는 `shop-db-1` · `order-db-1` (둘 다 writer, class `lab.local`) — [02_dba.sql:85-87](../lab/mysql/init/02_dba.sql#L85).

CMDB 는 **수집 대상(`collect`) · 티켓 담당자(`owner` · `owner_team`) · 알림 채널 · 대시보드 필터(`realm` · `tag`)** 의 기준입니다([02_dba.sql:63](../lab/mysql/init/02_dba.sql#L63)).

## 실행 방법

별도 명령이 없습니다. 서버 첫 기동 때 init 스크립트가 자동 실행됩니다([01 문서](01-database-setup.md)). 적재에 몇 분 걸립니다.

## 확인 방법

```sql
SELECT COUNT(*) FROM shop.users;      -- 200000
SELECT COUNT(*) FROM shop.products;   -- 20000
SELECT COUNT(*) FROM shop.orders;     -- 2000000
SELECT status, COUNT(*) FROM shop.orders GROUP BY status;          -- PAID 800000 · SHIPPED/DONE/CANCEL 각 400000
SELECT COUNT(coupon_code), COUNT(DISTINCT coupon_code) FROM shop.orders;  -- 222222 · 500
SELECT DISTINCT table_name, index_name FROM information_schema.statistics
 WHERE table_schema = 'shop' AND index_name <> 'PRIMARY';           -- 시뮬레이션 직후에는 0행
```

마지막 쿼리는 [reset.sql:23](../lab/sql/reset.sql#L23) 의 확인 쿼리와 같습니다.

## 주의 · 운영 팁

- 데이터는 결정적입니다(난수 없음). 그래서 shop-db 와 order-db 의 `shop` 데이터가 같고, order-db 를 "복제본"으로 써서 검증할 수 있습니다([verify.py:3](../lab/ai/verify.py#L3)).
- 시뮬레이션 · 실습 SQL 이 인덱스를 만들고 지웁니다. 남은 임시 인덱스는 `sql/reset.sql` 로 정리합니다([05 문서](05-slow-query-generation.md)).
- 모든 데이터는 합성 데이터입니다.

## 다음 단계

→ [03. Grafana 구성](03-grafana.md)
