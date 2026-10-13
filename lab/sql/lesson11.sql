-- @ ===== 11강 복합 인덱스 컬럼 순서 =====
-- @ 인덱스 세 가지를 하나씩 만들고 지우며 비교한다 (동시에 있으면 옵티마이저가 골라 버린다)
-- @ [s2] 인덱스 없음
EXPLAIN ANALYZE SELECT order_id, amount, status, ordered_at FROM orders WHERE user_id = 1001 ORDER BY ordered_at DESC LIMIT 20;
-- @ [s3] (ordered_at, user_id) — 오히려 느려진다
ALTER TABLE orders ADD INDEX ix_a (ordered_at, user_id);
EXPLAIN SELECT order_id, amount, status, ordered_at FROM orders WHERE user_id = 1001 ORDER BY ordered_at DESC LIMIT 20;
EXPLAIN ANALYZE SELECT order_id, amount, status, ordered_at FROM orders WHERE user_id = 1001 ORDER BY ordered_at DESC LIMIT 20;
ALTER TABLE orders DROP INDEX ix_a;
-- @ [s4] (user_id) — 찾기는 빠르지만 정렬이 남는다
ALTER TABLE orders ADD INDEX ix_b (user_id);
EXPLAIN SELECT order_id, amount, status, ordered_at FROM orders WHERE user_id = 1001 ORDER BY ordered_at DESC LIMIT 20;
ALTER TABLE orders DROP INDEX ix_b;
-- @ [s5] (user_id, ordered_at) — 찾기와 정렬을 한 번에
ALTER TABLE orders ADD INDEX ix_c (user_id, ordered_at);
EXPLAIN SELECT order_id, amount, status, ordered_at FROM orders WHERE user_id = 1001 ORDER BY ordered_at DESC LIMIT 20;
EXPLAIN ANALYZE SELECT order_id, amount, status, ordered_at FROM orders WHERE user_id = 1001 ORDER BY ordered_at DESC LIMIT 20;
-- @ 정리
ALTER TABLE orders DROP INDEX ix_c;
