# Grafana OSS — EC2 한 대 (Amazon Linux 2023, arm64). 대시보드는 lab/grafana 가 만든 JSON 을 그대로 쓰고
# 데이터 소스 uid 만 바꾼다. 접속은 grafana_allowed_cidrs(선택) 또는 SSM 포트 포워딩.

locals {
  dashboard_key  = "grafana/slowquery.json"
  dashboard_json = replace(file("${path.module}/../../lab/grafana/dashboards/slowquery.json"), "\"lab-dba\"", "\"slowq-store\"")
  dashboard_url  = length(var.grafana_allowed_cidrs) > 0 ? "http://${aws_instance.grafana.public_ip}:3000/d/lab-slowquery" : "http://localhost:3000/d/lab-slowquery"
}

data "aws_ssm_parameter" "al2023_arm64" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_s3_object" "dashboard" {
  bucket       = aws_s3_bucket.artifacts.id
  key          = local.dashboard_key
  content      = local.dashboard_json
  content_type = "application/json"
  etag         = md5(local.dashboard_json)
}

resource "aws_security_group" "grafana" {
  name        = "${local.p}-grafana"
  description = "slowq Grafana"
  vpc_id      = aws_vpc.this.id
  tags        = { Name = "${local.p}-grafana" }
}

resource "aws_vpc_security_group_ingress_rule" "grafana_http" {
  for_each          = toset(var.grafana_allowed_cidrs)
  security_group_id = aws_security_group.grafana.id
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 3000
  to_port           = 3000
  description       = "Grafana UI"
}

resource "aws_vpc_security_group_egress_rule" "grafana_https" {
  security_group_id = aws_security_group.grafana.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "Package repo, Secrets Manager, S3, SSM"
}

resource "aws_vpc_security_group_egress_rule" "grafana_http_repo" {
  security_group_id = aws_security_group.grafana.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  description       = "OS package mirrors"
}

resource "aws_vpc_security_group_egress_rule" "grafana_mysql" {
  security_group_id            = aws_security_group.grafana.id
  referenced_security_group_id = aws_security_group.rds.id
  ip_protocol                  = "tcp"
  from_port                    = 3306
  to_port                      = 3306
  description                  = "MySQL (read-only account)"
}

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "grafana" {
  name               = "${local.p}-grafana"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "grafana_ssm" {
  role       = aws_iam_role.grafana.name
  policy_arn = "arn:${local.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "grafana" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.db["grafana"].arn, aws_secretsmanager_secret.grafana_admin.arn]
  }
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.artifacts.arn}/${local.dashboard_key}"]
  }
}

resource "aws_iam_role_policy" "grafana" {
  name   = "read-config"
  role   = aws_iam_role.grafana.id
  policy = data.aws_iam_policy_document.grafana.json
}

resource "aws_iam_instance_profile" "grafana" {
  name = "${local.p}-grafana"
  role = aws_iam_role.grafana.name
}

resource "aws_instance" "grafana" {
  ami                         = data.aws_ssm_parameter.al2023_arm64.value
  instance_type               = var.grafana_instance_type
  subnet_id                   = aws_subnet.public[0].id
  vpc_security_group_ids      = [aws_security_group.grafana.id]
  iam_instance_profile        = aws_iam_instance_profile.grafana.name
  associate_public_ip_address = true # 패키지 설치용 아웃바운드 (인바운드는 보안 그룹이 막는다)

  credit_specification {
    cpu_credits = "standard" # T4g 잉여 CPU 크레딧 과금 대신 크레딧 소진 시 제한
  }

  metadata_options {
    http_tokens   = "required" # IMDSv2 만
    http_endpoint = "enabled"
  }

  root_block_device {
    volume_size = 8
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = templatefile("${path.module}/../grafana/user_data.sh.tftpl", {
    region           = local.region
    db_host          = aws_db_instance.target.address
    db_name          = "dba"
    ds_secret_arn    = aws_secretsmanager_secret.db["grafana"].arn
    admin_secret_arn = aws_secretsmanager_secret.grafana_admin.arn
    bucket           = aws_s3_bucket.artifacts.bucket
    dashboard_key    = local.dashboard_key
  })
  user_data_replace_on_change = true

  tags       = { Name = "${local.p}-grafana" }
  depends_on = [aws_s3_object.dashboard, aws_secretsmanager_secret_version.db, aws_secretsmanager_secret_version.grafana_admin]
}
