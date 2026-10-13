"""섹션 5 · 24강: 실습 DB 읽기 전용 MCP 서버

AI 가 할 수 있는 일을 네 가지 도구로만 제한한다.
- top_queries : 일자별 슬로우 쿼리 상위 목록 (dba 저장소)
- table_info  : 테이블 구조 · 인덱스 · 행 수
- explain     : SELECT 문의 실행 계획 (EXPLAIN FORMAT=TREE — 실제 실행은 하지 않음)
- query_trend : 쿼리 지문 하나의 일자별 추이
"""
import os, re, sys
import pymysql
from mcp.server.mcpserver import MCPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from mask import PATTERNS  # 19강 마스킹 패턴 재사용 (계획에서는 문자열 값만 지운다)

PORTS = {"shop-db": 3306, "order-db": 3307}
USER, PASSWORD = "lab_ai", "lab-ai-pw"   # 로컬 실습 전용 계정 (SELECT 만)

server = MCPServer("labdb", instructions="실습 MySQL 읽기 전용 도구. 운영 변경 불가. EXPLAIN 은 SELECT 만 허용.")


def q(cluster, sql, args=None, db="dba"):
    if cluster not in PORTS:
        raise ValueError(f"알 수 없는 클러스터: {cluster}")
    with pymysql.connect(host="127.0.0.1", port=PORTS[cluster], user=USER, password=PASSWORD,
                         database=db, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor) as c:
        with c.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall()


@server.tool(description="일자별 슬로우 쿼리 상위 목록(총 부하 순). log_date 형식 YYYY-MM-DD")
def top_queries(log_date: str, cluster: str = "shop-db", limit: int = 10) -> list[dict]:
    rows = q("shop-db", """SELECT cluster, qhash, query_text, exec_cnt, ROUND(avg_sec,4) avg_sec,
                                  ROUND(total_sec,2) total_sec, rows_examined
                           FROM slow_digest_daily WHERE log_date=%s AND cluster=%s
                           ORDER BY total_sec DESC LIMIT %s""", (log_date, cluster, int(limit)))
    return rows


@server.tool(description="테이블 구조(SHOW CREATE TABLE), 인덱스 목록, 대략적 행 수")
def table_info(table: str, cluster: str = "shop-db") -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_]+", table):
        raise ValueError("테이블 이름 형식이 아닙니다")
    ddl = q(cluster, f"SHOW CREATE TABLE `{table}`", db="shop")[0]["Create Table"]
    idx = q(cluster, f"SHOW INDEX FROM `{table}`", db="shop")
    rows = q(cluster, "SELECT TABLE_ROWS FROM information_schema.tables WHERE table_schema='shop' AND table_name=%s",
             (table,))[0]["TABLE_ROWS"]
    return {"ddl": ddl, "indexes": [{k: i[k] for k in ("Key_name", "Seq_in_index", "Column_name", "Cardinality")} for i in idx],
            "approx_rows": rows}


@server.tool(description="SELECT 문 한 개의 실행 계획(EXPLAIN FORMAT=TREE). 쿼리를 실제로 실행하지 않는다. 값 자리에는 테스트 값을 넣을 것")
def explain(sql: str, cluster: str = "shop-db") -> str:
    s = sql.strip().rstrip(";")
    if not re.match(r"(?is)^\s*select\b", s) or ";" in s or re.search(r"(?i)\b(into\s+outfile|for\s+update|sleep\s*\()", s):
        raise ValueError("SELECT 한 문장만 허용합니다")
    plan = q(cluster, "EXPLAIN FORMAT=TREE " + s, db="shop")[0]["EXPLAIN"]
    # 계획에서는 문자열 값만 지운다. 숫자까지 지우면 rows · cost 근거가 사라진다 (실습에서 발견)
    return PATTERNS[0][0].sub(PATTERNS[0][1], plan)


@server.tool(description="쿼리 지문(qhash) 하나의 일자별 실행 횟수 · 평균 시간 추이")
def query_trend(qhash: str, cluster: str = "shop-db") -> list[dict]:
    return q("shop-db", """SELECT log_date, exec_cnt, ROUND(avg_sec,4) avg_sec, ROUND(total_sec,2) total_sec
                           FROM slow_digest_daily WHERE qhash=%s AND cluster=%s ORDER BY log_date""", (qhash, cluster))


if __name__ == "__main__":
    server.run("stdio")
