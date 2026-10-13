# 문서

슬로우 쿼리를 매일 **수집 → 검출 → 티켓 → AI 분석 → 실측 검증 → 반영 → 추적 → 리포트** 하는 이 저장소의 구조와 동작을, 실제 코드 줄을 근거로 설명합니다. 모든 링크는 저장소 안의 파일 · 줄을 가리킵니다.

## 목차

| 문서 | 한 줄 요약 |
|---|---|
| [00. 흐름도](00-flow.md) | 전체 아키텍처 · 하루 배치 순서 · 티켓 상태 머신 · 저장소 테이블 관계 · lab 과 skeleton 대응 |
| [01. 데이터베이스 설정](01-database-setup.md) | MySQL 8.0 두 대(3306 · 3307), my.cnf · native.sh 설정, 계정과 권한, 확인 방법 |
| [02. 샘플 데이터 생성](02-sample-data.md) | `shop` 스키마(회원 20만 · 상품 2만 · 주문 200만)의 생성 식과 분포, CMDB 시드 |
| [03. Grafana 구성](03-grafana.md) | 컨테이너 · native 기동, 데이터 소스 · 대시보드 provisioning, 익명 Viewer |
| [04. 모니터링 대시보드 구성](04-dashboard.md) | 변수 9개 · 패널 8개의 SQL 과 용도, 공통 필터, JSON 재생성, 매일 보는 순서 |
| [05. 슬로우 쿼리 발생](05-slow-query-generation.md) | 부하 쿼리 7종과 느린 이유, 14일 시나리오, N+1, 강의 실험 SQL |
| [06. 수집](06-collection.md) | performance_schema digest 스냅숏, 제외 스키마, 기준 스냅숏 · 재시작 처리, 스켈레톤 차이 |
| [07. 집계](07-aggregation.md) | 스냅숏 차이 → 일자 집계, 검출 규칙 4종의 SQL 조건, 마스킹 |
| [08. 진단](08-diagnosis.md) | Claude Code 호출 옵션, 분석 규칙, 읽기 전용 MCP 도구 4개, 실측 검증, 결과 첨부 |
| [09. 티켓 발행](09-ticket.md) | 발행 기준 · 담당자 매핑 · 중복 방지 · 하루 상한, Jira · Slack 본문(dry-run) |
| [10. 성능 추적 관리 자동화](10-tracking-automation.md) | 해결 · 재발 판정, 온라인 DDL 반영과 사전 점검, 주간 리포트, 매일 운영 런북 |

## 읽는 순서

1. **전체 그림**: [00 흐름도](00-flow.md)
2. **환경 띄우기**: [01](01-database-setup.md) → [02](02-sample-data.md) → [03](03-grafana.md) → [05 의 simulate](05-slow-query-generation.md) 실행 → [04 대시보드](04-dashboard.md) 로 결과 보기
3. **자동화 단계별**: [06 수집](06-collection.md) → [07 집계](07-aggregation.md) → [09 티켓](09-ticket.md) → [08 진단](08-diagnosis.md) → [10 추적 · 반영](10-tracking-automation.md)
   (티켓이 먼저 있어야 진단 결과를 붙일 수 있으므로 09 를 08 보다 먼저 읽어도 좋습니다.)
4. **내 환경에 붙이기**: 각 문서의 skeleton 비교 부분과 [skeleton/README.md](../skeleton/README.md)

## 알아 둘 점

- `lab/` 은 실습 환경(클러스터 `shop-db` · `order-db`, 서비스 스키마 `shop`, 저장소 `dba`)에 맞춘 예제이고, `skeleton/` 이 내 환경용 최소 프로그램입니다.
- Jira · Slack 은 **본문을 출력하는 dry-run 만** 구현돼 있습니다. 실제 전송 코드는 없습니다.
- 계정 · 비밀번호는 모두 로컬 실습 전용 값입니다.
