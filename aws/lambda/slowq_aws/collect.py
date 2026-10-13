"""Collect 단계: CMDB(cmdb_cluster) 의 수집 대상마다 performance_schema digest 를 읽어 하루치 차이를 저장한다.

입력: {"log_date": "YYYY-MM-DD"} (없으면 어제). 출력: {"log_date", "weekly", "collected": {...}, "failed": [...]}
한 클러스터의 실패가 나머지 수집을 막지 않는다. 모두 실패하면 예외로 알린다(Step Functions Catch → SNS).
"""
import datetime as dt

from slowq import collect as scollect

from . import common


def targets(store):
    with store.cursor() as cur:
        cur.execute("SELECT cluster, host, port FROM cmdb_cluster WHERE collect = 1 ORDER BY cluster")
        return cur.fetchall()


def is_weekly(log_date, weekday):
    """주간 리포트를 낼 날인지 (weekday: 0=월 ... 6=일, log_date 기준)."""
    return dt.date.fromisoformat(log_date).weekday() == int(weekday)


def run(store, connect_target, log_date, store_db="dba"):
    collected, failed = {}, []
    for t in targets(store):
        try:
            conn = connect_target(t["host"], t["port"])
            try:
                collected[t["cluster"]] = scollect.collect(store, conn, t["cluster"], log_date, exclude_schema=store_db)
            finally:
                conn.close()
        except Exception:  # noqa: BLE001 — 클러스터 단위 격리. 실패는 기록하고 결과로 알린다
            common.log.exception("수집 실패 cluster=%s", t["cluster"])
            failed.append(t["cluster"])
    return collected, failed


def handler(event, context):
    log_date = common.resolve_log_date(event)
    secret = common.env("COLLECTOR_SECRET_ARN", required=True)
    store = common.store_conn()
    try:
        collected, failed = run(store, lambda h, p: common.connect(h, secret, None, port=p), log_date,
                                common.env("STORE_DB", "dba"))
    finally:
        store.close()
    if failed and not collected:
        raise RuntimeError(f"모든 클러스터 수집 실패: {failed}")
    return {"log_date": log_date, "weekly": is_weekly(log_date, common.env("REPORT_WEEKDAY", "6")),
            "collected": collected, "failed": failed}
