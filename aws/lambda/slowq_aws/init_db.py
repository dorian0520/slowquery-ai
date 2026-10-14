"""init_db (한 번만 실행): 샘플 서비스 스키마 · 데이터, 자동화 저장소 스키마, 최소 권한 계정, CMDB 를 만든다.

aws lambda invoke --function-name <prefix>-init-db --payload '{}' out.json        # 두 DB 모두
aws lambda invoke ... --payload '{"only": "verify"}' out.json                     # 검증 DB 만 (시간이 모자라 나눠 돌릴 때)

- 접속은 RDS 가 관리하는 마스터 비밀(manage_master_user_password)로 한다. 비밀번호는 출력하지 않는다.
- 샘플 데이터는 lab/mysql/init/01_shop.sql 을 그대로 쓴다 (빌드 때 패키지의 sql/ 로 복사).
- 여러 번 실행해도 안전하다: 데이터가 이미 있으면 건너뛰고, 계정은 비밀의 비밀번호로 다시 맞춘다.
"""
import os

from slowq.db import apply_schema

from . import common

SQL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sql")
EXPECTED_ORDERS = 2_000_000
NEED_SEC_FOR_SAMPLE = 420          # 샘플 데이터 한 벌을 만드는 데 남겨 둘 최소 시간(초)


class InitError(RuntimeError):
    pass


def master_conn(host, secret_arn):
    # RDS 관리 비밀의 키 이름은 username / password 라 common.connect 를 그대로 쓴다
    return common.connect(host, secret_arn, None, connect_timeout=15, read_timeout=890)


def shop_state(cur, shop_db):
    cur.execute("SELECT COUNT(*) AS n FROM information_schema.schemata WHERE schema_name=%s", (shop_db,))
    if not cur.fetchone()["n"]:
        return "absent"
    cur.execute("SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema=%s AND table_name='orders'", (shop_db,))
    if not cur.fetchone()["n"]:
        return "partial"
    cur.execute(f"SELECT COUNT(*) AS n FROM `{shop_db}`.orders")
    return "ready" if cur.fetchone()["n"] >= EXPECTED_ORDERS else "partial"


def load_sample(conn, shop_db="shop", reset=False):
    """01_shop.sql 적용. 반쯤 만들어진 상태면 reset=True 일 때만 지우고 다시 만든다."""
    with conn.cursor() as cur:
        st = shop_state(cur, shop_db)
        if st == "ready":
            return "skip (이미 있음)"
        if st == "partial":
            if not reset:
                raise InitError(f"{shop_db} 가 덜 만들어져 있습니다. 샘플 DB 를 지우고 다시 만들려면 payload 에 "
                                '{"reset_shop": true} 를 넣어 다시 실행하세요')
            cur.execute(f"DROP DATABASE `{shop_db}`")     # 이 스택이 만든 샘플 스키마만 대상
    apply_schema(conn, os.path.join(SQL_DIR, "01_shop.sql"))
    return "created"


def accounts(store_db, shop_db):
    """(비밀 환경 변수, 대상(target/verify), 권한 목록). 권한은 필요한 것만."""
    return [
        ("COLLECTOR_SECRET_ARN", "target", ["GRANT SELECT ON performance_schema.* TO {u}"]),
        ("STORE_SECRET_ARN", "target", [f"GRANT SELECT, INSERT, UPDATE, DELETE ON `{store_db}`.* TO {{u}}"]),
        ("AI_SECRET_ARN", "target", [f"GRANT SELECT ON `{shop_db}`.* TO {{u}}",
                                      f"GRANT SELECT ON `{store_db}`.`slow_digest_daily` TO {{u}}"]),
        ("GRAFANA_SECRET_ARN", "target", [f"GRANT SELECT ON `{store_db}`.* TO {{u}}"]),
        ("WORKLOAD_SECRET_ARN", "target", [f"GRANT SELECT ON `{shop_db}`.* TO {{u}}"]),
        # 검증 계정: 검증 DB 의 서비스 스키마에서만 인덱스 추가 · 삭제 (ALTER TABLE 은 ALTER · CREATE · INSERT 가 필요)
        ("VERIFY_SECRET_ARN", "verify", [f"GRANT SELECT, ALTER, INDEX, CREATE, INSERT ON `{shop_db}`.* TO {{u}}"]),
    ]


def ensure_user(cur, username, password, grants):
    cur.execute("CREATE USER IF NOT EXISTS %s@'%%' IDENTIFIED BY %s", (username, password))
    cur.execute("ALTER USER %s@'%%' IDENTIFIED BY %s", (username, password))     # 비밀이 바뀌었으면 맞춘다
    u = cur.mogrify("%s@'%%'", (username,))
    for g in grants:
        cur.execute(g.format(u=u))


def seed_cmdb(cur, store_db, target_host, verify_host):
    rows = [("shop-db", target_host, 3306, "prod", "주문", "dev-kim", "주문개발팀", "#shop-db-alert", 1),
            # 검증 DB 는 실측 검증 부하가 섞이므로 기본은 수집하지 않는다(collect=0)
            ("order-db", verify_host, 3306, "verify", "검증", "dev-lee", "검증담당", "#order-db-alert", 0)]
    cur.executemany(f"""INSERT INTO `{store_db}`.cmdb_cluster
                          (cluster, host, port, realm, tag, owner, owner_team, slack_channel, collect)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE host=VALUES(host), port=VALUES(port)""", rows)


def handler(event, context):
    event = event or {}
    only = event.get("only")             # None | "target" | "verify"
    if only not in (None, "target", "verify"):
        raise InitError("only 는 target 또는 verify 여야 합니다")
    reset = event.get("reset_shop", False)
    if not isinstance(reset, bool):
        raise InitError("reset_shop 은 JSON true/false 여야 합니다")
    store_db, shop_db = common.env("STORE_DB", "dba"), common.env("SHOP_DB", "shop")
    hosts = {"target": common.env("TARGET_HOST", required=True), "verify": common.env("VERIFY_HOST", required=True)}
    masters = {"target": common.env("TARGET_MASTER_SECRET_ARN", required=True),
               "verify": common.env("VERIFY_MASTER_SECRET_ARN", required=True)}
    done = {}
    for which in ("target", "verify"):
        if only and only != which:
            continue
        remaining = context.get_remaining_time_in_millis() / 1000 if context else 900
        if done and remaining < NEED_SEC_FOR_SAMPLE:
            done[which] = f'시간 부족 — payload {{"only": "{which}"}} 로 다시 실행하세요'
            continue
        conn = master_conn(hosts[which], masters[which])
        try:
            with conn.cursor() as cur:
                cur.execute("SET SESSION cte_max_recursion_depth = 2000001")
            sample = load_sample(conn, shop_db, reset)
            if which == "target":
                apply_schema(conn, os.path.join(SQL_DIR, "02_store.sql"))
            with conn.cursor() as cur:
                for secret_env, where, grants in accounts(store_db, shop_db):
                    if where != which:
                        continue
                    s = common.get_secret(common.env(secret_env, required=True))
                    ensure_user(cur, s["username"], s["password"], grants)
                if which == "target":
                    seed_cmdb(cur, store_db, hosts["target"], hosts["verify"])
            done[which] = f"샘플 {sample} · 계정 적용"
        finally:
            conn.close()
    common.log.info("init_db %s", done)
    return done
