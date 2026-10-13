# 비밀 값은 출력하지 않는다 — 비밀의 ARN 과 다음에 실행할 명령만.

output "state_machine_arn" {
  description = "일일 파이프라인 상태 머신"
  value       = aws_sfn_state_machine.daily.arn
}

output "target_db_endpoint" {
  description = "대상 DB(shop-db, 저장소 dba 포함) 주소 — 프라이빗"
  value       = aws_db_instance.target.address
}

output "verify_db_endpoint" {
  description = "검증 DB(order-db) 주소 — 프라이빗"
  value       = aws_db_instance.verify.address
}

output "artifacts_bucket" {
  description = "리포트 · 변경 계획서 버킷"
  value       = aws_s3_bucket.artifacts.bucket
}

output "grafana_admin_secret_arn" {
  description = "Grafana 관리자 비밀번호가 든 비밀 (값은 콘솔 또는 get-secret-value 로 직접 확인)"
  value       = aws_secretsmanager_secret.grafana_admin.arn
}

output "grafana_instance_id" {
  value = aws_instance.grafana.id
}

output "grafana_url" {
  description = "Grafana 주소 (grafana_allowed_cidrs 를 비웠다면 아래 SSM 포트 포워딩 후 localhost)"
  value       = local.dashboard_url
}

output "next_steps" {
  description = "apply 다음에 실행할 명령"
  value       = <<-EOT
    # 1) 샘플 데이터 · 저장소 스키마 · 최소 권한 계정 · CMDB (한 번, 수 분)
    aws lambda invoke --region ${local.region} --function-name ${aws_lambda_function.fn["init-db"].function_name} \
      --cli-read-timeout 910 --payload '{}' --cli-binary-format raw-in-base64-out /dev/stdout
    # 2) 기준 스냅숏 (첫 실행은 기준만 남김)
    aws stepfunctions start-execution --region ${local.region} --state-machine-arn ${aws_sfn_state_machine.daily.arn} --input '{}'
    # 3) 부하 → 다음 실행부터 하루치 차이가 쌓임
    aws lambda invoke --region ${local.region} --function-name ${aws_lambda_function.fn["workload"].function_name} \
      --cli-read-timeout 910 --payload '{"scale": 1.0}' --cli-binary-format raw-in-base64-out /dev/stdout
    # 4) Grafana (SSM 포트 포워딩)
    aws ssm start-session --region ${local.region} --target ${aws_instance.grafana.id} \
      --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["3000"],"localPortNumber":["3000"]}'
  EOT
}
