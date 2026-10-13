-- @ ===== 12강 커버링 인덱스와 정렬 · 그룹핑 =====
-- @ [s2] (coupon_code): 인덱스로 찾고 금액을 보러 테이블을 다녀온다
ALTER TABLE orders ADD INDEX ix_cp (coupon_code);
EXPLAIN ANALYZE SELECT COUNT(*), SUM(amount) FROM orders WHERE coupon_code = 'CPN29';
ALTER TABLE orders DROP INDEX ix_cp;
-- @ [s3] (coupon_code, amount) 커버링: 인덱스만으로 끝
ALTER TABLE orders ADD INDEX ix_cp_amt (coupon_code, amount);
EXPLAIN SELECT COUNT(*), SUM(amount) FROM orders WHERE coupon_code = 'CPN29';
EXPLAIN ANALYZE SELECT COUNT(*), SUM(amount) FROM orders WHERE coupon_code = 'CPN29';
ALTER TABLE orders DROP INDEX ix_cp_amt;
-- @ [s4] 하루치 status 집계: (ordered_at) 와 (ordered_at, status) 비교
ALTER TABLE orders ADD INDEX ix_od (ordered_at);
EXPLAIN ANALYZE SELECT status, COUNT(*) FROM orders WHERE ordered_at >= '2025-03-15' AND ordered_at < '2025-03-16' GROUP BY status;
ALTER TABLE orders DROP INDEX ix_od;
ALTER TABLE orders ADD INDEX ix_od_st (ordered_at, status);
EXPLAIN ANALYZE SELECT status, COUNT(*) FROM orders WHERE ordered_at >= '2025-03-15' AND ordered_at < '2025-03-16' GROUP BY status;
ALTER TABLE orders DROP INDEX ix_od_st;
-- @ [s5] temporary 를 없애려고 (status, ordered_at) 를 만들면 200만 행을 읽는다
ALTER TABLE orders ADD INDEX ix_st_od (status, ordered_at);
EXPLAIN SELECT status, COUNT(*) FROM orders WHERE ordered_at >= '2025-03-15' AND ordered_at < '2025-03-16' GROUP BY status;
EXPLAIN ANALYZE SELECT status, COUNT(*) FROM orders WHERE ordered_at >= '2025-03-15' AND ordered_at < '2025-03-16' GROUP BY status;
-- @ 정리
ALTER TABLE orders DROP INDEX ix_st_od;
