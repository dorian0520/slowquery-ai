-- @ ===== 13강 인덱스를 못 타는 7가지 패턴 =====
-- @ [s2] ① 컬럼 함수: DATE(ordered_at)  (ordered_at 인덱스가 있어도)
ALTER TABLE orders ADD INDEX ix_od (ordered_at);
EXPLAIN SELECT COUNT(*) FROM orders WHERE DATE(ordered_at) = '2025-03-15';
EXPLAIN SELECT COUNT(*) FROM orders WHERE ordered_at >= '2025-03-15' AND ordered_at < '2025-03-16';
ALTER TABLE orders DROP INDEX ix_od;
-- @ 나머지 패턴에 쓸 인덱스를 만든다
ALTER TABLE orders ADD INDEX ix_cp (coupon_code), ADD INDEX ix_c (user_id, ordered_at), ADD INDEX ix_st (status);
ALTER TABLE users ADD INDEX ix_email (email);
-- @ [s3] ② 형 변환: 문자열 컬럼에 숫자 비교
EXPLAIN SELECT COUNT(*) FROM orders WHERE coupon_code = 29;
EXPLAIN SELECT COUNT(*) FROM orders WHERE coupon_code = '29';
-- @ [s4] ③ 앞쪽 % LIKE
EXPLAIN SELECT user_id FROM users WHERE email LIKE '%1234@example.com';
EXPLAIN SELECT user_id FROM users WHERE email LIKE 'user1234@%';
-- @ [s5] ④ 선두 컬럼 누락: (user_id, ordered_at) 로 날짜만 찾기
EXPLAIN SELECT COUNT(*) FROM orders WHERE ordered_at >= '2025-03-15' AND ordered_at < '2025-03-16';
-- @ [s6] ⑤ 컬럼 연산
EXPLAIN SELECT * FROM orders WHERE order_id + 1 = 1002;
EXPLAIN SELECT * FROM orders WHERE order_id = 1002 - 1;
-- @ [s7] ⑥ 한쪽만 인덱스인 OR
EXPLAIN SELECT * FROM orders WHERE user_id = 1001 OR amount = 50000;
EXPLAIN SELECT * FROM orders WHERE user_id = 1001 OR coupon_code = 'CPN29';
-- @ [s8] ⑦ 선택도 낮은 컬럼: 값이 4종류뿐인 status
EXPLAIN SELECT * FROM orders WHERE status = 'CANCEL';
EXPLAIN SELECT * FROM orders WHERE status != 'CANCEL';
SELECT status, COUNT(*) FROM orders GROUP BY status;
-- @ 정리
ALTER TABLE orders DROP INDEX ix_cp, DROP INDEX ix_c, DROP INDEX ix_st;
ALTER TABLE users DROP INDEX ix_email;
