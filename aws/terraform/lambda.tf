# Lambda — 패키지 하나(aws/lambda/slowq_aws + skeleton/slowq + SQL)를 모든 함수가 같이 쓰고, 핸들러만 다르다.
# pymysql · cryptography 는 레이어로 분리. 둘 다 scripts/build.sh 로 먼저 만든다.

locals {
  secret_arns = merge(
    { for k, s in aws_secretsmanager_secret.db : k => s.arn },
    {
      target_master = aws_db_instance.target.master_user_secret[0].secret_arn
      verify_master = aws_db_instance.verify.master_user_secret[0].secret_arn
      publish       = aws_secretsmanager_secret.publish.arn
    },
  )

  # 함수별: 핸들러 · 제한 시간 · 메모리 · 읽을 수 있는 비밀 · S3 쓰기 경로 · Bedrock 사용 여부
  functions = {
    init-db       = { handler = "slowq_aws.init_db.handler", timeout = 900, memory = var.lambda_memory_mb, secrets = ["target_master", "verify_master", "collector", "store", "ai", "verify", "grafana", "workload"], s3_prefixes = [], bedrock = false }
    workload      = { handler = "slowq_aws.workload.handler", timeout = 900, memory = var.lambda_memory_mb, secrets = ["workload"], s3_prefixes = [], bedrock = false }
    collect       = { handler = "slowq_aws.collect.handler", timeout = 300, memory = var.lambda_memory_mb, secrets = ["store", "collector"], s3_prefixes = [], bedrock = false }
    detect        = { handler = "slowq_aws.detect.handler", timeout = 120, memory = var.lambda_memory_mb, secrets = ["store"], s3_prefixes = [], bedrock = false }
    issue-tickets = { handler = "slowq_aws.issue_tickets.handler", timeout = 120, memory = var.lambda_memory_mb, secrets = ["store"], s3_prefixes = [], bedrock = false }
    analyze       = { handler = "slowq_aws.analyze.handler", timeout = 900, memory = var.lambda_memory_mb, secrets = ["ai"], s3_prefixes = [], bedrock = true }
    verify        = { handler = "slowq_aws.verify.handler", timeout = 900, memory = var.lambda_memory_mb, secrets = ["verify"], s3_prefixes = [], bedrock = false }
    attach        = { handler = "slowq_aws.attach.handler", timeout = 60, memory = var.lambda_memory_mb, secrets = ["store"], s3_prefixes = [], bedrock = false }
    track         = { handler = "slowq_aws.track.handler", timeout = 120, memory = var.lambda_memory_mb, secrets = ["store"], s3_prefixes = [], bedrock = false }
    publish       = { handler = "slowq_aws.publish.handler", timeout = 300, memory = var.lambda_memory_mb, secrets = ["store", "publish"], s3_prefixes = [], bedrock = false }
    report        = { handler = "slowq_aws.report.handler", timeout = 300, memory = var.lambda_memory_mb, secrets = ["store"], s3_prefixes = ["reports/"], bedrock = false }
    apply-plan    = { handler = "slowq_aws.apply_plan.handler", timeout = 120, memory = var.lambda_memory_mb, secrets = ["store", "ai"], s3_prefixes = ["plans/"], bedrock = false }
  }

  # Step Functions 가 부르는 함수 (init-db · workload · apply-plan 은 수동 또는 별도 스케줄)
  pipeline_functions = ["collect", "detect", "issue-tickets", "analyze", "verify", "attach", "track", "publish", "report"]

  # 비밀 '값'이 아니라 ARN 만 넘긴다
  lambda_env = {
    TARGET_HOST              = aws_db_instance.target.address
    VERIFY_HOST              = aws_db_instance.verify.address
    DB_PORT                  = "3306"
    STORE_DB                 = "dba"
    SHOP_DB                  = "shop"
    TARGET_MASTER_SECRET_ARN = local.secret_arns.target_master
    VERIFY_MASTER_SECRET_ARN = local.secret_arns.verify_master
    COLLECTOR_SECRET_ARN     = local.secret_arns.collector
    STORE_SECRET_ARN         = local.secret_arns.store
    AI_SECRET_ARN            = local.secret_arns.ai
    VERIFY_SECRET_ARN        = local.secret_arns.verify
    GRAFANA_SECRET_ARN       = local.secret_arns.grafana
    WORKLOAD_SECRET_ARN      = local.secret_arns.workload
    PUBLISH_SECRET_ARN       = local.secret_arns.publish
    PUBLISH_DRY_RUN          = var.publish_dry_run ? "true" : "false"
    BEDROCK_MODEL_ID         = var.bedrock_model_id
    ANALYZE_MAX              = tostring(var.analyze_max)
    ANALYZE_MAX_TURNS        = "8"
    ANALYZE_MAX_TOKENS       = "4096"
    REPORT_BUCKET            = aws_s3_bucket.artifacts.bucket
    REPORT_WEEKDAY           = tostring(var.report_weekday)
    TZ_NAME                  = var.schedule_timezone
    DASHBOARD_URL            = local.dashboard_url
    RULE_MIN_SEC             = tostring(var.rules.min_sec)
    RULE_MIN_Q               = tostring(var.rules.min_q)
    RULE_WORSE_RATIO         = tostring(var.rules.worse_ratio)
    RULE_SPIKE_RATIO         = tostring(var.rules.spike_ratio)
    RULE_SPIKE_MIN_TOTAL     = tostring(var.rules.spike_min_total)
    RULE_TOP_N               = tostring(var.rules.top_n)
  }
}

resource "aws_cloudwatch_log_group" "fn" {
  for_each          = local.functions
  name              = "/aws/lambda/${local.p}-${each.key}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_layer_version" "deps" {
  layer_name               = "${local.p}-deps"
  description              = "pymysql + cryptography (arm64, python3.12)"
  filename                 = local.layer_zip
  source_code_hash         = filebase64sha256(local.layer_zip)
  compatible_runtimes      = ["python3.12"]
  compatible_architectures = ["arm64"]
}

resource "aws_lambda_function" "fn" {
  for_each         = local.functions
  function_name    = "${local.p}-${each.key}"
  role             = aws_iam_role.fn[each.key].arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = each.value.handler
  filename         = local.function_zip
  source_code_hash = filebase64sha256(local.function_zip)
  layers           = [aws_lambda_layer_version.deps.arn]
  timeout          = each.value.timeout
  memory_size      = each.value.memory
  # Map 동시성은 실행 하나만 제한한다. 다른 실행/수동 호출도 검증 DB 측정에 섞이지 않게 한다.
  reserved_concurrent_executions = each.key == "verify" ? 1 : -1

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = local.lambda_env
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.fn[each.key].name
  }

  depends_on = [aws_iam_role_policy.fn, aws_cloudwatch_log_group.fn]
}
