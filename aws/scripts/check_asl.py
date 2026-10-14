"""상태 머신 정의 정적 검사: JSON 형식 · 모든 Task 의 Retry/Catch · Map 동시성 · 다음 상태 존재 · 템플릿 변수 일치.

python3 check_asl.py <daily.asl.json> <stepfunctions.tf>
"""
import json
import re
import sys


def walk(states, path=""):
    for name, st in states.items():
        yield f"{path}{name}", st, states
        if st.get("Type") == "Map":
            yield from walk(st["ItemProcessor"]["States"], f"{path}{name}/")


def check(asl_path, tf_path):
    text = open(asl_path, encoding="utf-8").read()
    asl = json.loads(text)                                        # JSON 형식 오류면 여기서 실패
    errors = []
    if asl["StartAt"] not in asl["States"]:
        errors.append("StartAt 상태가 없습니다")
    for name, st, scope in walk(asl["States"]):
        t = st.get("Type")
        for key in ("Next", "Default"):
            if key in st and st[key] not in scope:
                errors.append(f"{name}: {key} → 없는 상태 {st[key]}")
        for c in st.get("Choices", []) + st.get("Catch", []):
            if c.get("Next") not in scope:
                errors.append(f"{name}: Choice/Catch → 없는 상태 {c.get('Next')}")
        if t == "Task":
            if not st.get("Retry"):
                errors.append(f"{name}: Retry 없음")
            if not st.get("Catch"):
                errors.append(f"{name}: Catch 없음")
        if t == "Map":
            if st.get("MaxConcurrency") != 1:
                errors.append(f"{name}: 공유 검증 DB의 MaxConcurrency 는 1이어야 합니다")
            child = st["ItemProcessor"]
            if child.get("StartAt") not in child["States"]:
                errors.append(f"{name}: ItemProcessor StartAt 상태가 없습니다")
        if t not in ("Choice", "Succeed", "Fail") and not st.get("End") and "Next" not in st:
            errors.append(f"{name}: Next/End 없음")
    used = set(re.findall(r"\$\{(\w+)\}", text))
    tf = open(tf_path, encoding="utf-8").read()
    block = tf[tf.index("templatefile("):]
    given = set(re.findall(r"^\s*(\w+)\s*=", block[: block.index("})")], re.M))
    if used - given:
        errors.append(f"templatefile 에 값이 없는 변수: {sorted(used - given)}")
    if given - used:
        errors.append(f"ASL 에서 쓰지 않는 변수: {sorted(given - used)}")
    return errors


if __name__ == "__main__":
    errs = check(sys.argv[1], sys.argv[2])
    for e in errs:
        print("ASL:", e)
    print("ASL OK" if not errs else f"ASL 오류 {len(errs)}건")
    sys.exit(1 if errs else 0)
