"""발행 어댑터. 기본은 dry-run(보내지 않고 기록) — Jira · Slack 어댑터는 같은 publish(ticket) 형태로 추가한다."""
import json


class DryRunPublisher:
    def __init__(self, out=None):
        self.sent, self.out = [], out

    def publish(self, ticket):
        self.sent.append(ticket)
        if self.out:
            self.out.write("# dry-run (보내지 않음) " + json.dumps(ticket, ensure_ascii=False) + "\n")
