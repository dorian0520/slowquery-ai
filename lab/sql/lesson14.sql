-- @ ===== 14강 서브쿼리 → 조인, OFFSET → 키셋 페이징 =====
-- @ [s2] ordered_at 인덱스가 있어도 깊은 OFFSET 은 0.5초대
ALTER TABLE orders ADD INDEX ix_od (ordered_at);
EXPLAIN SELECT order_id, user_id, amount, ordered_at FROM orders ORDER BY ordered_at DESC LIMIT 300000, 20;
SELECT order_id, user_id, amount, ordered_at FROM orders ORDER BY ordered_at DESC LIMIT 300000, 20;
-- @ [s3] 키셋: 직전 페이지 마지막 행의 ordered_at 부터 (값은 위 결과의 마지막 행으로 바꿔도 된다)
EXPLAIN SELECT order_id, user_id, amount, ordered_at FROM orders WHERE ordered_at < '2025-10-23 03:15:15' ORDER BY ordered_at DESC LIMIT 20;
SELECT order_id, user_id, amount, ordered_at FROM orders WHERE ordered_at < '2025-10-23 03:15:15' ORDER BY ordered_at DESC LIMIT 20;
ALTER TABLE orders DROP INDEX ix_od;
-- @ [s5] 회원마다 서브쿼리 반복 (orders.user_id 인덱스 없음)
SELECT u.user_id, (SELECT MAX(o.ordered_at) FROM orders o WHERE o.user_id = u.user_id) AS last_order FROM users u WHERE u.grade = 'VIP' ORDER BY u.user_id LIMIT 10;
-- @ [s6] 같은 10명을 먼저 고르고 한 번만 조인
SELECT u.user_id, MAX(o.ordered_at) AS last_order FROM (SELECT user_id FROM users WHERE grade = 'VIP' ORDER BY user_id LIMIT 10) u JOIN orders o ON o.user_id = u.user_id GROUP BY u.user_id ORDER BY u.user_id;
