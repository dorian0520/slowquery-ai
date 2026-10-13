# 복사해서 terraform.tfvars 로 쓴다 (terraform.tfvars 는 .gitignore 대상 — 토큰을 커밋하지 않는다).
region      = "ap-northeast-2"
name_prefix = "slowq"

# Bedrock: 서울 리전은 global. 추론 프로필만 지원 (README 「Bedrock 모델 ID」 참고)
bedrock_model_id = "global.anthropic.claude-sonnet-4-6"

# 처음에는 수동 실행으로 확인한 뒤 켠다
schedule_enabled = false
enable_workload  = true

# 실패 알림 메일 (구독 확인 메일의 링크를 눌러야 받는다)
alert_email = ""

# Grafana 를 내 IP 에서만 열 때 (비우면 SSM 포트 포워딩으로만 접속)
grafana_allowed_cidrs = []

# 실제 Jira · Slack 전송: publish_dry_run=false + 자격 증명 + enable_nat=true 가 모두 필요
publish_dry_run = true
enable_nat      = false
# jira = {
#   base_url    = "https://<내 사이트>.atlassian.net"
#   email       = "<봇 계정 이메일>"
#   api_token   = "<API 토큰>"
#   project_key = "SLOWQ"
# }
# slack_bot_token = "<xoxb-...>"
