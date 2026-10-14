# VPC: 퍼블릭 2 (Grafana · NAT) + 프라이빗 2 (RDS · Lambda).
# NAT 를 끄면(기본) Lambda 는 VPC 엔드포인트로만 AWS 서비스에 나간다: S3(게이트웨이, 무료) + 인터페이스 엔드포인트.

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true # 인터페이스 엔드포인트의 private DNS 에 필요
  tags                 = { Name = "${local.p}-vpc" }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${local.p}-igw" }
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 4, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = false
  tags                    = { Name = "${local.p}-public-${count.index}" }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.this.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, count.index + 8)
  availability_zone = local.azs[count.index]
  tags              = { Name = "${local.p}-private-${count.index}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
  tags = { Name = "${local.p}-public" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_eip" "nat" {
  count  = var.enable_nat ? 1 : 0
  domain = "vpc"
  tags   = { Name = "${local.p}-nat" }
}

resource "aws_nat_gateway" "this" {
  count         = var.enable_nat ? 1 : 0
  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public[0].id
  tags          = { Name = "${local.p}-nat" }
  depends_on    = [aws_internet_gateway.this]
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${local.p}-private" }
}

resource "aws_route" "private_nat" {
  count                  = var.enable_nat ? 1 : 0
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[0].id
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# S3 게이트웨이 엔드포인트 (무료) — 리포트 · 계획서 업로드
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${local.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]
  tags              = { Name = "${local.p}-s3" }
}

# 인터페이스 엔드포인트 — NAT 를 끈 경우에만. 비용을 줄이려 첫 번째 프라이빗 서브넷(AZ 하나)에만 둔다.
resource "aws_vpc_endpoint" "interface" {
  for_each            = var.enable_nat ? toset([]) : toset(var.interface_endpoints)
  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${local.region}.${each.key}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [aws_subnet.private[0].id]
  security_group_ids  = [aws_security_group.endpoints.id]
  private_dns_enabled = true
  tags                = { Name = "${local.p}-${each.key}" }
}

# 보안 그룹 — 서로를 참조하는 규칙은 별도 리소스로 둔다 (순환 참조 방지)
resource "aws_security_group" "lambda" {
  # Lambda needs its execution-role permissions while retiring the last VPC ENI.
  # Keep policies (and their roles) until this security group can be deleted.
  depends_on = [aws_iam_role_policy.fn]

  name        = "${local.p}-lambda"
  description = "slowq Lambda functions"
  vpc_id      = aws_vpc.this.id
  tags        = { Name = "${local.p}-lambda" }
}

resource "aws_security_group" "rds" {
  name        = "${local.p}-rds"
  description = "slowq RDS MySQL (target and verify)"
  vpc_id      = aws_vpc.this.id
  tags        = { Name = "${local.p}-rds" }
}

resource "aws_security_group" "endpoints" {
  name        = "${local.p}-endpoints"
  description = "Interface VPC endpoints"
  vpc_id      = aws_vpc.this.id
  tags        = { Name = "${local.p}-endpoints" }
}

resource "aws_vpc_security_group_egress_rule" "lambda_to_rds" {
  security_group_id            = aws_security_group.lambda.id
  referenced_security_group_id = aws_security_group.rds.id
  ip_protocol                  = "tcp"
  from_port                    = 3306
  to_port                      = 3306
  description                  = "MySQL"
}

resource "aws_vpc_security_group_egress_rule" "lambda_https" {
  security_group_id = aws_security_group.lambda.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "HTTPS to VPC endpoints, S3 gateway, and (with NAT) Jira/Slack"
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_lambda" {
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = aws_security_group.lambda.id
  ip_protocol                  = "tcp"
  from_port                    = 3306
  to_port                      = 3306
  description                  = "MySQL from Lambda"
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_grafana" {
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = aws_security_group.grafana.id
  ip_protocol                  = "tcp"
  from_port                    = 3306
  to_port                      = 3306
  description                  = "MySQL from Grafana (read-only account)"
}

resource "aws_vpc_security_group_ingress_rule" "endpoints_from_lambda" {
  security_group_id            = aws_security_group.endpoints.id
  referenced_security_group_id = aws_security_group.lambda.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  description                  = "HTTPS from Lambda"
}

# Secrets Manager private DNS also applies to the public Grafana subnet.
# Grafana must reach the interface endpoint rather than the public internet address.
resource "aws_vpc_security_group_ingress_rule" "endpoints_grafana" {
  count                        = var.enable_nat ? 0 : 1
  security_group_id            = aws_security_group.endpoints.id
  referenced_security_group_id = aws_security_group.grafana.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  description                  = "Grafana to Secrets Manager private endpoint"
}
