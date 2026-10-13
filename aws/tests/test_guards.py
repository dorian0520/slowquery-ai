"""SQL 가드 · 근거 도구: AI 가 넘긴 SQL 은 SELECT 한 문장만 실행한다."""
import pytest

from slowq_aws import guards
from slowq_aws.tools import Tools


@pytest.mark.parametrize("sql", [
    "SELECT * FROM orders WHERE user_id = 1",
    "select status, COUNT(*) from orders group by status;",                 # 끝 세미콜론 하나는 허용
    "SELECT * FROM orders WHERE note = 'for update; drop table x'",          # 문자열 안 단어는 키워드가 아님
])
def test_select_only_accepts(sql):
    assert guards.select_only(sql).lower().startswith("select")


@pytest.mark.parametrize("sql", [
    "", "   ", None,
    "UPDATE orders SET amount = 0",
    "DELETE FROM orders",
    "EXPLAIN ANALYZE SELECT 1",
    "SELECT 1; DROP TABLE orders",
    "SELECT * FROM orders -- comment",
    "SELECT * FROM orders /* x */",
    "SELECT * FROM orders INTO OUTFILE '/tmp/x'",
    "SELECT * FROM orders FOR UPDATE",
    "SELECT SLEEP(10)",
    "SELECT BENCHMARK(1000000, MD5('a'))",
    "WITH x AS (SELECT 1) SELECT * FROM x",
])
def test_select_only_rejects(sql):
    with pytest.raises(guards.UnsafeSQL):
        guards.select_only(sql)


def test_explain_rejects_non_select_without_touching_db(fake_conn):
    shop = fake_conn()
    t = Tools(store=fake_conn(), shop=shop, cluster="shop-db")
    out, is_err = t.call("explain", {"sql": "DELETE FROM orders"})
    assert is_err and "거부" in out["error"]
    assert shop.executed == []                                   # DB 에 아무것도 보내지 않았다


def test_explain_masks_string_values_keeps_numbers(fake_conn):
    plan = "-> Filter: (orders.coupon_code = 'CPN29')  (cost=201068 rows=1.99e+6)"
    shop = fake_conn(rules=[(r"^EXPLAIN FORMAT=TREE", [{"EXPLAIN": plan}])])
    out, is_err = Tools(fake_conn(), shop, "shop-db").call("explain", {"sql": "SELECT * FROM orders WHERE coupon_code='CPN29'"})
    assert not is_err
    assert "CPN29" not in out and "'?'" in out and "201068" in out


def test_table_info_rejects_bad_name(fake_conn):
    shop = fake_conn()
    out, is_err = Tools(fake_conn(), shop, "shop-db").call("table_info", {"table": "orders`; DROP TABLE x"})
    assert is_err and shop.executed == []


def test_unknown_tool(fake_conn):
    out, is_err = Tools(fake_conn(), fake_conn(), "c").call("run_sql", {"sql": "x"})
    assert is_err and "알 수 없는 도구" in out["error"]


def test_top_queries_limit_is_capped(fake_conn):
    store = fake_conn()
    Tools(store, fake_conn(), "shop-db").call("top_queries", {"log_date": "2026-10-12", "limit": 999})
    assert store.executed[0][1][-1] == 20


def test_first_ddl():
    assert guards.first_ddl("1) ALTER TABLE orders ADD INDEX ix (a, b); 2) keyset") == "ALTER TABLE orders ADD INDEX ix (a, b)"
    assert guards.first_ddl("쿼리를 재작성합니다") is None
