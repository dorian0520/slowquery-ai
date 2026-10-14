"""정적 산출물: 상태 머신 정의 · 결정적 패키징 · 저장소 스키마와 대시보드의 열 호환."""
import importlib.util
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
AWS = os.path.dirname(HERE)
ROOT = os.path.dirname(AWS)


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(AWS, "scripts", f"{name}.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ASL = os.path.join(AWS, "statemachine", "daily.asl.json")
SFN_TF = os.path.join(AWS, "terraform", "stepfunctions.tf")


def test_asl_passes_static_check():
    assert load("check_asl").check(ASL, SFN_TF) == []


def test_asl_check_catches_missing_catch(tmp_path):
    asl = json.load(open(ASL, encoding="utf-8"))
    del asl["States"]["Detect"]["Catch"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(asl), encoding="utf-8")
    assert any("Detect: Catch 없음" in e for e in load("check_asl").check(str(bad), SFN_TF))


def test_asl_flow_order():
    s = json.load(open(ASL, encoding="utf-8"))["States"]
    order, cur = [], "Collect"
    while cur in s and s[cur]["Type"] not in ("Choice", "Succeed", "Fail"):
        order.append(cur)
        cur = s[cur]["Next"]
    assert order == ["Collect", "Detect", "IssueTickets", "Slim", "AnalyzeEach", "Track", "Publish"]
    inner = s["AnalyzeEach"]["ItemProcessor"]["States"]
    assert inner["Analyze"]["Next"] == "Verify" and inner["Verify"]["Next"] == "Attach"
    assert s["IsWeekly"]["Choices"][0]["Next"] == "Report"


def test_pack_is_deterministic(tmp_path):
    pack = load("pack").pack
    src = tmp_path / "src"
    (src / "pkg" / "__pycache__").mkdir(parents=True)
    (src / "pkg" / "a.py").write_text("x = 1\n")
    (src / "pkg" / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"junk")
    a, b = tmp_path / "a.zip", tmp_path / "b.zip"
    pack(str(src), str(a))
    os.utime(src / "pkg" / "a.py", (1, 1))                     # 시각이 달라도 결과는 같아야 한다
    pack(str(src), str(b))
    assert a.read_bytes() == b.read_bytes()
    import zipfile
    assert zipfile.ZipFile(a).namelist() == ["pkg/a.py"]


def test_store_schema_has_dashboard_columns():
    """대시보드(lab/grafana)가 읽는 열이 AWS 저장소 스키마에 모두 있다."""
    schema = open(os.path.join(AWS, "sql", "02_store.sql"), encoding="utf-8").read()
    dash = open(os.path.join(ROOT, "lab", "grafana", "dashboards", "slowquery.json"), encoding="utf-8").read()
    for col in ("max_sec", "updated_at", "realm", "tag", "owner_team", "after_avg_sec", "resolved_at"):
        assert col in dash and re.search(rf"\b{col}\b", schema), col


def test_store_schema_superset_of_skeleton():
    """skeleton 의 수집 · 발행 코드가 쓰는 열을 그대로 받는다 (skeleton/schema.sql 의 열 ⊆ AWS 스키마)."""
    def cols(path):
        out = {}
        for tbl, body in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", open(path, encoding="utf-8").read(), re.S):
            out[tbl] = {ln.split()[0] for ln in body.splitlines()
                        if ln.strip() and not ln.strip().startswith(("PRIMARY", "KEY", "UNIQUE", "--"))}
        return out
    sk, aws = cols(os.path.join(ROOT, "skeleton", "schema.sql")), cols(os.path.join(AWS, "sql", "02_store.sql"))
    for tbl, c in sk.items():
        assert c <= aws[tbl], (tbl, c - aws[tbl])


def test_asl_rejects_invalid_inner_start(tmp_path):
    asl=json.load(open(ASL,encoding='utf-8'))
    asl['States']['AnalyzeEach']['ItemProcessor']['StartAt']='Missing'
    bad=tmp_path/'bad.json';bad.write_text(json.dumps(asl))
    assert any('StartAt' in e for e in load('check_asl').check(str(bad),SFN_TF))


def test_asl_rejects_unsafe_map_concurrency(tmp_path):
    asl=json.load(open(ASL,encoding='utf-8'));asl['States']['AnalyzeEach']['MaxConcurrency']=0
    bad=tmp_path/'bad.json';bad.write_text(json.dumps(asl))
    assert any('MaxConcurrency' in e for e in load('check_asl').check(str(bad),SFN_TF))


def test_repo_checks_unpacked_source_without_git(tmp_path):
    (tmp_path/'demo.py').write_text('if broken syntax\n')
    (tmp_path/'data.json').write_text('{bad json')
    (tmp_path/'README.md').write_text('[missing](missing.txt) [external](https://example.com)')
    build=tmp_path/'build';build.mkdir();(build/'ignored.py').write_text('invalid!')
    counts,errors=load('check_repo').check(tmp_path)
    assert counts['python']==0 and counts['local_links']==1
    assert len(errors)==3 and any('missing.txt' in e for e in errors)
