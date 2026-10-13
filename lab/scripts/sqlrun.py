"""강의 화면용 SQL 실행기: 여러 문장을 실행하고 mysql 클라이언트 비슷한 표로 출력한다.

python3 sqlrun.py [--port 3306] [--db shop] [--user root] [--keep-going] < queries.sql
문장은 ';' 로 끝나는 줄 단위로 나눈다. '-- @' 로 시작하는 줄은 화면용 주석으로 그대로 출력.
"""
import argparse, sys, time
import pymysql


def fmt(rows, cols):
    if not cols:
        return ""
    data = [[("NULL" if v is None else str(v)) for v in r] for r in rows]
    w = [max([len(c)] + [len(r[i]) for r in data]) for i, c in enumerate(cols)]
    line = "  ".join(c.ljust(w[i]) for i, c in enumerate(cols))
    body = ["  ".join(r[i].ljust(w[i]) for i in range(len(cols))) for r in data]
    return "\n".join([line] + body)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=3306)
    p.add_argument("--db", default="shop")
    p.add_argument("--user", default="root")
    p.add_argument("--password", default="lab-root-pw")
    p.add_argument("--keep-going", action="store_true", help="오류가 나도 다음 문장을 계속 실행 (reset.sql 용)")
    a = p.parse_args()
    conn = pymysql.connect(host="127.0.0.1", port=a.port, user=a.user, password=a.password,
                           database=a.db, charset="utf8mb4", autocommit=True)
    buf = ""
    for raw in sys.stdin:
        if raw.startswith("-- @"):
            print(raw[4:].rstrip())
            continue
        buf += raw
        if raw.rstrip().endswith(";"):
            sql = buf.strip()
            buf = ""
            print(f"mysql> {sql}")
            with conn.cursor() as cur:
                t = time.perf_counter()
                try:
                    cur.execute(sql)
                except pymysql.MySQLError as e:
                    if not a.keep_going:
                        raise
                    print(f"(건너뜀: {e.args[-1]})\n")
                    continue
                dt = time.perf_counter() - t
                cols = [d[0] for d in cur.description] if cur.description else []
                rows = cur.fetchall() if cols else []
                out = fmt(rows, cols)
                if out:
                    print(out)
                print(f"({len(rows) if cols else cur.rowcount} rows, {dt:.3f} sec)\n")
    conn.close()


if __name__ == "__main__":
    main()
