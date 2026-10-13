# slowquery-ai — AI가 매일 잡아내는 슬로우 쿼리

인프런 강의 **「AI가 매일 잡아내는 슬로우 쿼리 — Claude Code로 만드는 MySQL 튜닝 자동화 시스템」** 의 실습 코드와 워킹 스켈레톤입니다.

느린 쿼리를 매일 자동으로 **수집 → 검출 → 티켓 발행 → AI 분석 → 실측 검증 → 운영 반영 → 해결 · 재발 추적 → 리포트** 하는 시스템을 로컬에서 그대로 돌려 볼 수 있습니다.

## 구성

| 필요한 것 | 위치 |
|---|---|
| 환경 구성 (MySQL 8.0 두 대 + Grafana) | `lab/docker-compose.yml` (Docker) · `lab/native.sh` (Homebrew) |
| 샘플 데이터베이스 · 테이블 · 데이터 생성 (주문 200만 행 등) | `lab/mysql/init/01_shop.sql` |
| 자동화 저장소 스키마 (CMDB · 스냅숏 · 일자 집계 · 티켓 · 이벤트) · 계정 | `lab/mysql/init/02_dba.sql` |
| 부하 재현 · 14일 운영 상황 시뮬레이션 | `lab/scripts/workload.py` · `simulate.py` · `next_day.py` |
| 데이터베이스 모니터링 (Grafana 대시보드 · 데이터 소스) | `lab/grafana/` |
| 슬로우 쿼리 자동 추출 (performance_schema 스냅숏 차이) | `lab/scripts/collector.py` |
| 검출 규칙 (기준 초과 · 신규 · 악화 · 급증) | `lab/scripts/detect.py` |
| 진단 (Claude Code + 읽기 전용 MCP 서버) · 실측 검증 | `lab/ai/` (`CLAUDE.md` · `labdb_mcp.py` · `mcp.json` · `verify.py`) |
| 티켓 발행 (중복 방지 · CMDB 담당자) · 해결 · 재발 추적 | `lab/scripts/tickets.py` |
| Jira · Slack 발행 본문 (dry-run) | `lab/scripts/publish.py` |
| 운영 반영 (변경 계획 · 온라인 DDL · 되돌리기) | `lab/scripts/apply_fix.py` |
| 결과 보고서 (주간 리포트) | `lab/scripts/report.py` |
| 강의 7~15강 실습 SQL | `lab/sql/` |
| 내 환경에 옮겨 심는 워킹 스켈레톤 (`python -m slowq daily`) | `skeleton/` |
| 테스트 | `lab/tests/` (20개) · `skeleton/tests/` (39개) |

## 빠른 시작

```bash
cd lab
docker compose up -d                       # 또는 ./native.sh up (Homebrew)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/simulate.py       # 14일 운영 상황 재현 (수 분)
```

Grafana: http://localhost:3000 (로그인 없이 보기). 자세한 순서는 [`lab/README.md`](lab/README.md), 내 환경에 붙이는 법은 [`skeleton/README.md`](skeleton/README.md) 를 보세요.

## AWS 버전 (Terraform · Lambda · Step Functions)

같은 파이프라인을 AWS 에 올리는 IaC 버전은 [`aws/README.md`](aws/README.md) 에 있습니다 — RDS MySQL 두 대 · Lambda(수집 · 검출 · 티켓 · Bedrock 진단 · 실측 검증 · 추적 · 발행 · 리포트) · Step Functions 일일 배치 · EventBridge 스케줄 · EC2 Grafana. 운영 DDL 은 자동 실행하지 않고 변경 계획만 만듭니다. 정적 검증(`terraform validate`, 테스트 73개)까지 마쳤고, 실제 배포는 직접 하며 비용이 발생합니다.

## 문서

단계별 흐름도와 상세 설명(설정 · 데이터 · 대시보드 · 수집 · 집계 · 진단 · 티켓 · 추적)은 [`docs/README.md`](docs/README.md) 에 있습니다.

## 주의

- `lab/` 의 계정 · 비밀번호는 **로컬 실습 전용**입니다. 운영 환경에 그대로 쓰지 마세요.
- `lab/` 코드는 실습 환경(`shop-db` · `order-db`, 스키마 `shop`, 저장소 `dba`)에 맞춘 예제입니다. 운영에는 `skeleton/` 을 기준으로 붙이고, 옮겨 쓰는 파일은 `skeleton/README.md` 의 표를 참고하세요.
- 샘플 데이터는 모두 합성 데이터입니다.

## 라이선스

[MIT](LICENSE) — 회사 · 개인 환경에 자유롭게 옮겨 쓰고 고칠 수 있습니다. 운영에 붙이기 전에는 검증 DB 에서 먼저 확인하세요.
