-- 실습용 가상 쇼핑몰 스키마 + 데이터 생성 (외부 데이터 다운로드 없음)
-- users 20만 · products 2만 · orders 200만
CREATE DATABASE IF NOT EXISTS shop;
USE shop;

CREATE TABLE users (
  user_id     INT PRIMARY KEY,
  email       VARCHAR(100) NOT NULL,
  grade       VARCHAR(10)  NOT NULL,
  joined_at   DATETIME     NOT NULL
);
CREATE TABLE products (
  product_id  INT PRIMARY KEY,
  category    VARCHAR(20) NOT NULL,
  name        VARCHAR(100) NOT NULL,
  price       INT NOT NULL
);
-- 일부러 인덱스를 최소로 둔다: 강의에서 느린 쿼리를 찾고 고치는 대상
CREATE TABLE orders (
  order_id    BIGINT PRIMARY KEY,
  user_id     INT NOT NULL,
  product_id  INT NOT NULL,
  status      VARCHAR(12) NOT NULL,
  amount      INT NOT NULL,
  coupon_code VARCHAR(20) NULL,
  ordered_at  DATETIME NOT NULL
);

SET SESSION cte_max_recursion_depth = 2000001;

INSERT INTO users
WITH RECURSIVE s(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM s WHERE n < 200000)
SELECT n, CONCAT('user', n, '@example.com'),
       ELT(1 + n % 4, 'BRONZE', 'SILVER', 'GOLD', 'VIP'),
       '2020-01-01' + INTERVAL (n * 7) MINUTE
FROM s;

INSERT INTO products
WITH RECURSIVE s(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM s WHERE n < 20000)
SELECT n, ELT(1 + n % 8, 'TOP', 'BOTTOM', 'OUTER', 'SHOES', 'BAG', 'ACC', 'BEAUTY', 'LIFE'),
       CONCAT('상품 ', n), 5000 + (n * 37) % 195000
FROM s;

INSERT INTO orders
WITH RECURSIVE s(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM s WHERE n < 2000000)
SELECT n, 1 + (n * 7919) % 200000, 1 + (n * 104729) % 20000,
       ELT(1 + n % 5, 'PAID', 'PAID', 'SHIPPED', 'DONE', 'CANCEL'),
       5000 + (n * 31) % 300000,
       IF(n % 9 = 0, CONCAT('CPN', n % 500), NULL),
       '2025-01-01' + INTERVAL (n * 15) SECOND
FROM s;
