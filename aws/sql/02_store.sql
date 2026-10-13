-- 슬로우 쿼리 자동화 저장소 스키마 (AWS 버전). init_db Lambda 가 대상 DB(shop-db)의 `dba` 에 적용한다.
-- 기준은 skeleton/schema.sql 이고, Grafana 대시보드(lab/grafana)가 읽는 열을 함께 둔다.
--   - slow_digest_daily.max_sec  : 대시보드 순위 패널용 (skeleton 수집기는 채우지 않으므로 NULL)
--   - tuning_ticket.verified     : 실측 검증 통과 여부 (attach 단계가 기록)
--   - tuning_ticket.updated_at   : 대시보드 티켓 패널 정렬용 (자동 갱신)
-- 모든 문장은 IF NOT EXISTS 라 여러 번 실행해도 안전하다.
CREATE DATABASE IF NOT EXISTS dba;
USE dba;

CREATE TABLE IF NOT EXISTS cmdb_cluster (
  cluster       VARCHAR(30) PRIMARY KEY,
  host          VARCHAR(255) NOT NULL,
  port          INT NOT NULL DEFAULT 3306,
  realm         VARCHAR(20) NOT NULL,
  tag           VARCHAR(30) NOT NULL,
  owner         VARCHAR(50) NOT NULL,
  owner_team    VARCHAR(50) NOT NULL,
  slack_channel VARCHAR(80) NOT NULL,
  collect       TINYINT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS digest_snapshot (
  snap_at           DATETIME(6) NOT NULL,
  cluster           VARCHAR(30) NOT NULL,
  digest            CHAR(64) NOT NULL,
  schema_name       VARCHAR(64) NOT NULL,
  digest_text       TEXT,
  count_star        BIGINT NOT NULL,
  sum_timer_wait    BIGINT NOT NULL,
  sum_rows_examined BIGINT NOT NULL,
  first_seen        DATETIME(6),
  PRIMARY KEY (snap_at, cluster, schema_name, digest)
);

CREATE TABLE IF NOT EXISTS slow_digest_daily (
  log_date      DATE NOT NULL,
  cluster       VARCHAR(30) NOT NULL,
  qhash         CHAR(32) NOT NULL,
  query_text    TEXT,
  exec_cnt      BIGINT NOT NULL,
  total_sec     DOUBLE NOT NULL,
  avg_sec       DOUBLE NOT NULL,
  max_sec       DOUBLE NULL,
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
  baseline_avg_sec DOUBLE NOT NULL,
  after_avg_sec    DOUBLE,
  recommendation   TEXT,
  verified         TINYINT NOT NULL DEFAULT 0,
  created_at       DATETIME NOT NULL,
  updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  resolved_at      DATETIME,
  UNIQUE KEY uk_target (cluster, qhash)
);

CREATE TABLE IF NOT EXISTS ticket_event (
  id        BIGINT AUTO_INCREMENT PRIMARY KEY,
  ticket_id INT NOT NULL,
  at        DATETIME NOT NULL,
  event     VARCHAR(30) NOT NULL,
  note      VARCHAR(500),
  KEY ix_ticket (ticket_id, at)
);
