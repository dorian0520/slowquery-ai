"""설정: ini 파일 + 비밀번호는 환경 변수(password_env 가 가리키는 이름)."""
import configparser
import os

NUM = {"min_sec": float, "min_q": int, "worse_ratio": float, "spike_ratio": float, "spike_min_total": float,
       "top_n": int, "port": int}


def load(path):
    cp = configparser.ConfigParser(inline_comment_prefixes=(";",))
    if not cp.read(path, encoding="utf-8"):
        raise FileNotFoundError(path)
    cfg = {}
    for sec in cp.sections():
        d = {k: NUM.get(k, str)(v) for k, v in cp[sec].items()}
        env = d.pop("password_env", None)
        if env:
            d["password"] = os.environ.get(env)   # 없으면 None — 접속할 때 명확히 실패한다
        cfg[sec] = d
    return cfg
