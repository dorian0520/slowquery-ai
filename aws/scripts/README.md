# aws/scripts — 빌드 · 정적 검증

Lambda 에 올릴 zip 을 만들고(`build.sh`), 배포 전에 AWS 를 부르지 않고 코드를 검사하는(`validate.sh`) 스크립트입니다. 빌드·정적 검사는 **AWS 계정 없이** 실행할 수 있습니다. `preflight.py`만 실제 자격 증명과 읽기·IAM 시뮬레이션 권한이 필요합니다.

## 파일

| 파일 | 역할 | 언제 쓰나 |
|---|---|---|
| `build.sh` | `aws/build/function.zip`(`lambda/slowq_aws` + `skeleton/slowq` + SQL 2개 + RDS CA 묶음) · `aws/build/layer.zip`(`pymysql` · `cryptography`, arm64 · Python 3.12 휠) 생성 | `terraform plan` 전에 항상 · 코드를 고친 뒤 |
| `validate.sh` | 정적 검증 8단계: `terraform fmt -check` · `init -backend=false` · `validate` · `py_compile` · `pytest` · ASL 검사 · 대시보드 JSON · 셸 문법 · 금지 문자열 | 배포 전 · 코드를 고친 뒤 |
| `preflight.py` | 예상 계정 및 이번 접두어의 RDS 두 대 삭제 권한 검사 (읽기 전용) | apply 전 |
| `check_repo.py` | 저장소 전체 Python/JSON/셸 문법·문서 로컬 파일 링크 검사 | validate.sh가 호출 |
| `pack.py` | 폴더를 결정적인 zip 으로 묶음 (같은 입력 → 같은 해시) | `build.sh` 가 부름 |
| `check_asl.py` | 상태 머신 정의 검사 (JSON 형식 · 모든 Task 의 Retry/Catch · Map 동시성 · 다음 상태 존재 · 템플릿 변수 일치) | `validate.sh` 가 부름 |

## 준비물

- Python 3.12 이상과 `pip` (`build.sh` 는 `PYTHON` 환경 변수로 다른 python 을 지정할 수 있음), `curl`, `shasum`
- 로컬 검증: Terraform 1.5 이상, `python3 -m pip install -r requirements-dev.txt`
- 인터넷 (휠 · RDS CA 묶음 · 프로바이더 내려받기)

## 따라 하기

모든 명령은 **`aws` 폴더**에서 칩니다.

1. **빌드**

   ```bash
   cd aws
   scripts/build.sh
   ```

   정상이면 이렇게 끝납니다 (해시 값은 내용에 따라 다름).

   ```
   rds-ca.pem 포함
   packed <개수> files -> function.zip
   packed <개수> files -> layer.zip
   <64자리 해시>  function.zip
   <64자리 해시>  layer.zip
   ```

   같은 코드 · 같은 CA 묶음으로 다시 빌드하면 해시가 같아야 합니다(결정적 빌드).

2. **정적 검증**

   ```bash
   scripts/validate.sh
   ```

   단계마다 `== 단계 이름` 이 지나가고, 끝에 결과 목록이 나옵니다.

   ```
   PASS  terraform fmt -check
   PASS  terraform init -backend=false
   PASS  terraform validate
   PASS  py_compile
   PASS  pytest aws/tests
   PASS  ASL JSON · 구조
   PASS  대시보드 JSON
   PASS  셸 문법
   PASS  금지 문자열 검사
   ```

   `FAIL` 이 하나라도 있으면 종료 코드 1 입니다. 그 단계의 출력(위쪽 `== …` 아래)을 보고 고칩니다.

3. 빌드 · 검증이 끝났으면 [terraform/README.md](../terraform/README.md) 로 넘어갑니다.

## 자주 막히는 곳

| 증상 | 원인 · 해결 |
|---|---|
| `오류: RDS CA 묶음을 받지 못했습니다` | 네트워크 확인 후 다시 빌드하세요. 정상 빌드는 중단되며 CA 없는 패키지는 DB 접속을 거부합니다 |
| pip 이 `No matching distribution found` | 대상 플랫폼(arm64 · Python 3.12) 휠을 못 찾음. `pip` 를 최신으로 올리고 인터넷 연결 확인 |
| `Permission denied` (`scripts/build.sh`) | 실행 권한이 없으면 `bash scripts/build.sh` 로 실행 |
| `SKIP  terraform init (프로바이더를 받지 못함 — 네트워크 확인)` | 프로바이더를 못 받았습니다. 네트워크 확인 후 다시 (이 경우 validate 도 SKIP) |
| `FAIL  terraform fmt -check` | `.tf` 형식이 어긋났습니다. `terraform -chdir=terraform fmt -recursive` 로 맞춥니다 |
| `FAIL  pytest aws/tests` | `pip install pytest` 했는지 확인. 실패한 테스트 이름은 위쪽 출력에 있습니다 ([tests/README.md](../tests/README.md)) |
| `FAIL  금지 문자열 검사` | 특정 조직 이름 · 계정 번호 · 실제 ARN · 개인 경로 같은 문자열이 `aws/` 안에 들어갔습니다. 출력된 줄을 지웁니다 |

## 다음 단계

- 배포: [terraform/README.md](../terraform/README.md)
- 테스트 상세: [tests/README.md](../tests/README.md)
- 전체 순서도: [docs/GETTING_STARTED.md](../../docs/GETTING_STARTED.md)

`SKIP_CA=1`은 오프라인 패키지 검사에만 사용합니다. CA가 없는 ZIP으로 배포해도 DB 연결은 거부됩니다. 테스트의 실제 네트워크 접근은 차단되어 있습니다. `SKIP terraform validate`를 포함한 결과는 Terraform 검증 완료가 아니므로 프로바이더 설치 문제를 해결한 뒤 다시 실행하세요.
