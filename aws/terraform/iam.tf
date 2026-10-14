# IAM — Lambda 마다 역할을 따로 두고, 필요한 비밀 · 버킷 경로 · 모델만 허용한다.

locals {
  # Bedrock 모델 ID 해석: "global.x" · "us.x" 같은 추론 프로필이면 프로필 + 기반 모델 권한이 둘 다 필요하다.
  bedrock_profile_prefixes = ["global", "us", "eu", "apac", "jp", "au", "ca", "us-gov"]
  bedrock_id_parts         = split(".", var.bedrock_model_id)
  bedrock_is_profile       = contains(local.bedrock_profile_prefixes, local.bedrock_id_parts[0])
  bedrock_is_global        = local.bedrock_id_parts[0] == "global"
  bedrock_base_model       = local.bedrock_is_profile ? join(".", slice(local.bedrock_id_parts, 1, length(local.bedrock_id_parts))) : var.bedrock_model_id
  bedrock_profile_arn      = "arn:${local.partition}:bedrock:${local.region}:${local.account_id}:inference-profile/${var.bedrock_model_id}"
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "fn" {
  for_each           = local.functions
  name               = "${local.p}-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "fn" {
  for_each = local.functions

  # 로그: 자기 로그 그룹에만
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.fn[each.key].arn}:*"]
  }

  # VPC 안 Lambda 의 ENI 관리 (AWS 가 리소스 수준 제한을 지원하지 않는 동작들)
  statement {
    sid = "VpcEni"
    actions = [
      "ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DescribeSubnets", "ec2:DeleteNetworkInterface",
      "ec2:AssignPrivateIpAddresses", "ec2:UnassignPrivateIpAddresses",
    ]
    resources = ["*"]
  }

  # 필요한 비밀만
  statement {
    sid       = "Secrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [for s in each.value.secrets : local.secret_arns[s]]
  }

  dynamic "statement" {
    for_each = length(each.value.s3_prefixes) > 0 ? [1] : []
    content {
      sid       = "ArtifactsWrite"
      actions   = ["s3:PutObject"]
      resources = [for pfx in each.value.s3_prefixes : "${aws_s3_bucket.artifacts.arn}/${pfx}*"]
    }
  }

  # Bedrock: 설정한 모델(추론 프로필)만. 프로필 → 기반 모델 호출은 그 프로필을 거칠 때만 허용.
  dynamic "statement" {
    for_each = each.value.bedrock && local.bedrock_is_profile ? [1] : []
    content {
      sid       = "BedrockProfile"
      actions   = ["bedrock:InvokeModel"]
      resources = [local.bedrock_profile_arn]
    }
  }
  dynamic "statement" {
    for_each = each.value.bedrock && local.bedrock_is_profile ? [1] : []
    content {
      sid     = "BedrockModelViaProfile"
      actions = ["bedrock:InvokeModel"]
      resources = concat(
        ["arn:${local.partition}:bedrock:*::foundation-model/${local.bedrock_base_model}"],
        local.bedrock_is_global ? ["arn:${local.partition}:bedrock:::foundation-model/${local.bedrock_base_model}"] : [],
      )
      condition {
        test     = "StringEquals"
        variable = "bedrock:InferenceProfileArn"
        values   = [local.bedrock_profile_arn]
      }
    }
  }
  dynamic "statement" {
    for_each = each.value.bedrock && !local.bedrock_is_profile ? [1] : []
    content {
      sid       = "BedrockModel"
      actions   = ["bedrock:InvokeModel"]
      resources = ["arn:${local.partition}:bedrock:${local.region}::foundation-model/${var.bedrock_model_id}"]
    }
  }
}

resource "aws_iam_role_policy" "fn" {
  for_each = local.functions
  name     = "least-privilege"
  role     = aws_iam_role.fn[each.key].id
  policy   = data.aws_iam_policy_document.fn[each.key].json
}

# Step Functions: 파이프라인 Lambda 호출 + SNS 알림 + 실행 로그
data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "sfn" {
  name               = "${local.p}-sfn"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
}

data "aws_iam_policy_document" "sfn" {
  statement {
    sid       = "InvokePipelineFunctions"
    actions   = ["lambda:InvokeFunction"]
    resources = flatten([for k in local.pipeline_functions : [aws_lambda_function.fn[k].arn, "${aws_lambda_function.fn[k].arn}:*"]])
  }
  statement {
    sid       = "Alert"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
  }
  statement {
    sid = "ExecutionLogs" # CloudWatch Logs 전달 설정 API 는 리소스 수준 제한이 없다
    actions = [
      "logs:CreateLogDelivery", "logs:GetLogDelivery", "logs:UpdateLogDelivery", "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries", "logs:PutResourcePolicy", "logs:DescribeResourcePolicies", "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "sfn" {
  name   = "pipeline"
  role   = aws_iam_role.sfn.id
  policy = data.aws_iam_policy_document.sfn.json
}

# EventBridge Scheduler: 상태 머신 시작 · 부하 Lambda 호출만
data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${local.p}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    actions   = ["states:StartExecution"]
    resources = [aws_sfn_state_machine.daily.arn]
  }
  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.fn["workload"].arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "start"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}
