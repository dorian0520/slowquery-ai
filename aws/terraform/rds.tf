# RDS MySQL 8.0 두 대
#   target (shop-db) : 서비스 DB 역할 + 자동화 저장소 스키마 dba (lab 과 같은 배치)
#   verify (order-db): 실측 검증 DB — AI 제안 인덱스를 여기에만 만들었다가 지운다
# 마스터 비밀번호는 RDS 가 Secrets Manager 에 직접 만들고 관리한다(manage_master_user_password) — Terraform 상태에 남지 않는다.

resource "aws_db_subnet_group" "this" {
  name       = "${local.p}-db"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_parameter_group" "mysql" {
  name        = "${local.p}-mysql80"
  family      = "mysql8.0"
  description = "slowq: performance_schema digest + slow log"

  # 정적 파라미터는 생성 시점에 적용된다 (나중에 바꾸면 재부팅 필요)
  parameter {
    name         = "performance_schema"
    value        = "1"
    apply_method = "pending-reboot"
  }
  parameter {
    name         = "performance_schema_digests_size"
    value        = "10000"
    apply_method = "pending-reboot"
  }
  parameter {
    name         = "performance_schema_max_digest_length"
    value        = "4096"
    apply_method = "pending-reboot"
  }
  parameter {
    name         = "max_digest_length"
    value        = "4096"
    apply_method = "pending-reboot"
  }
  parameter {
    name  = "slow_query_log"
    value = "1"
  }
  parameter {
    name  = "long_query_time"
    value = "0.5"
  }
  parameter {
    name  = "log_output"
    value = "FILE"
  }
  parameter {
    name  = "require_secure_transport"
    value = "1" # 평문 접속 거부 — Lambda · Grafana 모두 TLS 로 접속
  }
}

locals {
  db_common = {
    engine                  = "mysql"
    engine_version          = var.db_engine_version
    instance_class          = var.db_instance_class
    allocated_storage       = var.db_allocated_storage
    storage_type            = "gp3"
    storage_encrypted       = true
    db_subnet_group_name    = aws_db_subnet_group.this.name
    parameter_group_name    = aws_db_parameter_group.mysql.name
    vpc_security_group_ids  = [aws_security_group.rds.id]
    username                = "slowq_admin"
    backup_retention_period = 1
  }
}

resource "aws_db_instance" "target" {
  identifier                      = "${local.p}-shop-db"
  engine                          = local.db_common.engine
  engine_version                  = local.db_common.engine_version
  instance_class                  = local.db_common.instance_class
  allocated_storage               = local.db_common.allocated_storage
  storage_type                    = local.db_common.storage_type
  storage_encrypted               = local.db_common.storage_encrypted
  db_subnet_group_name            = local.db_common.db_subnet_group_name
  parameter_group_name            = local.db_common.parameter_group_name
  vpc_security_group_ids          = local.db_common.vpc_security_group_ids
  username                        = local.db_common.username
  manage_master_user_password     = true
  backup_retention_period         = local.db_common.backup_retention_period
  publicly_accessible             = false
  multi_az                        = false
  auto_minor_version_upgrade      = true
  deletion_protection             = false # 실습 스택 — 운영에 쓸 때는 true
  skip_final_snapshot             = true
  enabled_cloudwatch_logs_exports = ["slowquery"]
  tags                            = { Name = "${local.p}-shop-db", Role = "target" }
}

resource "aws_db_instance" "verify" {
  identifier                  = "${local.p}-order-db"
  engine                      = local.db_common.engine
  engine_version              = local.db_common.engine_version
  instance_class              = local.db_common.instance_class
  allocated_storage           = local.db_common.allocated_storage
  storage_type                = local.db_common.storage_type
  storage_encrypted           = local.db_common.storage_encrypted
  db_subnet_group_name        = local.db_common.db_subnet_group_name
  parameter_group_name        = local.db_common.parameter_group_name
  vpc_security_group_ids      = local.db_common.vpc_security_group_ids
  username                    = local.db_common.username
  manage_master_user_password = true
  backup_retention_period     = 0 # 검증 DB 는 언제든 다시 만들 수 있다
  publicly_accessible         = false
  multi_az                    = false
  auto_minor_version_upgrade  = true
  deletion_protection         = false
  skip_final_snapshot         = true
  tags                        = { Name = "${local.p}-order-db", Role = "verify" }
}
