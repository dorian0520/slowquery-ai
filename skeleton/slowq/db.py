"""DB 연결과 스키마 적용."""
import pymysql


def connect(dsn):
    if dsn.get("password") is None:
        raise ValueError(f"비밀번호가 없습니다 ({dsn.get('user')}@{dsn.get('host')}) — password_env 환경 변수를 확인하세요")
    return pymysql.connect(host=dsn["host"], port=int(dsn.get("port", 3306)), user=dsn["user"], password=dsn["password"],
                           database=dsn.get("database"), charset="utf8mb4", autocommit=True,
                           cursorclass=pymysql.cursors.DictCursor)


def apply_schema(conn, path):
    with open(path, encoding="utf-8") as f:
        sql = f.read()
    stmts = [s.strip() for s in "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--")).split(";")]
    with conn.cursor() as cur:
        for s in stmts:
            if s:
                cur.execute(s)
