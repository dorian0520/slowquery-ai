# EventBridge Scheduler — 매일 자정 직후 상태 머신 시작 (입력 {} → log_date = 어제)
resource "aws_scheduler_schedule" "daily" {
  name                         = "${local.p}-daily"
  description                  = "slowq daily pipeline"
  schedule_expression          = var.schedule_cron
  schedule_expression_timezone = var.schedule_timezone
  state                        = var.schedule_enabled ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.daily.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({})
    retry_policy {
      maximum_retry_attempts = 2
    }
  }
}

# 부하 발생 (선택) — 샘플 DB 에 느린 쿼리를 주기적으로 실행
resource "aws_scheduler_schedule" "workload" {
  count                        = var.enable_workload ? 1 : 0
  name                         = "${local.p}-workload"
  description                  = "slowq sample workload (demo only)"
  schedule_expression          = var.workload_schedule
  schedule_expression_timezone = var.schedule_timezone

  flexible_time_window {
    mode                      = "FLEXIBLE"
    maximum_window_in_minutes = 15
  }

  target {
    arn      = aws_lambda_function.fn["workload"].arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ scale = 1.0 })
    retry_policy {
      maximum_retry_attempts = 0
    }
  }
}
