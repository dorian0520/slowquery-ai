"""Grafana 대시보드 JSON 생성 (섹션 8). 실행하면 dashboards/slowquery.json 을 만든다."""
import json, os

DS = {"type": "mysql", "uid": "lab-dba"}
FILT = ("d.cluster IN (${cluster:sqlstring}) AND c.realm IN (${realm:sqlstring}) "
        "AND c.tag IN (${tag:sqlstring}) AND d.avg_sec >= ${min_sec} AND d.exec_cnt >= ${min_q}")


def q_var(name, label, sql, multi=True):
    return {"name": name, "label": label, "type": "query", "datasource": DS, "query": sql, "refresh": 1,
            "multi": multi, "includeAll": multi, "current": {"text": "All", "value": "$__all"} if multi else {}}


def custom(name, label, options, default):
    return {"name": name, "label": label, "type": "custom", "query": options,
            "current": {"text": default, "value": default}}


def panel(pid, title, ptype, sql, x, y, w, h, fmt="table", extra=None):
    p = {"id": pid, "title": title, "type": ptype, "datasource": DS,
         "gridPos": {"x": x, "y": y, "w": w, "h": h},
         "targets": [{"refId": "A", "datasource": DS, "rawQuery": True, "editorMode": "code",
                      "format": fmt, "rawSql": sql}]}
    p.update(extra or {})
    return p


BASE = f"FROM slow_digest_daily d JOIN cmdb_cluster c ON c.cluster = d.cluster WHERE {FILT}"
panels = [
    panel(1, "검출된 슬로우 쿼리", "stat", f"SELECT COUNT(*) AS cnt {BASE} AND d.log_date = '${{log_date}}'", 0, 0, 6, 4),
    panel(2, "총 부하 (초)", "stat", f"SELECT ROUND(SUM(d.total_sec)) AS sec {BASE} AND d.log_date = '${{log_date}}'", 6, 0, 6, 4),
    panel(3, "열린 티켓", "stat",
          "SELECT COUNT(*) FROM tuning_ticket WHERE status IN ('OPEN','IN_PROGRESS','REOPENED') AND cluster IN (${cluster:sqlstring})",
          12, 0, 6, 4),
    panel(4, "해결 확인된 티켓", "stat",
          "SELECT COUNT(*) FROM tuning_ticket WHERE status='RESOLVED' AND cluster IN (${cluster:sqlstring})", 18, 0, 6, 4),
    panel(5, "슬로우 쿼리 순위 (${log_date}, 정렬: ${sort})", "table",
          f"""SELECT d.cluster AS 클러스터, c.tag AS 업무, d.qhash AS qhash, d.exec_cnt AS 실행횟수,
                     ROUND(d.total_sec,1) AS 총부하초, ROUND(d.avg_sec,3) AS 평균초, ROUND(d.max_sec,3) AS 최대초,
                     d.rows_examined AS 읽은행수, IFNULL(t.status,'-') AS 티켓, c.owner_team AS 담당팀,
                     LEFT(d.query_text, 120) AS 쿼리
              {BASE.replace('WHERE', 'LEFT JOIN tuning_ticket t ON t.cluster=d.cluster AND t.qhash=d.qhash WHERE')}
                AND d.log_date = '${{log_date}}'
              ORDER BY ${{sort}} DESC LIMIT 50""", 0, 4, 24, 10),
    panel(6, "총 부하 상위 5개 쿼리 추이 (최근 ${days}일)", "timeseries",
          f"""SELECT UNIX_TIMESTAMP(d.log_date) AS time, CONCAT(d.cluster, ' ', LEFT(d.qhash, 8)) AS metric, d.total_sec AS value
              {BASE} AND d.log_date >= CURDATE() - INTERVAL ${{days}} DAY
                AND d.qhash IN (SELECT qhash FROM (SELECT qhash FROM slow_digest_daily
                  WHERE log_date >= CURDATE() - INTERVAL ${{days}} DAY GROUP BY qhash
                  ORDER BY SUM(total_sec) DESC LIMIT 5) x)
              ORDER BY 1""", 0, 14, 12, 9, fmt="time_series"),
    panel(7, "선택한 쿼리 평균 실행 시간 (${qhash})", "timeseries",
          """SELECT UNIX_TIMESTAMP(log_date) AS time, cluster AS metric, avg_sec AS value
             FROM slow_digest_daily WHERE qhash = '${qhash}'
               AND log_date >= CURDATE() - INTERVAL ${days} DAY ORDER BY 1""", 12, 14, 12, 9, fmt="time_series"),
    panel(8, "티켓 추적 — 개선 효과", "table",
          """SELECT t.ticket_id AS 번호, t.cluster AS 클러스터, t.qhash, t.status AS 상태, t.owner AS 담당자,
                    ROUND(t.baseline_avg_sec,3) AS 기준평균초,
                    (SELECT ROUND(d.avg_sec,4) FROM slow_digest_daily d WHERE d.cluster = t.cluster AND d.qhash = t.qhash
                       AND d.log_date = '${log_date}') AS 현재평균초,   -- 해결 당시 값이 아니라 선택한 일자 값
                    CASE WHEN t.status = 'RESOLVED' THEN ROUND(100*(1 - t.after_avg_sec / t.baseline_avg_sec)) END AS 개선율, DATE_FORMAT(t.created_at,'%m-%d') AS 발행, IFNULL(DATE_FORMAT(t.resolved_at,'%m-%d'),'-') AS 해결
             FROM tuning_ticket t WHERE t.cluster IN (${cluster:sqlstring}) ORDER BY t.updated_at DESC""",
          0, 23, 24, 9),
]

dash = {
    "uid": "lab-slowquery", "title": "슬로우 쿼리 운영 대시보드 (실습)", "timezone": "browser",
    "schemaVersion": 39, "time": {"from": "now-14d", "to": "now"}, "panels": panels,
    "templating": {"list": [
        q_var("realm", "환경", "SELECT DISTINCT realm FROM cmdb_cluster"),
        q_var("tag", "업무", "SELECT DISTINCT tag FROM cmdb_cluster WHERE realm IN (${realm:sqlstring})"),
        q_var("cluster", "클러스터", "SELECT cluster FROM cmdb_cluster WHERE realm IN (${realm:sqlstring}) AND tag IN (${tag:sqlstring})"),
        q_var("log_date", "일자", "SELECT DISTINCT DATE_FORMAT(log_date,'%Y-%m-%d') FROM slow_digest_daily ORDER BY 1 DESC", multi=False),
        custom("min_sec", "최소 평균(초)", "0,0.1,0.2,0.5,1", "0.2"),
        custom("min_q", "최소 횟수", "1,5,10,30", "5"),
        custom("sort", "정렬", "load : d.total_sec,count : d.exec_cnt,avg : d.avg_sec", "load"),
        custom("days", "기간(일)", "7,14,30", "14"),
        q_var("qhash", "쿼리", "SELECT qhash FROM slow_digest_daily WHERE log_date = '${log_date}' ORDER BY total_sec DESC LIMIT 20", multi=False),
    ]},
}

out = os.path.join(os.path.dirname(__file__), "dashboards", "slowquery.json")
json.dump(dash, open(out, "w"), ensure_ascii=False, indent=1)
print("written", os.path.relpath(out))   # 절대 경로(사용자 이름)를 화면에 남기지 않는다
