terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # 상태 파일에는 DB 계정 비밀번호(random_password)가 들어간다. 팀에서 쓸 때는 암호화된 원격 백엔드를 쓴다.
  # backend "s3" {
  #   bucket       = "<내 상태 버킷>"
  #   key          = "slowq/terraform.tfstate"
  #   region       = "ap-northeast-2"
  #   encrypt      = true
  #   use_lockfile = true
  # }
}
