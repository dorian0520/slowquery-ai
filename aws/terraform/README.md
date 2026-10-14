# aws/terraform — AWS 리소스 만들기 · 지우기

`terraform apply` 한 번으로 VPC · RDS MySQL 두 대 · Lambda 12개 · Step Functions · EventBridge 스케줄 · Grafana EC2 · S3 · SNS 를 만드는 코드입니다. **apply 하는 순간부터 비용이 발생**하니(하루 약 $3, [aws/README.md](../README.md) 2장) 다 보면 꼭 `destroy` 합니다.

## 파일

| 파일 | 역할 | 언제 보나 |
|---|---|---|
| `versions.tf` · `providers.tf` | Terraform ≥ 1.5 · AWS 프로바이더 · (주석) 원격 상태 백엔드 예 | 상태 파일을 S3 에 두고 싶을 때 |
| `variables.tf` | 입력 변수 전체와 기본값 (리전 · 모델 ID · 스케줄 · 규칙 · 발행 설정 …) | 무엇을 바꿀 수 있는지 볼 때 |
| `example.tfvars` | 자주 바꾸는 값만 모은 예시. `terraform.tfvars` 로 복사해 씀 | **처음 한 번** |
| `network.tf` | VPC · 서브넷 · 보안 그룹 · VPC 엔드포인트 · (선택) NAT | 네트워크 구조 확인 |
| `rds.tf` | RDS MySQL 8.0 × 2 (대상 `shop-db` · 검증 `order-db`) · 파라미터 그룹 | DB 사양 · 설정 |
| `secrets.tf` | DB 계정 · Grafana 관리자 · 발행 자격 증명 비밀 | 비밀 이름 확인 |
| `iam.tf` | Lambda 함수별 · Step Functions · Scheduler 역할 (최소 권한) | 권한 오류 때 |
| `lambda.tf` | Lambda 12개 + 레이어 (`../build/function.zip` · `../build/layer.zip` 을 올림) | 함수 설정 · 제한 시간 |
| `stepfunctions.tf` | 상태 머신 `slowq-daily` (`../statemachine/daily.asl.json` 을 채움) | 배치 흐름 |
| `schedule.tf` | 매일 실행(기본 꺼짐) · 부하 발생(선택) 스케줄 | 자동 실행을 켤 때 |
| `grafana.tf` | Grafana EC2 · 대시보드 JSON 업로드 (`lab/grafana/dashboards/slowquery.json` 재사용) | 대시보드 접속 |
| `monitoring.tf` | 실패 알림 SNS · CloudWatch 경보 | 알림 메일 설정 |
| `main.tf` | 리포트 · 계획서용 S3 버킷 | 결과 파일 위치 |
| `outputs.tf` | apply 뒤 출력값 (`state_machine_arn` · `artifacts_bucket` · `grafana_instance_id` · `next_steps` …) | apply 직후 |
| `.terraform.lock.hcl` | 프로바이더 버전 고정 | 손대지 않음 |

## 준비물

- Terraform 1.5 이상, AWS CLI v2, 배포할 AWS 계정의 자격 증명 (`aws sts get-caller-identity` 로 계정이 맞는지 먼저 확인)
- Bedrock 에서 Anthropic 모델 사용 권한 (처음이면 콘솔에서 사용 사례 제출이 필요할 수 있음)
- **먼저 빌드**: `aws` 폴더에서 `scripts/build.sh` 를 실행해 `aws/build/function.zip` · `layer.zip` 이 있어야 합니다 ([scripts/README.md](../scripts/README.md))

## 따라 하기

모든 명령은 **`aws/terraform` 폴더**에서 칩니다.

1. **변수 파일 만들기**

   ```bash
   cd aws/terraform
   cp example.tfvars terraform.tfvars
   ```

   `terraform.tfvars` 를 열어 `region` · `expected_account_id` · `alert_email` 등을 고칩니다. 이 파일은 `.gitignore` 대상이라 커밋되지 않습니다(토큰을 넣어도 되는 유일한 곳).

2. **초기화** (프로바이더를 내려받음)

   ```bash
   terraform init
   ```

   ```
   Terraform has been successfully initialized!
   ```

3. **계획 보기** (아직 아무것도 만들지 않음 · 비용 없음)

   ```bash
   terraform plan -out tfplan
   ```

   끝에 `Plan: N to add, 0 to change, 0 to destroy.` 가 나오면 정상입니다(N 은 버전마다 다름). 처음 만드는 것이니 `change` · `destroy` 가 0 이어야 합니다.

4. **만들기** (15~20분, 여기부터 과금)

   ```bash
   terraform apply tfplan
   ```

   ```
   Apply complete! Resources: N added, 0 changed, 0 destroyed.
   ```

