-- @ ===== 10강 조인 순서와 옵티마이저의 선택 =====
-- @ [s3] 인덱스 없음: 주문부터 읽고 95만 번 회원을 찾는다
EXPLAIN ANALYZE SELECT u.grade, SUM(o.amount) FROM orders o JOIN users u ON u.user_id = o.user_id WHERE u.grade = 'VIP' AND o.ordered_at >= '2025-07-01' GROUP BY u.grade;
-- @ [s4] (user_id, ordered_at) 인덱스: 회원부터 읽고 5만 번만 주문을 찾는다
ALTER TABLE orders ADD INDEX ix_tmp_user_ordered (user_id, ordered_at);
EXPLAIN ANALYZE SELECT u.grade, SUM(o.amount) FROM orders o JOIN users u ON u.user_id = o.user_id WHERE u.grade = 'VIP' AND o.ordered_at >= '2025-07-01' GROUP BY u.grade;
-- @ [s6] STRAIGHT_JOIN 으로 회원 → 주문 순서를 강제해도 같은 결과 (인덱스가 있을 때)
SELECT STRAIGHT_JOIN u.grade, SUM(o.amount) FROM users u JOIN orders o ON u.user_id = o.user_id WHERE u.grade = 'VIP' AND o.ordered_at >= '2025-07-01' GROUP BY u.grade;
-- @ 정리
ALTER TABLE orders DROP INDEX ix_tmp_user_ordered;
