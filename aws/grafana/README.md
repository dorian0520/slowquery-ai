# aws/grafana — Grafana EC2 설치 스크립트

AWS 버전에서 Grafana 를 띄울 EC2 인스턴스가 **처음 부팅할 때 실행하는 설치 스크립트 템플릿** 하나가 있습니다. 직접 실행하지 않고, Terraform(`terraform/grafana.tf`)이 값을 채워 EC2 `user_data` 로 넘깁니다.

## 파일

| 파일 | 역할 | 언제 보나 |
|---|---|---|
| `user_data.sh.tftpl` | Grafana OSS 설치(Amazon Linux 2023 · arm64) → Secrets Manager 에서 DB · 관리자 비밀번호 읽기 → MySQL 데이터 소스(TLS · 읽기 전용 계정) 등록 → S3 에서 대시보드 JSON 받아 등록 | Grafana 가 안 뜰 때 · 설치 과정을 볼 때 |

- 대시보드는 로컬 실습과 **같은 파일**(`lab/grafana/dashboards/slowquery.json`)을 쓰고, 데이터 소스 uid 만 `slowq-store` 로 바꿉니다(`terraform/grafana.tf`).
- `${region}` · `${bucket}` 처럼 `${…}` 로 된 자리는 Terraform 이 채웁니다. 그래서 셸에서 바로 실행할 수 없습니다.
- 설치 로그는 인스턴스의 `/var/log/slowq-grafana-setup.log` 에 남습니다.

## 준비물

- [terraform/README.md](../terraform/README.md) 로 배포 완료 (apply 후 설치까지 3~5분)
- `init-db` 실행 완료 — 그 전에는 데이터 소스 접속이 실패합니다 ([lambda/README.md](../lambda/README.md) 3단계)
- AWS CLI v2 + **Session Manager 플러그인** (기본 설정은 Grafana 를 인터넷에 열지 않고 SSM 포트 포워딩으로만 접속)

## 따라 하기

`aws/terraform` 폴더에서 칩니다.

1. **포트 포워딩 열기** (이 터미널은 열어 둡니다)

   ```bash
   cd aws/terraform
   aws ssm start-session --target "$(terraform output -raw grafana_instance_id)" \
     --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["3000"],"localPortNumber":["3000"]}'
   ```

   `Port 3000 opened for sessionId …` · `Waiting for connections...` 가 나오면 준비된 것입니다.

2. **브라우저로 열기** — http://localhost:3000/d/lab-slowquery

3. **관리자 로그인이 필요할 때만** — 비밀번호를 화면에 띄우므로 주변을 확인하고 실행합니다.

   ```bash
   aws secretsmanager get-secret-value \
     --secret-id "$(terraform output -raw grafana_admin_secret_arn)" --query SecretString --output text
   ```

4. **`grafana_allowed_cidrs` 에 내 IP 를 넣었다면** 포트 포워딩 없이 `terraform output -raw grafana_url` 주소로 바로 엽니다.

## 자주 막히는 곳

| 증상 | 원인 · 해결 |
|---|---|
| `SessionManagerPlugin is not found` | Session Manager 플러그인을 설치합니다 (AWS 문서의 「Session Manager 플러그인 설치」) |
| `TargetNotConnected` | 인스턴스가 아직 부팅 · 설치 중입니다. apply 후 3~5분 기다린 뒤 다시 |
| 브라우저가 연결 거부 | 1단계 터미널이 닫혔거나 로컬 3000 포트를 다른 프로그램(로컬 lab Grafana 등)이 쓰고 있습니다. 로컬 Grafana 를 멈추거나 `localPortNumber` 를 `3001` 로 바꾸고 http://localhost:3001 |
| 패널이 모두 데이터 소스 오류 | `init-db` 를 아직 안 했습니다. 실행 후 새로 고침 |
| 그래프가 비어 있다 | 상태 머신을 두 번 이상 돌려야 하루치 데이터가 생깁니다 ([statemachine/README.md](../statemachine/README.md)) |
| 설치가 실패한 것 같다 | `aws ssm start-session --target <grafana_instance_id>` 로 접속해 `sudo tail -50 /var/log/slowq-grafana-setup.log` |

## 다음 단계

- 대시보드 패널 읽는 법: [lab/grafana/README.md](../../lab/grafana/README.md) · [docs/04-dashboard.md](../../docs/04-dashboard.md)
- 다 봤으면 삭제: [terraform/README.md](../terraform/README.md) 6단계
- 전체 순서도: [docs/GETTING_STARTED.md](../../docs/GETTING_STARTED.md)

## 실제 실행에서 확인한 설정

RPM 설치는 `/etc/grafana/grafana.ini`의 file provider로 관리자 비밀번호를 읽습니다. Docker 환경 변수 전용 설정으로 대체하지 않습니다. MySQL datasource는 특수문자 비밀번호·여러 줄 CA를 보존하는 JSON/YAML 호환 문서로 생성하고 TLS 검증을 켭니다. NAT가 꺼진 경우 Grafana 보안 그룹에도 Secrets Manager 인터페이스 엔드포인트 443 접근 규칙이 필요합니다. 실제 관리자 인증·TLS 연결·대시보드 SQL 8개는 확인했으며, 전체 브라우저 UI 검사는 별개입니다.
