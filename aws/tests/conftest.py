"""테스트 공통: 네트워크 · AWS · DB 없이 핸들러를 돌린다."""
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [os.path.join(ROOT, "aws", "lambda"), os.path.join(ROOT, "skeleton")]

# 실수로 실제 AWS 를 부르지 않게 — 자격 증명을 비우고 엉뚱한 리전을 준다
for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE"):
    os.environ.pop(k, None)
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")


class FakeCursor:
    """실행한 SQL 을 기록하고, 정규식 → 결과 목록 규칙으로 fetch 값을 돌려준다. fail 규칙에 맞으면 예외."""

    def __init__(self, conn):
        self.conn, self._rows, self.lastrowid = conn, [], 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, args=None):
        self.conn.executed.append((sql, args))
        for pat, exc in self.conn.fail:
            if re.search(pat, sql, re.I | re.S):
                if callable(exc):
                    exc = exc()
                if exc is not None:
                    raise exc
        self._rows = []
        for pat, rows in self.conn.rules:
            if re.search(pat, sql, re.I | re.S):
                self._rows = rows(sql, args) if callable(rows) else list(rows)
                break
        self.lastrowid += 1
        return len(self._rows)

    def executemany(self, sql, seq):
        for a in seq:
            self.execute(sql, a)

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def mogrify(self, sql, args):
        return sql % tuple(repr(a) for a in args)


class FakeConn:
    def __init__(self, rules=(), fail=()):
        self.rules, self.fail, self.executed, self.closed = list(rules), list(fail), [], False

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True

    def sqls(self):
        return [s for s, _ in self.executed]


@pytest.fixture
def fake_conn():
    return FakeConn
