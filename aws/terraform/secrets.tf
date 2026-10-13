# 애플리케이션 DB 계정 (최소 권한) — 비밀번호는 Terraform 이 만들고 Secrets Manager 에만 둔다.
# 출력(outputs)에는 비밀 값이 나가지 않는다. 계정 생성 · 권한 부여는 init_db Lambda 가 한다.
# 주의: random_password 값은 Terraform 상태 파일에 남는다 → 상태 파일은 암호화된 원격 백엔드에 둔다(versions.tf 참고).

locals {
  db_accounts = {
    collector = "slowq_collector" # 대상: performance_schema SELECT
    store     = "slowq_store"     # 대상: dba DML
    ai        = "slowq_ai"        # 대상: shop SELECT + dba.slow_digest_daily SELECT
    verify    = "slowq_verify"    # 검증 DB: shop 인덱스 추가 · 삭제
    grafana   = "slowq_grafana"   # 대상: dba SELECT
    workload  = "slowq_workload"  # 대상: shop SELECT (부하 발생)
  }
}

resource "random_password" "db" {
  for_each         = local.db_accounts
  length           = 32
  special          = true
  override_special = "-_.~+"
}

resource "aws_secretsmanager_secret" "db" {
  for_each                = local.db_accounts
  name_prefix             = "${local.p}/db/${each.key}-"
  description             = "slowq DB account ${each.value}"
  recovery_window_in_days = 0 # 실습 스택: destroy 후 같은 이름으로 다시 만들 수 있게
}

resource "aws_secretsmanager_secret_version" "db" {
  for_each      = local.db_accounts
  secret_id     = aws_secretsmanager_secret.db[each.key].id
  secret_string = jsonencode({ username = each.value, password = random_password.db[each.key].result })
}

# Grafana 관리자 비밀번호
resource "random_password" "grafana_admin" {
  length           = 24
  special          = true
  override_special = "-_.~+"
}

resource "aws_secretsmanager_secret" "grafana_admin" {
  name_prefix             = "${local.p}/grafana/admin-"
  description             = "slowq Grafana admin"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "grafana_admin" {
  secret_id     = aws_secretsmanager_secret.grafana_admin.id
  secret_string = jsonencode({ username = "admin", password = random_password.grafana_admin.result })
}

# 발행(Jira · Slack) 자격 증명 — 설정한 경우에만 값이 들어간다. 비어 있으면 publish 는 dry-run.
locals {
  publish_secret = merge(
    var.jira == null ? {} : {
      jira_base_url    = var.jira.base_url
      jira_email       = var.jira.email
      jira_api_token   = var.jira.api_token
      jira_project_key = var.jira.project_key
      jira_issue_type  = var.jira.issue_type
      jira_api_version = var.jira.api_version
    },
    var.slack_bot_token == "" ? {} : { slack_bot_token = var.slack_bot_token },
    var.slack_webhook_url == "" ? {} : { slack_webhook_url = var.slack_webhook_url },
  )
}

resource "aws_secretsmanager_secret" "publish" {
  name_prefix             = "${local.p}/publish-"
  description             = "slowq Jira/Slack credentials (optional)"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "publish" {
  secret_id     = aws_secretsmanager_secret.publish.id
  secret_string = jsonencode(local.publish_secret)
}
