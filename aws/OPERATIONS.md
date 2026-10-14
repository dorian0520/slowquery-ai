# 설치부터 결과 확인·정리까지

저장소 루트에서 시작합니다. `lab/`은 로컬 사례, `skeleton/`은 확장용 코드, 이 문서의 명령은 새로운 AWS 실습 스택용입니다. 기존 운영 DB에 연결하는 설정은 포함하지 않습니다.

## 1. 소스와 도구 준비

```bash
git clone https://github.com/dorian0520/slowquery-ai.git
cd slowquery-ai
python3 --version                 # 3.12 이상 확인
python3 -m venv .venv
.venv/bin/python -m pip install -r aws/requirements-dev.txt
export PYTHON="$PWD/.venv/bin/python"
terraform version                # OS/CPU에 맞는 바이너리
aws --version                    # CLI v2
```

원격 저장소에서 받은 버전은 그 커밋의 검증 기록을 확인하세요. [소스 검토 기록](SOURCE_REVIEW.md)은 이 수정본에 대한 기록이며 GitHub 반영 여부를 대신 확인해 주지는 않습니다.

## 2. 배포 없이 검사

```bash
bash aws/scripts/build.sh
bash aws/scripts/validate.sh
```

모든 단계가 PASS인지 확인합니다. Terraform 프로바이더 설치가 실패한 SKIP은 검증 완료가 아닙니다. 단위 테스트는 실제 네트워크 접속을 차단하며 DB·Bedrock·Jira·Slack 대역을 사용합니다. `check_repo.py`는 저장소 전체 문법·로컬 문서 링크를 검사하지만 SQL 실행이나 외부 링크의 유효성을 보장하지 않습니다.

## 3. 계정·삭제 권한 확인

```bash
export AWS_PROFILE='<승인된 프로필>'
export AWS_REGION='ap-northeast-2'
export SLOWQ_PREFIX='<고유한 소문자 접두어>'
export SLOWQ_ACCOUNT_ID='<12자리 계정 ID>'
aws sts get-caller-identity --query Account --output text
.venv/bin/python aws/scripts/preflight.py \
  --profile "$AWS_PROFILE" --region "$AWS_REGION" \
  --expected-account "$SLOWQ_ACCOUNT_ID" --prefix "$SLOWQ_PREFIX"
```

계정이 맞고 두 DB 삭제 결과가 allowed이며 누락 컨텍스트가 없어야 다음 단계로 진행합니다. 이 도구는 IAM 시뮬레이션이며 SCP·리소스 조건·실제 서비스 동작을 보장하지 않습니다. 생성만 허용되고 삭제는 explicitDeny인 역할도 있으므로 승인된 삭제 경로를 미리 마련합니다. 점검 역할에 IAM GetRole/SimulatePrincipalPolicy 권한이 없으면 담당자가 승인된 방식으로 확인합니다.

## 4. 생성과 초기화

```bash
cd aws/terraform
cp example.tfvars terraform.tfvars
# name_prefix·expected_account_id를 위 점검 값으로 맞춘다.
# schedule_enabled=false·enable_workload=false·publish_dry_run=true로 시작한다.
terraform init
terraform plan -out tfplan
terraform apply tfplan
terraform output -raw next_steps
```

계획의 대상 계정·새 자원·변경·삭제를 확인합니다. 출력된 실제 함수 이름과 ARN을 사용하세요. 문서의 `slowq-*`는 기본 접두어 예시입니다. 계획·상태·개인 변수 파일에는 비밀값이 들어갈 수 있으므로 Git에 넣지 않습니다.

`init-db` 결과는 `StatusCode: 200`뿐 아니라 **FunctionError 없음**과 target/verify 둘 다 완료를 확인합니다. verify 시간 부족이면 `{"only":"verify"}`로 나누어 실행합니다. `reset_shop=true`는 부분 생성된 합성 샘플 스키마를 삭제·재생성하므로 상태를 확인한 뒤 명시적으로 사용합니다. `only` 오타나 `reset_shop:"false"` 문자열은 거부합니다.

## 5. 파이프라인 확인

