variable "region" {
  description = "배포 리전. 기본은 서울(ap-northeast-2) — Bedrock 은 global 추론 프로필로 호출한다."
  type        = string
  default     = "ap-northeast-2"
}

variable "name_prefix" {
  description = "모든 리소스 이름 앞에 붙는 접두어"
  type        = string
  default     = "slowq"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}$", var.name_prefix))
    error_message = "소문자 · 숫자 · 하이픈, 2~21자."
  }
}

variable "vpc_cidr" {
  description = "VPC CIDR (/16 권장). 퍼블릭 2개 · 프라이빗 2개 서브넷을 /20 으로 나눈다."
  type        = string
  default     = "10.40.0.0/16"
}

variable "enable_nat" {
  description = "NAT 게이트웨이 사용 여부. false 면 Secrets Manager · Bedrock 런타임 등은 VPC 엔드포인트로 쓰고, Jira · Slack 실제 전송은 할 수 없다."
  type        = bool
  default     = false
}

variable "interface_endpoints" {
  description = "NAT 를 끈 경우 만들 인터페이스 엔드포인트 (서비스 이름 끝부분). Lambda 로그는 엔드포인트가 필요 없다."
  type        = list(string)
  default     = ["secretsmanager", "bedrock-runtime"]
}

variable "db_instance_class" {
  description = "RDS 인스턴스 클래스 (대상 · 검증 공통)"
  type        = string
  default     = "db.t4g.micro"
}

variable "db_engine_version" {
  description = "RDS MySQL 엔진 버전 (8.0 계열)"
  type        = string
  default     = "8.0"
}

variable "db_allocated_storage" {
  description = "RDS 스토리지(GB). 샘플 데이터(주문 200만 행)와 검증용 인덱스에 20GB 면 충분하다."
  type        = number
  default     = 20
}

variable "bedrock_model_id" {
  description = "Bedrock 모델 ID 또는 추론 프로필 ID. 서울 리전은 global. 접두어 프로필을 쓴다."
  type        = string
  default     = "global.anthropic.claude-sonnet-4-6"
}

variable "schedule_cron" {
  description = "일일 파이프라인 실행 시각 (EventBridge Scheduler cron, schedule_timezone 기준). 기본 매일 00:10 — 어제 하루치를 처리."
  type        = string
  default     = "cron(10 0 * * ? *)"
}

variable "schedule_timezone" {
  description = "스케줄 · 날짜 계산 기준 시간대"
  type        = string
  default     = "Asia/Seoul"
}

variable "schedule_enabled" {
  description = "일일 스케줄 활성화 여부. 처음에는 수동 실행으로 확인한 뒤 켜는 것을 권장."
  type        = bool
  default     = false
}

variable "report_weekday" {
  description = "주간 리포트를 만드는 log_date 요일 (0=월 ... 6=일)"
  type        = number
  default     = 6
}

variable "enable_workload" {
  description = "샘플 DB 에 느린 쿼리를 주기적으로 실행하는 부하 스케줄 (실습 · 데모용)"
  type        = bool
  default     = false
}

variable "workload_schedule" {
  description = "부하 스케줄 식 (enable_workload=true 일 때)"
  type        = string
  default     = "rate(3 hours)"
}

variable "rules" {
  description = "검출 · 발행 규칙 (skeleton config 의 [rules] 와 같음)"
  type = object({
    min_sec         = number
    min_q           = number
    worse_ratio     = number
    spike_ratio     = number
    spike_min_total = number
    top_n           = number
  })
  default = {
    min_sec         = 0.5
    min_q           = 30
    worse_ratio     = 2.0
    spike_ratio     = 2.0
    spike_min_total = 1.0
    top_n           = 10
  }
}

variable "analyze_max" {
  description = "하루에 AI 분석할 티켓 상한 (Bedrock 비용 상한)"
  type        = number
  default     = 5
}

variable "alert_email" {
  description = "파이프라인 실패 알림을 받을 이메일 (비우면 구독 없음 — SNS 토픽만 만든다)"
  type        = string
  default     = ""
}

variable "publish_dry_run" {
  description = "true 면 Jira · Slack 로 보내지 않고 본문만 로그에 남긴다. 실제 전송은 false + 자격 증명 + NAT 가 모두 필요."
  type        = bool
  default     = true
}

variable "jira" {
  description = "Jira 설정 (선택). api_token 은 Secrets Manager 에만 저장된다."
  type = object({
    base_url    = string
    email       = string
    api_token   = string
    project_key = string
    issue_type  = optional(string, "Task")
    api_version = optional(string, "3")
  })
  default   = null
  sensitive = true
}

variable "slack_bot_token" {
  description = "Slack 봇 토큰 (선택, chat.postMessage). 채널은 CMDB 의 slack_channel."
  type        = string
  default     = ""
  sensitive   = true
}

variable "slack_webhook_url" {
  description = "Slack 수신 웹훅 주소 (선택, 봇 토큰이 없을 때 사용)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "grafana_allowed_cidrs" {
  description = "Grafana(3000/tcp) 에 접속을 허용할 CIDR 목록. 비우면 인터넷에서 열지 않고 SSM 포트 포워딩으로만 접속한다."
  type        = list(string)
  default     = []
}

variable "grafana_instance_type" {
  description = "Grafana EC2 인스턴스 타입 (arm64)"
  type        = string
  default     = "t4g.small"
}

variable "log_retention_days" {
  description = "CloudWatch Logs 보관 기간"
  type        = number
  default     = 14
}
