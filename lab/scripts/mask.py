"""섹션 4 · 19강: 분석 · AI 전달 전에 쿼리 원문의 값을 지운다.

python3 mask.py  # 실습 DB 최근 실행 이력에서 원문을 가져와 마스킹 전후를 보여 준다
"""
import re
from common import connect

PATTERNS = [
    (re.compile(r"'(?:[^'\\]|\\.)*'"), "'?'"),                     # 문자열 값 (이메일 · 이름 · 전화번호 포함)
    (re.compile(r'"(?:[^"\\]|\\.)*"'), '"?"'),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "?"),                       # 16진수
    (re.compile(r"(?<![\w.`])-?\d+(?:\.\d+)?(?![\w`])"), "?"),      # 숫자 (컬럼 이름 속 숫자는 그대로)
]


def mask(sql: str) -> str:
    for pat, rep in PATTERNS:
        sql = pat.sub(rep, sql)
    return sql


if __name__ == "__main__":
    with connect("shop-db", user="root", password="lab-root-pw") as c, c.cursor() as cur:
        cur.execute("""SELECT SQL_TEXT FROM performance_schema.events_statements_history_long
                       WHERE CURRENT_SCHEMA = 'shop' AND SQL_TEXT REGEXP 'email LIKE|user_id = [0-9]|coupon_code ='
                       ORDER BY EVENT_ID DESC LIMIT 3""")
        for r in cur.fetchall():
            print("원문 :", r["SQL_TEXT"])
            print("마스킹:", mask(r["SQL_TEXT"]))
            print()
