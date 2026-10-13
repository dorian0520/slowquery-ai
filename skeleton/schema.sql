-- 슬로우 쿼리 자동화 저장소 스키마 (워킹 스켈레톤). 저장소 DB 하나에 만든다.
CREATE TABLE IF NOT EXISTS cmdb_cluster (          -- 자동화의 기준: 수집 대상 · 담당자 · 알림 채널
  cluster       VARCHAR(30) PRIMARY KEY,
  host          VARCHAR(255) NOT NULL,
  port          INT NOT NULL DEFAULT 3306,
  realm         VARCHAR(20) NOT NULL,              -- prod / stage
  tag           VARCHAR(30) NOT NULL,              -- 업무 분류
  owner         VARCHAR(50) NOT NULL,
  owner_team    VARCHAR(50) NOT NULL,
  slack_channel VARCHAR(80) NOT NULL,
  collect       TINYINT NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS digest_snapshot (       -- 누적값 원본 (보관 짧게)
  snap_at           DATETIME(6) NOT NULL,
  cluster           VARCHAR(30) NOT NULL,
  digest            CHAR(64) NOT NULL,
  schema_name       VARCHAR(64) NOT NULL,
  digest_text       TEXT,
  count_star        BIGINT NOT NULL,
  sum_timer_wait    BIGINT NOT NULL,
  sum_rows_examined BIGINT NOT NULL,
  first_seen        DATETIME(6),                   -- 재시작 · TRUNCATE 감지
  PRIMARY KEY (snap_at, cluster, schema_name, digest)   -- 같은 지문도 스키마별로 따로
);
CREATE TABLE IF NOT EXISTS slow_digest_daily (     -- 일자 × 클러스터 × 지문 (보관 길게)
  log_date      DATE NOT NULL,
  cluster       VARCHAR(30) NOT NULL,
  qhash         CHAR(32) NOT NULL,
  query_text    TEXT,
  exec_cnt      BIGINT NOT NULL,
  total_sec     DOUBLE NOT NULL,
  avg_sec       DOUBLE NOT NULL,
  rows_examined BIGINT NOT NULL,
  PRIMARY KEY (log_date, cluster, qhash),
  KEY ix_qhash (cluster, qhash, log_date)
);
CREATE TABLE IF NOT EXISTS tuning_ticket (
  ticket_id        INT AUTO_INCREMENT PRIMARY KEY,
  cluster          VARCHAR(30) NOT NULL,
  qhash            CHAR(32) NOT NULL,
  title            VARCHAR(200) NOT NULL,
  status           ENUM('OPEN','IN_PROGRESS','RESOLVED','REOPENED') NOT NULL DEFAULT 'OPEN',
  owner            VARCHAR(50),
  baseline_avg_sec DOUBLE NOT NULL,                -- 발행 시점 기준값 (해결 판정 기준)
  after_avg_sec    DOUBLE,
  recommendation   TEXT,                           -- AI 분석 + 실측 검증 결과 (JSON)
  created_at       DATETIME NOT NULL,
  resolved_at      DATETIME,
  UNIQUE KEY uk_target (cluster, qhash)            -- 같은 지문은 티켓 하나
);
CREATE TABLE IF NOT EXISTS ticket_event (
  id        BIGINT AUTO_INCREMENT PRIMARY KEY,
  ticket_id INT NOT NULL,
  at        DATETIME NOT NULL,
  event     VARCHAR(30) NOT NULL,
  note      VARCHAR(500),
  KEY ix_ticket (ticket_id, at)
);
