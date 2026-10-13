-- @ ===== 9강 풀 스캔 · filesort · temporary 가 나오는 이유 =====
-- @ [s2] 조건 컬럼에 인덱스가 없으면 type ALL
EXPLAIN SELECT COUNT(*), SUM(amount) FROM orders WHERE coupon_code = 'CPN29';
-- @ [s3] 정렬 순서의 인덱스가 없으면 Using filesort
EXPLAIN SELECT order_id, user_id, amount FROM orders ORDER BY ordered_at DESC LIMIT 300000, 20;
-- @ [s4] 그룹핑을 인덱스로 못 하면 Using temporary
EXPLAIN SELECT status, COUNT(*) FROM orders WHERE ordered_at >= '2025-03-15' AND ordered_at < '2025-03-15' + INTERVAL 1 DAY GROUP BY status;
-- @ [s5] 날짜 인덱스가 있으면 읽는 행이 하루치로
ALTER TABLE orders ADD INDEX ix_tmp_ordered (ordered_at);
EXPLAIN SELECT status, COUNT(*) FROM orders WHERE ordered_at >= '2025-03-15' AND ordered_at < '2025-03-16' GROUP BY status;
-- @ 정리
ALTER TABLE orders DROP INDEX ix_tmp_ordered;
