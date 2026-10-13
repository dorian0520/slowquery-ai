"""14일치 운영 상황을 빠르게 재현한다 (대시보드·추적 실습용).

- 1~7일차: 평소 부하
- 8일차: 쿠폰 쿼리 급증(행사 상황)
- 9일차: user_recent_orders 인덱스 추가 → 개선 확인
- 12일차: 인덱스 실수로 삭제 → 재발 검출
"""
import argparse
import datetime as dt
import collector, tickets, workload
from common import connect

FIX = "ALTER TABLE orders ADD INDEX ix_user_ordered (user_id, ordered_at)"
UNFIX = "ALTER TABLE orders DROP INDEX ix_user_ordered"


def ddl(sql):
    with connect("shop-db", user="root", password="lab-root-pw", db="shop") as c, c.cursor() as cur:
        cur.execute(sql)


def main(days=14):
    start = dt.date.today() - dt.timedelta(days=days - 1)
    collector.main((start - dt.timedelta(days=1)).isoformat())  # 기준 스냅숏
    for i in range(days):
        d = (start + dt.timedelta(days=i)).isoformat()
        if i == 8:
            ddl(FIX); print("== 인덱스 추가")
        if i == 11:
            ddl(UNFIX); print("== 인덱스 삭제(재발 상황)")
        workload.run("shop-db", 1.0 + 0.1 * (i % 3))
        if i == 7:
            workload.run("shop-db", 3.0, only=["coupon_usage"])
        workload.run("order-db", 0.5)
        collector.main(d)
        tickets.issue(d)
        tickets.track(d)
    # 강의 화면의 날짜는 촬영일 기준이다. 내 환경의 날짜로 바꿔 입력한다.
    lecture = dt.date(2026, 9, 29)
    print("\n강의 날짜 → 내 날짜")
    for i, label in [(0, "1일차 · 첫 티켓 발행"), (7, "8일차 · 쿠폰 급증"), (8, "9일차 · 인덱스 추가(해결)"),
                     (11, "12일차 · 인덱스 삭제(재발)"), (days - 1, f"{days}일차 · 마지막 날"), (days, "다음 날 · 37~39강 사례 실습")]:
        print(f"  {lecture + dt.timedelta(days=i)} → {start + dt.timedelta(days=i)}  ({label})")


if __name__ == "__main__":
    argparse.ArgumentParser(description="14일치 운영 상황을 재현한다 (실습 DB 에 씁니다)").parse_args()   # --help 는 도움말만
    main()
