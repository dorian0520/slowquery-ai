"""Lambda 공통: 환경 변수 · 비밀 값 조회 · DB 연결 · 로그.

- 비밀번호는 환경 변수에 두지 않는다. 환경 변수에는 Secrets Manager 비밀의 ARN 만 있고, 값은 실행 중에 읽는다.
- 비밀 값은 컨테이너 안에서만 캐시하고 로그에 남기지 않는다.
- DB 연결은 TLS 를 켠다. 패키지에 RDS CA 묶음(rds-ca.pem)이 있으면 인증서까지 검증한다.
"""
import datetime as dt
import json
import logging
import os
import zoneinfo

import pymysql

log = logging.getLogger("slowq")
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

HERE = os.path.dirname(os.path.abspath(__file__))
CA_BUNDLE = os.path.join(os.path.dirname(HERE), "rds-ca.pem")

_secret_cache = {}
_sm_client = None


def env(name, default=None, required=False):
    v = os.environ.get(name, default)
    if required and not v:
        raise RuntimeError(f"환경 변수 {name} 가 없습니다")
    return v


def secrets_client():
    global _sm_client
    if _sm_client is None:
        import boto3  # Lambda 런타임에 포함 — 테스트에서는 이 함수를 바꿔 끼운다
        _sm_client = boto3.client("secretsmanager")
    return _sm_client


def get_secret(arn):
    """JSON 비밀을 dict 로. 값은 반환만 하고 어디에도 출력하지 않는다."""
    if not arn:
        return {}
    if arn not in _secret_cache:
        raw = secrets_client().get_secret_value(SecretId=arn)["SecretString"]
        _secret_cache[arn] = json.loads(raw)
    return _secret_cache[arn]


def ssl_options():
    if os.path.exists(CA_BUNDLE):
        return {"ca": CA_BUNDLE}                  # 인증서 + 호스트 이름 검증
    return {"verify_mode": False}                 # 묶음이 없으면 암호화만 (README 의 제한 사항 참고)


def connect(host, secret_arn, database=None, port=None, autocommit=True, connect_timeout=10, read_timeout=600):
    s = get_secret(secret_arn)
    if not s.get("username") or not s.get("password"):
        raise RuntimeError("비밀에 username/password 가 없습니다 (init_db 를 먼저 실행했는지 확인)")
    return pymysql.connect(host=host, port=int(port or env("DB_PORT", "3306")), user=s["username"], password=s["password"],
                           database=database, charset="utf8mb4", autocommit=autocommit,
                           connect_timeout=connect_timeout, read_timeout=read_timeout, write_timeout=read_timeout,
                           ssl=ssl_options(), cursorclass=pymysql.cursors.DictCursor)


def store_conn():
    """저장소(dba) — 대상 DB 에 있다."""
    return connect(env("TARGET_HOST", required=True), env("STORE_SECRET_ARN", required=True), env("STORE_DB", "dba"))


def rules():
    return {"min_sec": float(env("RULE_MIN_SEC", "0.5")), "min_q": int(env("RULE_MIN_Q", "30")),
            "worse_ratio": float(env("RULE_WORSE_RATIO", "2.0")), "spike_ratio": float(env("RULE_SPIKE_RATIO", "2.0")),
            "spike_min_total": float(env("RULE_SPIKE_MIN_TOTAL", "1.0")), "top_n": int(env("RULE_TOP_N", "10"))}


def today_local():
    return dt.datetime.now(zoneinfo.ZoneInfo(env("TZ_NAME", "Asia/Seoul"))).date()


def resolve_log_date(event):
    """입력에 log_date 가 있으면 그 날, 없으면 '어제'(스케줄은 자정 직후에 돈다)."""
    v = (event or {}).get("log_date")
    if v:
        return dt.date.fromisoformat(v).isoformat()   # 형식이 틀리면 여기서 실패한다
    return (today_local() - dt.timedelta(days=1)).isoformat()


def jsonable(obj):
    """Step Functions 로 넘길 수 있게 Decimal · datetime 을 바꾼다."""
    return json.loads(json.dumps(obj, default=_default, ensure_ascii=False))


def _default(o):
    if isinstance(o, (dt.date, dt.datetime)):
        return o.isoformat()
    try:
        return float(o)
    except (TypeError, ValueError):
        return str(o)
