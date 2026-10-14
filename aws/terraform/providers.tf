provider "aws" {
  region              = var.region
  allowed_account_ids = var.expected_account_id == null ? null : [var.expected_account_id]

  default_tags {
    tags = {
      Project   = var.name_prefix
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}
data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name
  partition  = data.aws_partition.current.partition
  azs        = slice(data.aws_availability_zones.available.names, 0, 2)
  p          = var.name_prefix

  # 빌드 산출물 (scripts/build.sh 가 만든다)
  build_dir    = "${path.module}/../build"
  function_zip = "${local.build_dir}/function.zip"
  layer_zip    = "${local.build_dir}/layer.zip"
}
