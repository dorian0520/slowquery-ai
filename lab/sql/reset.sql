-- @ 실습이 중간에 끊겨 임시 인덱스가 남았을 때 정리한다
-- @ 실행: .venv/bin/python scripts/sqlrun.py --keep-going < sql/reset.sql   (없는 인덱스는 건너뜀 · 검증 DB 는 --port 3307)
ALTER TABLE orders DROP INDEX ix_tmp_user;
-- @ (simulate.py 가 중간에 끊겼을 때 남는 인덱스)
ALTER TABLE orders DROP INDEX ix_user_ordered;
ALTER TABLE orders DROP INDEX ix_tmp_ordered;
ALTER TABLE orders DROP INDEX ix_tmp_user_ordered;
ALTER TABLE orders DROP INDEX ix_a;
ALTER TABLE orders DROP INDEX ix_b;
ALTER TABLE orders DROP INDEX ix_c;
ALTER TABLE orders DROP INDEX ix_cp;
ALTER TABLE orders DROP INDEX ix_cp_amt;
ALTER TABLE orders DROP INDEX ix_od;
ALTER TABLE orders DROP INDEX ix_od_st;
ALTER TABLE orders DROP INDEX ix_st;
ALTER TABLE orders DROP INDEX ix_st_od;
ALTER TABLE users DROP INDEX ix_email;
-- @ (37~39강 사례 실습에서 운영 반영한 인덱스도 지운다 — 사례 실습 상태를 유지하려면 아래 한 줄을 빼고 실행)
ALTER TABLE orders DROP INDEX ix_orders_user_ordered;
-- @ (26강 verify.py 가 중간에 끊겼을 때 검증 DB 에 남는 인덱스)
ALTER TABLE orders DROP INDEX ix_orders_ordered;
ALTER TABLE orders DROP INDEX ix_orders_coupon_amount;
SELECT DISTINCT table_name, index_name FROM information_schema.statistics WHERE table_schema = 'shop' AND index_name <> 'PRIMARY';
