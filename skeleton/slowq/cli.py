"""python -m slowq --config config.ini daily --date 2026-10-12

daily = CMDB 의 수집 대상 전체 수집 → 검출 → 티켓 발행(dry-run 알림) → 해결 · 재발 추적. 스케줄러(cron 등)로 하루 한 번.
"""
import argparse
import datetime as dt
import sys

from . import collect, detect, tickets
from .config import load
from .db import connect
from .publish import DryRunPublisher


def targets(store):
    with store.cursor() as cur:
        cur.execute("SELECT cluster, host, port FROM cmdb_cluster WHERE collect = 1 ORDER BY cluster")
        return cur.fetchall()


def daily(cfg, log_date, out=sys.stdout):
    store = connect(cfg["store"])
    try:
        failed = []
        for t in targets(store):
            try:                   # 한 클러스터의 실패가 나머지 수집을 막지 않게 — 실패는 기록하고 끝에 알린다
                conn = connect(dict(cfg["target"], host=t["host"], port=t["port"], database=None))
                try:
                    n = collect.collect(store, conn, t["cluster"], log_date, exclude_schema=cfg["store"].get("database", ""))
                finally:
                    conn.close()
                out.write(f"수집 {t['cluster']}: {n}개 지문\n")
            except Exception as e:  # noqa: BLE001 — 클러스터 단위 격리, 아래에서 실패로 보고
                failed.append(t["cluster"])
                out.write(f"수집 실패 {t['cluster']}: {e}\n")
        hits = detect.run(store, log_date, cfg["rules"])
        out.write(f"검출 {len(hits)}건\n")
        made = tickets.issue(store, log_date, hits, cfg["rules"].get("top_n", 10))
        pub = DryRunPublisher(out)
        for m in made:
            pub.publish(m)
        changed = tickets.track(store, log_date)
        out.write(f"신규 티켓 {len(made)}건 · 상태 변경 {len(changed)}건\n")
        if failed:
            out.write(f"수집 실패 클러스터 {len(failed)}개: {', '.join(failed)}\n")
        return {"hits": hits, "made": made, "changed": changed, "failed": failed}
    finally:
        store.close()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="slowq")
    ap.add_argument("--config", default="config.ini")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("daily"); d.add_argument("--date", default=dt.date.today().isoformat())
    sub.add_parser("init-schema")
    a = ap.parse_args(argv)
    cfg = load(a.config)
    if a.cmd == "init-schema":
        import os
        from .db import apply_schema
        with connect(cfg["store"]) as c:
            apply_schema(c, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schema.sql"))
        print("스키마 적용 완료")
        return None
    r = daily(cfg, a.date)
    if r["failed"]:
        sys.exit(1)        # 스케줄러가 실패를 알아차리도록
    return r
