"""AI 가 넘긴 SQL 을 실행하기 전에 거르는 규칙. AI 출력은 신뢰하지 않는다."""
import re

from slowq.mask import PATTERNS

FORBIDDEN = re.compile(
    r"(?i)\b(into\s+(outfile|dumpfile|@)|for\s+update|for\s+share|lock\s+in\s+share\s+mode|sleep\s*\(|benchmark\s*\(|"
    r"get_lock\s*\(|load_file\s*\(|release_lock\s*\()")   # SELECT 로 시작하는 한 문장 안에서 부작용을 내는 것들
TABLE_NAME = re.compile(r"[A-Za-z0-9_]{1,64}")
DDL_IN_PROPOSAL = re.compile(r"ALTER\s+TABLE[^;]+", re.I)


class UnsafeSQL(ValueError):
    """허용하지 않는 SQL — 실행하지 않는다."""


def select_only(sql):
    """SELECT 한 문장만 통과. 주석 · 세미콜론 · 잠금 · 파일 출력 · 쓰기 키워드가 있으면 거부한다."""
    if not isinstance(sql, str) or not sql.strip():
        raise UnsafeSQL("SQL 이 비어 있습니다")
    s = sql.strip().rstrip(";").strip()
    bare = _strip_strings(s)                         # 문자열 값 안의 ; · -- · 단어는 구문으로 보지 않는다
    if ";" in bare:
        raise UnsafeSQL("한 문장만 허용합니다")
    if "--" in bare or "/*" in bare or "#" in bare:
        raise UnsafeSQL("주석은 허용하지 않습니다")
    if not re.match(r"(?is)^select\b", bare):
        raise UnsafeSQL("SELECT 문만 허용합니다")
    m = FORBIDDEN.search(bare)
    if m:
        raise UnsafeSQL(f"허용하지 않는 구문: {m.group(0)}")
    return s


def _strip_strings(s):
    """문자열 값 안의 단어(예: 'update')는 키워드로 보지 않는다."""
    return PATTERNS[1][0].sub('""', PATTERNS[0][0].sub("''", s))


def mask_plan(plan):
    """실행 계획에서는 문자열 값만 지운다 — 숫자(rows · cost)는 근거라 남긴다."""
    return PATTERNS[0][0].sub(PATTERNS[0][1], plan or "")


def table_name(name):
    if not isinstance(name, str) or not TABLE_NAME.fullmatch(name):
        raise UnsafeSQL("테이블 이름 형식이 아닙니다")
    return name


def first_ddl(proposal):
    """제안 문장에서 첫 ALTER TABLE 한 문장. 실제 실행 가능 여부는 slowq.verify.index_target 이 다시 판정한다."""
    m = DDL_IN_PROPOSAL.search(proposal or "")
    return m.group(0).strip() if m else None
