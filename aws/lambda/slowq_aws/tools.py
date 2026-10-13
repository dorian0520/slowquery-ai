"""AI 근거 도구 4가지 (lab/ai/labdb_mcp.py 의 MCP 도구를 Lambda 안의 함수로 옮김).

AI 가 할 수 있는 일은 이 네 가지뿐이고, 모두 읽기 전용 계정(slowq_ai)으로 실행한다.
- top_queries : 일자별 슬로우 쿼리 상위 목록 (저장소)
- table_info  : 테이블 구조 · 인덱스 · 대략적 행 수 (서비스 스키마)
- explain     : SELECT 한 문장의 실행 계획 (EXPLAIN FORMAT=TREE — 쿼리를 실행하지 않음, 문자열 값은 마스킹)
- query_trend : 쿼리 지문 하나의 일자별 추이
"""
from . import guards

SPECS = [
    {"name": "top_queries", "description": "일자별 슬로우 쿼리 상위 목록(총 부하 순). log_date 형식 YYYY-MM-DD",
     "inputSchema": {"json": {"type": "object", "properties": {
         "log_date": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 20}},
         "required": ["log_date"]}}},
    {"name": "table_info", "description": "테이블 구조(SHOW CREATE TABLE), 인덱스 목록, 대략적 행 수",
     "inputSchema": {"json": {"type": "object", "properties": {"table": {"type": "string"}}, "required": ["table"]}}},
    {"name": "explain", "description": "SELECT 문 한 개의 실행 계획(EXPLAIN FORMAT=TREE). 쿼리를 실행하지 않는다. 값 자리(?)에는 테스트 값을 넣을 것",
     "inputSchema": {"json": {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]}}},
    {"name": "query_trend", "description": "쿼리 지문(qhash) 하나의 일자별 실행 횟수 · 평균 시간 추이",
     "inputSchema": {"json": {"type": "object", "properties": {"qhash": {"type": "string"}}, "required": ["qhash"]}}},
]


class Tools:
    """store: 저장소 연결(dba), shop: 서비스 스키마 연결 — 둘 다 읽기 전용 계정. cluster 는 분석 중인 티켓의 클러스터로 고정."""

    def __init__(self, store, shop, cluster, shop_db="shop"):
        self.store, self.shop, self.cluster, self.shop_db = store, shop, cluster, shop_db

    def _q(self, conn, sql, args=None):
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall()

    def top_queries(self, log_date, limit=10):
        return self._q(self.store, """SELECT cluster, qhash, query_text, exec_cnt, ROUND(avg_sec,4) avg_sec,
                                             ROUND(total_sec,2) total_sec, rows_examined
                                      FROM slow_digest_daily WHERE log_date=%s AND cluster=%s
                                      ORDER BY total_sec DESC LIMIT %s""",
                       (str(log_date), self.cluster, max(1, min(int(limit), 20))))

    def table_info(self, table):
        t = guards.table_name(table)
        ddl = self._q(self.shop, f"SHOW CREATE TABLE `{t}`")[0]["Create Table"]
        idx = self._q(self.shop, f"SHOW INDEX FROM `{t}`")
        rows = self._q(self.shop, "SELECT TABLE_ROWS FROM information_schema.tables WHERE table_schema=%s AND table_name=%s",
                       (self.shop_db, t))
        return {"ddl": ddl,
                "indexes": [{k: i[k] for k in ("Key_name", "Seq_in_index", "Column_name", "Cardinality")} for i in idx],
                "approx_rows": rows[0]["TABLE_ROWS"] if rows else None}

    def explain(self, sql):
        s = guards.select_only(sql)
        plan = self._q(self.shop, "EXPLAIN FORMAT=TREE " + s)[0]["EXPLAIN"]
        return guards.mask_plan(plan)

    def query_trend(self, qhash):
        return self._q(self.store, """SELECT log_date, exec_cnt, ROUND(avg_sec,4) avg_sec, ROUND(total_sec,2) total_sec
                                      FROM slow_digest_daily WHERE qhash=%s AND cluster=%s ORDER BY log_date""",
                       (str(qhash), self.cluster))

    def call(self, name, args):
        """도구 이름은 목록에 있는 것만. 실패는 예외 대신 오류 메시지로 돌려 AI 가 다른 근거를 찾게 한다."""
        fn = {"top_queries": self.top_queries, "table_info": self.table_info,
              "explain": self.explain, "query_trend": self.query_trend}.get(name)
        if fn is None:
            return {"error": f"알 수 없는 도구: {name}"}, True
        try:
            return fn(**(args or {})), False
        except guards.UnsafeSQL as e:
            return {"error": f"거부: {e}"}, True
        except TypeError as e:
            return {"error": f"인자 오류: {e}"}, True
        except Exception as e:  # noqa: BLE001 — DB 오류 문구만 AI 에 돌려준다 (접속 정보는 포함되지 않음)
            return {"error": f"{type(e).__name__}: {str(e)[:200]}"}, True
