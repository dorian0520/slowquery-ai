-- @ ===== 7강 EXPLAIN 컬럼 한 번에 정리 =====
-- @ 시작 상태: orders 에 PRIMARY 만 있다 (simulate.py 실행 직후)
-- @ [s2] 기본 키로 한 건 → type const
EXPLAIN SELECT * FROM orders WHERE order_id = 1001;
-- @ [s3] 주문 목록 쿼리 → type ALL + Using filesort
EXPLAIN SELECT order_id, amount, status, ordered_at FROM orders WHERE user_id = 1001 ORDER BY ordered_at DESC LIMIT 20;
-- @ [s5] 인덱스를 잠시 만들고 ref · range · index 보기
ALTER TABLE orders ADD INDEX ix_tmp_user (user_id), ADD INDEX ix_tmp_ordered (ordered_at);
EXPLAIN SELECT * FROM orders WHERE user_id = 1001;
EXPLAIN SELECT * FROM orders WHERE ordered_at >= '2025-03-15' AND ordered_at < '2025-03-16';
EXPLAIN SELECT COUNT(*) FROM orders;
-- @ 정리: 만든 인덱스를 지운다
ALTER TABLE orders DROP INDEX ix_tmp_user, DROP INDEX ix_tmp_ordered;
