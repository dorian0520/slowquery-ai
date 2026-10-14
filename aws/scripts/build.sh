#!/usr/bin/env bash
# Lambda 패키지 + 레이어를 결정적으로 만든다 → aws/build/function.zip · aws/build/layer.zip
#   function.zip : aws/lambda/slowq_aws + skeleton/slowq + sql(01_shop.sql · 02_store.sql) + rds-ca.pem(받을 수 있으면)
#   layer.zip    : python/ 아래 pymysql · cryptography (Lambda python3.12 · arm64 용 휠)
# 사용: aws/scripts/build.sh            (SKIP_CA=1 이면 RDS CA 묶음을 받지 않음)
set -euo pipefail

AWS_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(dirname "$AWS_DIR")"
BUILD="$AWS_DIR/build"
PY="${PYTHON:-python3}"

rm -rf "$BUILD/function" "$BUILD/layer" "$BUILD/function.zip" "$BUILD/layer.zip"
mkdir -p "$BUILD/function/sql" "$BUILD/layer/python"

# 1) 함수 코드 — skeleton 의 순수 로직을 그대로 싣는다 (복사만, 수정 없음)
cp -R "$AWS_DIR/lambda/slowq_aws" "$BUILD/function/slowq_aws"
cp -R "$ROOT/skeleton/slowq" "$BUILD/function/slowq"
cp "$ROOT/lab/mysql/init/01_shop.sql" "$BUILD/function/sql/01_shop.sql"
cp "$AWS_DIR/sql/02_store.sql" "$BUILD/function/sql/02_store.sql"

# 2) RDS CA 묶음 (TLS 인증서 검증용). 일반 빌드는 받지 못하면 중단한다.
if [ "${SKIP_CA:-0}" != "1" ]; then
  if curl -fsSL --max-time 30 https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem -o "$BUILD/function/rds-ca.pem"; then
    echo "rds-ca.pem 포함"
  else
    rm -f "$BUILD/function/rds-ca.pem"
    echo "오류: RDS CA 묶음을 받지 못했습니다. 네트워크 확인 후 다시 빌드하세요." >&2
    exit 1
  fi
fi
if [ "${SKIP_CA:-0}" = "1" ]; then
  echo "오프라인 검사 전용: CA 없는 패키지는 DB 연결을 거부합니다." >&2
fi

# 3) 레이어 — 대상 플랫폼 휠만 (로컬 OS 와 무관하게 같은 결과)
"$PY" -m pip install --quiet --disable-pip-version-check --no-compile \
  --target "$BUILD/layer/python" \
  --platform manylinux2014_aarch64 --platform manylinux_2_28_aarch64 --platform manylinux_2_34_aarch64 \
  --implementation cp --python-version 3.12 --only-binary=:all: \
  -r "$AWS_DIR/lambda/requirements.txt"

rm -rf "$BUILD/layer/python/bin"   # pip 이 만든 실행 스크립트는 레이어에 필요 없다

# 4) 결정적 zip
"$PY" "$AWS_DIR/scripts/pack.py" "$BUILD/function" "$BUILD/function.zip"
"$PY" "$AWS_DIR/scripts/pack.py" "$BUILD/layer" "$BUILD/layer.zip"
shasum -a 256 "$BUILD/function.zip" "$BUILD/layer.zip" | sed "s#$BUILD/##"
