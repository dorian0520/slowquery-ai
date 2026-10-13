resource "aws_cloudwatch_log_group" "sfn" {
  name              = "/aws/vendedlogs/states/${local.p}-daily"
  retention_in_days = var.log_retention_days
}

resource "aws_sfn_state_machine" "daily" {
  name     = "${local.p}-daily"
  role_arn = aws_iam_role.sfn.arn
  type     = "STANDARD"

  definition = templatefile("${path.module}/../statemachine/daily.asl.json", {
    collect_arn       = aws_lambda_function.fn["collect"].arn
    detect_arn        = aws_lambda_function.fn["detect"].arn
    issue_tickets_arn = aws_lambda_function.fn["issue-tickets"].arn
    analyze_arn       = aws_lambda_function.fn["analyze"].arn
    verify_arn        = aws_lambda_function.fn["verify"].arn
    attach_arn        = aws_lambda_function.fn["attach"].arn
    track_arn         = aws_lambda_function.fn["track"].arn
    publish_arn       = aws_lambda_function.fn["publish"].arn
    report_arn        = aws_lambda_function.fn["report"].arn
    alert_topic_arn   = aws_sns_topic.alerts.arn
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn.arn}:*"
    include_execution_data = false # 실행 데이터(쿼리 본문 등)는 로그에 남기지 않는다
    level                  = "ERROR"
  }

  depends_on = [aws_iam_role_policy.sfn]
}