5. **다음에 칠 명령 받기**

   ```bash
   terraform output -raw next_steps
   ```

   내 리전 · 함수 이름 · 상태 머신 ARN 이 채워진 명령 4개(① `init-db` ② 기준 스냅숏 ③ 부하 ④ Grafana 포트 포워딩)가 나옵니다. 순서대로 실행하는 방법은 [aws/README.md](../README.md) 4장과 [statemachine/README.md](../statemachine/README.md) 에 있습니다.

6. **다 봤으면 지우기**

   ```bash
   terraform destroy
   ```

   확인 질문에 `yes` 를 입력하면 `Destroy complete! Resources: N destroyed.` 로 끝납니다. RDS 는 최종 스냅숏 없이 지워지고, S3 의 리포트 · 계획서와 비밀도 함께 지워집니다(필요한 리포트는 먼저 내려받으세요).

## 자주 바꾸는 변수

| 변수 | 기본값 | 바꾸는 경우 |
|---|---|---|
| `schedule_enabled` | `false` | 수동 실행으로 확인한 뒤 매일 자동 실행을 켤 때 `true` |
| `enable_workload` | `false` (`example.tfvars` 는 `true`) | 3시간마다 부하 Lambda 를 돌릴지 |
| `bedrock_model_id` | `global.anthropic.claude-sonnet-4-6` | 리전 · 모델이 다를 때 ([aws/README.md](../README.md) 3장) |
| `rules` | `min_sec = 0.5` · `min_q = 30` … | 실습 부하에서 티켓이 안 생기면 lab 과 같은 `0.2` · `5` 로 (객체라 6개 값을 모두 적음) |
| `analyze_max` | `5` | 실행 한 번의 분석 후보 0~10개 (일일 예산 제한 아님) |
| `grafana_allowed_cidrs` | `[]` | 비우면 SSM 포트 포워딩으로만 접속. 내 IP 만 열려면 `["x.x.x.x/32"]` |
| `publish_dry_run` · `enable_nat` | `true` · `false` | 실제 Jira · Slack 전송 (자격 증명도 필요) |

## 자주 막히는 곳

| 증상 | 원인 · 해결 |
|---|---|
| plan 에서 `filebase64sha256` · `no such file or directory` (`build/function.zip`) | 빌드를 안 했습니다. `aws` 폴더에서 `scripts/build.sh` |
| `No valid credential sources found` · `ExpiredToken` | AWS 자격 증명이 없거나 만료. `aws sts get-caller-identity` 가 되는지 먼저 확인 |
| Bedrock `AccessDeniedException` (분석 단계) | 모델 사용 권한이 없거나 리전에 그 프로필이 없음. `bedrock_model_id` 와 콘솔의 모델 접근 확인 |
| apply 가 RDS 에서 오래 멈춘 것 같다 | RDS 생성이 10분 이상 걸리는 것이 보통입니다 |
| Apple Silicon 에서 첫 init · plan 이 매우 느림 | x86_64 Terraform 을 쓰는 경우입니다. arm64 빌드를 권장 |
| `terraform.tfvars` 를 커밋할 뻔했다 | `aws/.gitignore` 가 막습니다. `example.tfvars` 에는 비밀을 넣지 마세요 |

## 다음 단계

- 상태 머신 실행 · 결과 확인: [statemachine/README.md](../statemachine/README.md)
- Lambda 함수별 역할: [lambda/README.md](../lambda/README.md)
- 비용 · 보안 · 제한 사항: [aws/README.md](../README.md)
- 전체 순서도: [docs/GETTING_STARTED.md](../../docs/GETTING_STARTED.md)

## 검증용 상태 관리

단발성 검증에서도 상태는 배포·수정·삭제 동안 같은 백엔드에 보관해야 합니다. 로컬 백엔드의 별도 경로를 사용할 때는 `-state` 플래그만 섞어 쓰기보다 `backend "local" {}`와 `terraform init -backend-config="path=..."`로 경로를 명시하세요. 상태와 저장된 계획에는 민감값이 포함될 수 있어 접근을 제한하고 Git에 넣지 않습니다.

## 삭제·반복 실행 전 확인

삭제 권한 점검과 잔존 자원 확인은 [OPERATIONS.md](../OPERATIONS.md)를 따릅니다. 명시적 거부가 있으면 정책을 우회하지 않고 승인된 예외 또는 승인된 삭제 담당 경로를 마련합니다. 검증 Lambda의 예약 동시 실행 수는 1이며 Map도 1입니다. 수집·티켓 기록까지 포함한 실행 전체의 동시 실행 잠금은 구현하지 않았으므로 일일 파이프라인을 겹쳐 시작하지 마세요.
