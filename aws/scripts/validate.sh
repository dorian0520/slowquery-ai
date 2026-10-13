#!/usr/bin/env bash
# 정적 검증 (AWS 자격 증명 · 배포 · Bedrock 호출 없음)
#   1) terraform fmt -check  2) terraform init -backend=false  3) terraform validate
#   4) py_compile  5) pytest aws/tests  6) ASL JSON · 구조 검사  7) 셸 문법  8) 금지 문자열 검사
# terraform init 은 프로바이더를 내려받으므로 네트워크가 필요하다. 받을 수 없으면 그 단계만 SKIP 으로 표시한다.
set -uo pipefail

AWS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(dirname "$AWS_DIR")"
PY="${PYTHON:-python3}"
TF="${TERRAFORM:-terraform}"
fail=0
results=()

step() {   # step <이름> <명령...>
  local name="$1"; shift
  echo "== $name"
  if "$@"; then results+=("PASS  $name"); else results+=("FAIL  $name"); fail=1; fi
}

# 비어 있는 aws 자격 증명으로 실행 — 실수로라도 AWS 를 부르지 않게
export AWS_ACCESS_KEY_ID= AWS_SECRET_ACCESS_KEY= AWS_SESSION_TOKEN= AWS_PROFILE=
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE

step "terraform fmt -check" "$TF" -chdir="$AWS_DIR/terraform" fmt -check -recursive

echo "== terraform init -backend=false"
if "$TF" -chdir="$AWS_DIR/terraform" init -backend=false -input=false -no-color >/tmp/slowq-tf-init.log 2>&1; then
  results+=("PASS  terraform init -backend=false")
  step "terraform validate" "$TF" -chdir="$AWS_DIR/terraform" validate -no-color
else
  tail -5 /tmp/slowq-tf-init.log
  results+=("SKIP  terraform init (프로바이더를 받지 못함 — 네트워크 확인)" "SKIP  terraform validate")
fi

pycompile() {
  find "$AWS_DIR/lambda" "$AWS_DIR/scripts" "$AWS_DIR/tests" -name '*.py' -not -path '*/__pycache__/*' -print0 \
    | xargs -0 "$PY" -m py_compile
}
step "py_compile" pycompile
step "pytest aws/tests" "$PY" -m pytest -q "$AWS_DIR/tests"
step "ASL JSON · 구조" "$PY" "$AWS_DIR/scripts/check_asl.py" "$AWS_DIR/statemachine/daily.asl.json" "$AWS_DIR/terraform/stepfunctions.tf"
step "대시보드 JSON" "$PY" -c "import json,sys; json.load(open(sys.argv[1], encoding='utf-8'))" "$ROOT/lab/grafana/dashboards/slowquery.json"
step "셸 문법" bash -c "bash -n '$AWS_DIR/scripts/build.sh' && bash -n '$AWS_DIR/scripts/validate.sh' && bash -n '$AWS_DIR/grafana/user_data.sh.tftpl'"

# 금지 문자열: 특정 조직 · 계정 · 개인 경로가 공개 저장소에 섞이지 않게 (이 파일 자신에 걸리지 않도록 조각으로 만든다)
forbidden="$(printf '%s|' 'mu''sinsa' '무신''사' '29''cm' 'oc''mp' 'm''ss' 'kr''eam' '7269''11960313' \
  'ar''n:aws:[a-z-]+:[a-z0-9-]*:[0-9]{12}' 'ora''cle' '오라''클' '/Us''ers/')"
forbidden="${forbidden%|}"
guard() {
  local hits
  hits="$(grep -rniEI --exclude-dir=.terraform --exclude-dir=build --exclude-dir=__pycache__ --exclude-dir=.pytest_cache \
          --exclude=.terraform.lock.hcl -e "$forbidden" "$AWS_DIR" || true)"
  if [ -n "$hits" ]; then echo "$hits"; return 1; fi
  echo "금지 문자열 0건"
}
step "금지 문자열 검사" guard

echo
printf '%s\n' "${results[@]}"
exit $fail
