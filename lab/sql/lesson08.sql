-- @ ===== 8강 EXPLAIN ANALYZE로 실제 시간 보기 =====
-- @ 주의: EXPLAIN ANALYZE 는 쿼리를 실제로 실행한다
-- @ [s2] 안쪽부터 읽기: 쿠폰 집계
EXPLAIN ANALYZE SELECT COUNT(*), SUM(amount) FROM orders WHERE coupon_code = 'CPN29';
-- @ [s4] 10건을 찾으려고 200만 행 → 정렬
EXPLAIN ANALYZE SELECT order_id, amount, status, ordered_at FROM orders WHERE user_id = 1001 ORDER BY ordered_at DESC LIMIT 20;
-- @ [s5] 확인용 인덱스 하나로 다시
ALTER TABLE orders ADD INDEX ix_tmp_user (user_id);
EXPLAIN ANALYZE SELECT order_id, amount, status, ordered_at FROM orders WHERE user_id = 1001 ORDER BY ordered_at DESC LIMIT 20;
-- @ 정리
ALTER TABLE orders DROP INDEX ix_tmp_user;
