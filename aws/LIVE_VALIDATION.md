# 독립 AWS 스택 실행 검증 기록

검증일: 2026-10-14. 공개 main의 기반 커밋은 `aed82bf4f6b4acebeb28b0b59e622d3e193c3622`입니다. 검증 계정·프로필·ARN·비밀번호는 공개 소스에 넣지 않았습니다. 전용 이름과 새 VPC/RDS를 사용했으며 기존 데이터베이스에는 접속하지 않았습니다.

## 실제 확인한 범위

- 서울 리전, Terraform 1.10.5 arm64 / AWS provider 5.100.0.
- RDS MySQL 8.4.11 `db.t4g.micro` 두 대에 각각 합성 주문 200만 행 생성.
- 기준 수집은 0건 차이로 완료, 합성 부하 후 쿼리 3건 검출·티켓 3건 발행.
- Bedrock `global.anthropic.claude-sonnet-4-6` 실제 호출: 3턴, 근거 도구 4회. 입력 8,785 / 출력 1,196 토큰.
- 검증 DB의 주문 조회: 전 0.744543초 / 후 0.002142초, 결과 동일, 통과. 한 쿼리·한 환경에서 관측한 최소 측정값이며 일반적인 개선율 보장이 아닙니다.
- 검증 인덱스 잔존 없음, target의 수동 테스트 인덱스도 제거.
- 동일 검출 결과 재발행은 신규 0건. 통과 제안의 S3 변경 계획 생성, `executed=false` 확인.
- 합성 target에 수동 시험 인덱스를 추가한 뒤 실제 부하·수집·Track으로 `OPEN→RESOLVED`, 인덱스 제거 및 4개 동시 부하 후 `RESOLVED→REOPENED` 확인. 재발 시험은 통제한 동시 부하를 포함하므로 인덱스 단독 인과 효과로 주장하지 않습니다. 임시 진단 Lambda는 삭제했습니다.
- S3 Markdown/HTML 리포트 생성. 잘못된 날짜 입력은 실패 경로를 거쳐 `FAILED`로 종료.
- Grafana 13.2.3 arm64 관리자 인증, TLS 데이터 소스 연결, 대시보드 로드와 티켓 3건 조회 성공.
- 대시보드 SQL 8개 모두 실제 DB에서 성공. 변수 값을 명시적으로 치환한 API 검사이며 브라우저 자동 변수 선택은 검사하지 않았습니다.
- Jira·Slack은 dry-run, 실제 메시지·이슈 전송 없음. SNS 시험 토픽의 외부 수신 구독 없음.

## 실행 중 수정한 것

1. 배포·삭제할 계정을 지정할 수 있는 `expected_account_id` / provider 계정 제한 추가. 잘못된 계정 ID의 계획을 실제로 거부함.
2. 기본 MySQL 8.4와 버전에 맞는 파라미터 그룹. 8.0 표준 지원 종료 후 신규 실습의 기본값을 보완함.
3. Grafana가 Secrets Manager의 private DNS 엔드포인트에 접근하도록 보안 그룹 규칙 추가. 원래 설치는 연결 시간 초과로 중단됐고 수정 후 조회 성공.
4. RPM Grafana의 관리자 비밀번호를 `grafana.ini` file provider로 구성. 원래 설정은 서비스가 기동해도 생성한 비밀번호로 401이 발생했고 수정 후 인증 성공.
5. 데이터 소스의 비밀번호·PEM은 JSON/YAML 호환 문서로 직렬화하고 `$`와 여러 줄·따옴표를 보존. file provider 표현을 datasource provisioning 값으로 사용하지 않음.
6. Lambda VPC 역할에 공식 최소 목록의 `ec2:DescribeSubnets` 보완. IAM 시뮬레이션에서 원래 implicitDeny를 확인.
7. 인덱스 되돌리기 확인 실패는 통과를 반환하지 않고 오류로 보고. 원본 재현 검사 실패 → 수정 후 통과.
8. 정적 검사의 금지 문자열 출력은 위치만 표시하고 상태·계획·개인 변수 파일을 제외하여 민감값 출력 방지.
9. 삭제 중 실행 역할이 먼저 제거돼 ENI 정리가 지연되는 상황을 확인했습니다. 네트워크 인터페이스가 사용하는 보안 그룹보다 역할 정책이 먼저 삭제되지 않도록 의존성을 보완했고 Terraform 구성 검증을 통과했습니다. 이 마지막 순서 보완은 정적 검증이며 새 스택의 생성·삭제 반복 검증은 아직 별도로 하지 않았습니다.

## 자동 검사

최초 실행 수정본의 단위 테스트 77개, Terraform fmt/validate, ASL 구조, Python·셸 문법, 대시보드 JSON, 공개 소스 금지 문자열 검사를 통과했습니다. 특수문자 비밀번호·여러 줄 인증서의 실제 provisioning 렌더러도 임시 파일로 검사했습니다.

## 제거와 남은 한계

Lambda 네트워크 인터페이스 2개와 임시 정리 역할·시험 로그까지 삭제했습니다. EC2/EBS, Lambda, S3, Step Functions, Scheduler, SNS, 애플리케이션 비밀값은 잔존 0건입니다. 현재 역할의 `rds:DeleteDBInstance` 명시적 거부로 합성 검증 RDS 2대와 연결된 VPC·백업·RDS 관리 비밀값이 남아 있습니다. 사용자가 승인된 삭제 예외를 마련하는 중이며 제거 완료로 표시하지 않습니다.

배포 전 `scripts/preflight.py`에서 예상 계정과 이번 실행의 정확한 두 DB 삭제 권한을 읽기 전용으로 검사하도록 추가했습니다. 현재 역할의 두 명시적 거부를 실제로 확인했고 관련 자동 검사 2개를 통과했습니다. IAM 시뮬레이션은 조직 정책·리소스 조건을 포함한 실제 API 성공을 보장하지 않습니다.

다른 계정의 조직 정책·리전·기존 운영 DB 이식·Jira/Slack 실제 전송·복구 SLA·장기 성능·브라우저 전체 UI·청구 확정액을 검증한 기록은 아닙니다. 상태와 자격 증명은 공개 자료에서 제외합니다.

## 추가 소스 검토

이후 Lambda·공유 로직·ASL·스크립트·문서를 확장 검토하고 AWS 단위 검사 115개를 통과했습니다. 최신 수정의 기능 검사·AWS 정의 검증 결과와 실제 재배포 미실행을 [SOURCE_REVIEW.md](SOURCE_REVIEW.md)에 구분했습니다.

## 참고 근거

- [AWS Lambda VPC ENI와 실행 역할의 삭제 순서](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html)
- [AWS Lambda VPC 최소 권한](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AWSLambdaVPCAccessExecutionRole.html)
- [RDS MySQL 지원 버전](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/MySQL.Concepts.VersionMgmt.html)
- [Grafana RPM 설정과 file provider](https://grafana.com/docs/grafana/latest/setup-grafana/configure-grafana/)
- [Grafana provisioning 환경 변수와 직렬화](https://grafana.com/docs/grafana/latest/administration/provisioning/)
