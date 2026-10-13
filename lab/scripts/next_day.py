"""섹션 9: 하루를 진행한다 — 그날의 부하 → 수집 → 발행 → 추적 (simulate.py 의 하루와 같은 순서).

python3 next_day.py --log-date 2026-10-13
"""
import argparse
import collector, tickets, workload

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--log-date", required=True)
    d = p.parse_args().log_date
    workload.run("shop-db", 1.0)
    workload.run("order-db", 0.5)
    collector.main(d)
    tickets.issue(d)
    tickets.track(d)