1. 기준 상태 머신 실행 → 완료를 기다립니다. 첫 수집 0건은 정상입니다.
2. workload를 한 번 실행하고 완료를 기다립니다.
3. 날짜를 지정해 다시 실행합니다. `log_date`는 스냅숏 간 차이를 저장할 날짜이며 과거 실제 쿼리를 복원하는 기능이 아닙니다.
4. `describe-execution`의 SUCCEEDED와 각 단계 결과를 함께 확인합니다. SUCCEEDED여도 개별 티켓은 FORMAT_ERROR·SKIPPED·사람 검토 상태일 수 있습니다.
5. Grafana TLS 연결·대시보드, S3 리포트와 계획서, 중복 발행 여부, 검증 DB의 임시 인덱스 제거를 확인합니다.

실행을 겹쳐 시작하지 않습니다. Map과 검증 Lambda는 직렬화하지만 수집부터 티켓 기록까지 전체 파이프라인의 분산 잠금은 없습니다. 오래된 날짜를 지정해 현재 티켓 상태를 소급 갱신하는 운영은 지원하지 않습니다. 과거 리포트는 report Lambda만 따로 호출합니다.

```bash
aws stepfunctions describe-execution --execution-arn '<실행 ARN>' \
  --query '{status:status,error:error,cause:cause}'
aws logs tail "/aws/lambda/$SLOWQ_PREFIX-analyze" --since 1h
aws s3 ls "s3://$(terraform output -raw artifacts_bucket)/reports/" --recursive
```

[Lambda별 입력·오류](lambda/README.md), [상태 머신 분기](statemachine/README.md), [Grafana 확인](grafana/README.md)을 참고하세요.

## 6. 수정 후 재검증

로직 변경 → 단위 검사 → build → 정적 검사 → Terraform plan 확인 → 승인된 실습 계정 apply → 합성 시나리오 순서로 진행합니다. `apply-plan`은 verified ADD INDEX의 문서를 만들 뿐 운영 DDL을 실행하지 않습니다. Jira·Slack 실제 전송은 별도 자격 증명·NAT·명시적인 발행 설정이 필요하며 이 검증에서는 수행하지 않았습니다.

- report 재생성은 보관된 날짜 범위 데이터를 읽습니다. 삭제된 데이터를 복원하지 않습니다.
- 되돌리기 경고가 있는 제안은 자동 승인 후보에서 제외됩니다. Lambda 강제 종료·DB 단절 때의 최종 인덱스 상태는 사람 확인이 필요합니다.
- 외부 API 성공과 DB 이벤트 저장은 원자적이지 않습니다. 발행이 모호하게 실패한 경우 원격 이슈·메시지를 확인한 뒤 재시도합니다.
- Secret 캐시는 실행 컨테이너 동안 유지됩니다. 비밀번호 회전·장기 실행·대량 CMDB·장기 데이터 보관을 운영에 적용하기 전 별도 검증합니다.

## 7. 제거와 잔존 확인

```bash
terraform plan -destroy -out destroy.tfplan
terraform apply destroy.tfplan
terraform state list
aws rds describe-db-instances --query 'DBInstances[].DBInstanceIdentifier'
aws lambda list-functions --query 'Functions[].FunctionName'
```

필요한 결과를 먼저 보관하고, 계획에는 이 스택 자원만 있는지 확인합니다. 위 읽기 명령에서 **자신의 고유 접두어**만 확인합니다. 오류로 끝났다면 상태를 보존하고 실패한 자원만 승인된 권한으로 정리합니다. RDS 삭제는 최종 스냅숏 없이 진행하도록 설계되어 있습니다.

Terraform state가 비었는지와 서비스 잔존을 모두 확인합니다. RDS가 자동으로 만든 slowquery 로그 그룹, 자동 백업·스냅숏, RDS 관리 비밀값, Lambda ENI, VPC·보안 그룹·서브넷·엔드포인트, EBS, S3, IAM, 스케줄·SNS가 점검 대상입니다. 다른 이름·태그의 자원을 일괄 삭제하지 않습니다. ENI 정리가 끝나기 전에 실행 역할을 제거하지 않도록 삭제 의존성을 보완했습니다. 역할 삭제가 먼저 일어난 경우 [AWS ENI 안내](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html)를 따릅니다.

현재 검증 스택의 RDS 삭제 권한 예외는 대기 중입니다. 이 문서의 절차가 제거 완료 증거는 아닙니다. [실행 기록](LIVE_VALIDATION.md)을 확인하세요.
