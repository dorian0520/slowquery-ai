-- 슬로우 쿼리 운영 저장소 (섹션 4·6·7·8)
CREATE DATABASE IF NOT EXISTS dba;
USE dba;

-- 수집 원본: performance_schema digest 누적값 스냅숏
CREATE TABLE digest_snapshot (
  snap_at           DATETIME     NOT NULL,
  cluster           VARCHAR(30)  NOT NULL,
  digest            CHAR(64)     NOT NULL,
  schema_name       VARCHAR(64)  NOT NULL DEFAULT '',
  digest_text       TEXT         NULL,
  count_star        BIGINT       NOT NULL,
  sum_timer_wait    BIGINT       NOT NULL,   -- 피코초
  max_timer_wait    BIGINT       NOT NULL,
  sum_rows_examined BIGINT       NOT NULL,
  PRIMARY KEY (snap_at, cluster, schema_name, digest)   -- 같은 지문도 스키마별로 따로 집계된다
);

-- 일자별 집계: 대시보드가 읽는 테이블
CREATE TABLE slow_digest_daily (
  log_date        DATE         NOT NULL,
  cluster         VARCHAR(30)  NOT NULL,
  qhash           CHAR(32)     NOT NULL,     -- digest 앞 32자리
  schema_name     VARCHAR(64)  NULL,
  query_text      TEXT         NULL,         -- 리터럴이 ? 로 바뀐 정규화 쿼리
  exec_cnt        BIGINT       NOT NULL,
  total_sec       DOUBLE       NOT NULL,     -- 총 부하
  avg_sec         DOUBLE       NOT NULL,
  max_sec         DOUBLE       NOT NULL,
  rows_examined   BIGINT       NOT NULL,
  PRIMARY KEY (log_date, cluster, qhash),
  KEY ix_qhash (qhash, log_date)
);

-- 튜닝 티켓 (섹션 6)
CREATE TABLE tuning_ticket (
  ticket_id        INT AUTO_INCREMENT PRIMARY KEY,
  cluster          VARCHAR(30)  NOT NULL,
  qhash            CHAR(32)     NOT NULL,
  title            VARCHAR(200) NOT NULL,
  status           ENUM('OPEN','IN_PROGRESS','RESOLVED','REOPENED') NOT NULL DEFAULT 'OPEN',
  owner            VARCHAR(50)  NULL,
  baseline_avg_sec DOUBLE       NOT NULL,
  after_avg_sec    DOUBLE       NULL,
  recommendation   TEXT         NULL,
  verified         TINYINT      NOT NULL DEFAULT 0,
  created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  resolved_at      DATETIME     NULL,
  UNIQUE KEY uk_target (cluster, qhash)      -- 같은 쿼리 지문은 티켓 하나
);

-- 티켓 이력 (섹션 7: 추적)
CREATE TABLE ticket_event (
  id         BIGINT AUTO_INCREMENT PRIMARY KEY,
  ticket_id  INT NOT NULL,
  at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  event      VARCHAR(30) NOT NULL,
  note       VARCHAR(500) NULL,
  KEY ix_ticket (ticket_id, at)
);

-- CMDB: DB 자산 목록과 서비스·담당자 매핑 (섹션 4-1 — 수집 대상·티켓 담당자·대시보드 필터의 기준)
CREATE TABLE cmdb_cluster (
  cluster       VARCHAR(30) PRIMARY KEY,
  engine        VARCHAR(30) NOT NULL,          -- 예: MySQL 8.0, Aurora MySQL 3
  realm         VARCHAR(20) NOT NULL,          -- 예: prod / stage
  tag           VARCHAR(30) NOT NULL,          -- 업무 분류 (주문, 상품 등)
  service       VARCHAR(50) NOT NULL,          -- 이 DB를 쓰는 서비스
  owner_team    VARCHAR(50) NOT NULL,          -- 티켓을 받을 팀
  owner         VARCHAR(50) NOT NULL,          -- 기본 담당자
  slack_channel VARCHAR(50) NULL,              -- 알림 채널
  collect       TINYINT     NOT NULL DEFAULT 1 -- 수집 대상 여부
);
CREATE TABLE cmdb_instance (
  instance  VARCHAR(50) PRIMARY KEY,
  cluster   VARCHAR(30) NOT NULL,
  role      ENUM('writer','reader') NOT NULL,
  class     VARCHAR(30) NOT NULL,              -- 사양 (예: r6g.xlarge)
  KEY ix_cluster (cluster)
);
INSERT INTO cmdb_cluster VALUES
 ('shop-db',  'MySQL 8.0', 'prod', '주문',  'order-api', '주문개발팀', 'dev-kim', '#order-db-alert', 1),
 ('order-db', 'MySQL 8.0', 'prod', '정산',  'settle-api', '정산개발팀', 'dev-lee', '#settle-db-alert', 1);
INSERT INTO cmdb_instance VALUES
 ('shop-db-1',  'shop-db',  'writer', 'lab.local'),
 ('order-db-1', 'order-db', 'writer', 'lab.local');

-- 계정: 수집용(대상은 읽기, dba 저장소 쓰기 포함 — 실습 편의), Grafana 조회용 (로컬 실습 전용 비밀번호)
CREATE USER IF NOT EXISTS 'lab_collector'@'%' IDENTIFIED BY 'lab-collector-pw';
GRANT SELECT ON performance_schema.* TO 'lab_collector'@'%';
GRANT SELECT, EXECUTE ON sys.* TO 'lab_collector'@'%';   -- sys 뷰 조회용 (4강)
GRANT SELECT, PROCESS ON *.* TO 'lab_collector'@'%';
GRANT INSERT, UPDATE, SELECT, DELETE ON dba.* TO 'lab_collector'@'%';
CREATE USER IF NOT EXISTS 'lab_grafana'@'%' IDENTIFIED BY 'lab-grafana-pw';
GRANT SELECT ON dba.* TO 'lab_grafana'@'%';

-- AI 분석용 계정 (섹션 5): EXPLAIN 을 위해 shop SELECT, 집계 조회만
CREATE USER IF NOT EXISTS 'lab_ai'@'%' IDENTIFIED BY 'lab-ai-pw';
GRANT SELECT ON shop.* TO 'lab_ai'@'%';
GRANT SELECT ON dba.slow_digest_daily TO 'lab_ai'@'%';
