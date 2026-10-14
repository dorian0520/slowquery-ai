# 전체 소스 검토·검증 기록

2026-10-14, 기반 커밋 `aed82bf4f6b4acebeb28b0b59e622d3e193c3622`. 공개 소스의 AWS 경로 전부와 공유 `skeleton/slowq`, 로컬 실습 코드·문서의 문법 및 회귀를 검토했습니다. 인프라 생성 성공만으로 애플리케이션 검증을 대신하지 않았습니다.

## 검증 결과

| 검사 | 결과 | 의미 |
|---|---|---|
| AWS 핸들러·공통·도구·ASL·빌드·권한 사전 검사 | 115개 통과 | 실제 네트워크 차단, DB/API 대역을 통한 기능·오류 경계 검사 |
| 공유 스켈레톤 단위 테스트 | 34개 통과 | 차이 집계·검출·마스킹·상태 전이·검증 판정 |
| 로컬 실습 단위 테스트 | 18개 통과 | 변경 계획·리포트·DDL·simulate CLI 회귀 |
| 별도 DB 통합 테스트 | 7개 미실행 | lab 2개·skeleton 5개. 이번 단계에서는 기존 로컬 DB를 사용하지 않음 |
| AWS Lambda Python 분기 포함 실행 범위 | 92% | coverage 7.16.2, AWS+스켈레톤 단위 148개 실행 기준. 모든 장애의 검증을 뜻하지 않음 |
| 전체 저장소 문법·문서 링크 | 통과 | Python AST·JSON·bash -n·Git 추적 및 새 파일의 로컬 문서 링크 |
| Terraform fmt/validate | 통과 | 계정 제한·네트워크·IAM·RDS·Lambda·스케줄·모니터링·Grafana 구성 |
| AWS 상태 머신 정의 검증 API | OK, 진단 0건 | 수정된 ASL의 AWS 서비스 구문 검증. 생성·실행은 하지 않음 |
| Lambda/ARM64 레이어 빌드 | 통과 | Python 3.12 패키지·공유 로직·SQL·CA 포함, 압축 무결성 확인 |

## 함수와 연결 계약

| 소스 | 검사한 동작 |
|---|---|
| `init_db.py` | target/verify 분리·최소 권한 계정·재실행·부분 적재·두 번째 적재 시간 부족·잘못된 only/reset 입력 |
| `workload.py` | 지정 쿼리 선택·횟수·시간 부족 중단·읽기 전용 연결 정리 |
| `collect.py` + 공유 collect | 기준 스냅숏·차이/리셋 판정·클러스터 실패 격리·전체 실패 알림 경로 |
| `detect.py` + 공유 detect | 4종 규칙·후보 압축·UTF-8 바이트 상한·생략 건수 |
| `issue_tickets.py` + 공유 tickets | 발행 제한·CMDB·중복·분석 후보 입력 계약 |
| `analyze.py` / `tools.py` / prompt | 형식 오류·qhash·근거 도구·SELECT 제한·마스킹·호출 상한·연결 오류 |
| `verify.py` / `guards.py` + 공유 verify | 되돌릴 수 있는 DDL·기존 인덱스 보호·실측 결과·예외 시 되돌리기·연결 정리 |
| `attach.py` | 성공/형식 오류/검증 오류 첨부·verified 값·되돌리기 경고 보존 |
| `track.py` + 공유 tickets | 0.5/0.8 히스테리시스·실행 없음 보류·해결/재발 반환 계약 |
| `publish.py` | dry-run·Jira v2/v3·Slack·자격 증명 마스킹·단독 실패·Jira 성공 기록 순서 |
| `report.py` | 주간 집계·과거 상태·지정 날짜 기간·기간 경계·HTML 이스케이프·S3 경로 |
| `apply_plan.py` | 검증 통과 조건·중복 인덱스·온라인 DDL/되돌리기 계획·운영 DDL 미실행 |
| `common.py` | 환경 변수·JSON 직렬화·비밀 조회/캐시·DB TLS·CA 누락 거부 |
| `daily.asl.json` | 단계 JSONPath·주간/비주간·티켓별 오류·핵심 단계 실패·Publish/SNS 실패 후 분기 |
| 빌드/패키징·SQL·Grafana | ZIP 결정성·레이어 타깃·핸들러 포함·SQL 열 호환·실제 provisioning 렌더러 |

## 발견해 수정한 문제

1. **과거 리포트 누락:** 현재 날짜의 최근 60일을 읽던 조건을 요청한 end/days 기간으로 변경했습니다.
2. **Slack 단독 실패의 완료 오기록:** 전송 오류는 미발행으로 남기고 오류를 반환합니다. Jira 성공은 Slack 호출 전에 기록합니다.
3. **한글 상태 크기:** 문자 수만 제한하던 hits를 직렬화된 UTF-8 80KiB로 제한합니다. 생략 수를 알려 줍니다.
4. **도구 호출 총량:** 여러 toolUse가 한 응답에 오면 턴 상한만으로 제한되지 않던 문제에 총 16회 제한을 추가했습니다.
5. **두 번째 DB 연결 실패:** 분석용 첫 연결이 남지 않도록 정리 범위를 보완했습니다.
6. **되돌리기 경고 유실:** 티켓에 보호 장치 개입을 남기고 verified 자동 승인을 막습니다.
7. **TLS 약화:** CA가 없는 정상 빌드는 중단하고 연결도 거부합니다.
8. **초기화 입력 오해:** `reset_shop:"false"`가 참으로 해석되던 위험을 제거하고 only 오타를 거부합니다.
9. **모델로 보내는 추가 값:** 도구의 쿼리·DDL 문자열을 마스킹하고 원시 DB 오류 값을 보내지 않습니다.
10. **실행 간 검증 간섭:** Map뿐 아니라 verify Lambda의 예약 동시 실행도 1로 제한합니다. 일일 실행 전체를 겹쳐 돌리지 않는 제약은 유지합니다.
11. **SNS 실패 분기:** 알림 실패가 주간 보고를 막거나 원래 실패 경로를 바꾸지 않도록 Catch를 추가했습니다.
12. **설정·문서 불일치:** 분석 상한이 일일 예산 제한이라는 설명, Lambda StatusCode만의 성공 판정, 예전 정적 검증 전용 설명을 고쳤습니다. 요일/분석 후보 변수의 범위를 검증합니다.

첫 6개는 수정 전에 모두 실패하는 회귀 사례를 확인한 뒤 수정 후 통과했습니다. 앞선 실제 AWS 실행에서 발견한 Grafana·VPC·MySQL·IAM·되돌리기 확인 오류의 수정은 [LIVE_VALIDATION.md](LIVE_VALIDATION.md)에 있습니다.

## 실제 실행과 최신 수정의 구분

이전 독립 AWS 스택에서 RDS 합성 주문 각 200만 행, 실제 Bedrock 분석, 검증 인덱스 추가/제거, 해결·재발, 중복 0건, 계획 executed=false, Grafana 인증/TLS/SQL 8개를 확인했습니다.

이번 추가 수정은 로컬 기능 검사·구성 검사·ZIP 검사와 AWS 정의 검증을 완료했습니다. **최신 수정본 전체를 AWS에 재배포해 같은 시나리오를 반복한 기록은 아닙니다.** 자원 재생성은 현재 삭제 권한 대기를 해결한 뒤 진행해야 합니다. Jira·Slack 실제 발송은 하지 않았습니다.

## 남은 검증과 운영 제약

- 합성 검증 RDS 2대 및 연결 자원이 삭제 권한 예외 대기 중입니다. 제거 완료가 아닙니다.
- 강제 Lambda 종료·DB 단절 시 인덱스 정리, 백업 복구 SLA, Secret 회전, 대량 데이터·장기 운영, 전체 브라우저 UI, 기존 DB 이식은 별도 실습에서 확인해야 합니다.
- 수집 스냅숏·일일 집계·티켓 이벤트 전체의 원자적 복구와 실행 전체의 분산 잠금은 구현하지 않았습니다. 동시/겹친 일일 실행은 지원 범위 밖입니다.
- Jira 생성과 DB 저장은 원자적이지 않습니다. Slack 실패 뒤 Jira 재발행은 막지만 장애·동시 실행·모호한 API 응답에 대한 exactly-once 보장은 아닙니다.
- 데이터 마스킹은 SQL 리터럴에 대한 보완이며 모든 이름·메타데이터·개인정보 제거를 보장하지 않습니다.
- SQL 파일은 전체 목록·스키마 열 호환 및 이전 AWS 초기화 실행으로 검사했습니다. 모든 SQL 사례를 MySQL에서 재실행한 기록은 아닙니다. 로컬 CLI·MCP의 실제 운영 실행도 이 단위 검사 범위에 포함하지 않습니다.

## 최소 사양 후속 변경

사용자 요청에 따라 Lambda 전부 128MB, Grafana t4g.micro·CPU standard, 분석 후보 1개, 로그 1일, 합성 DB 자동 백업 0일로 낮췄습니다. RDS는 이미 db.t4g.micro·gp3 20GiB·Single-AZ, Grafana EBS는 8GiB입니다. 예시 파일의 자동 부하도 false로 맞췄습니다. 구성·단위 검사는 다시 수행하지만 기존 실제 실행 결과는 이 최소 사양의 성능 증거가 아닙니다. 삭제 권한 대기 중인 자원에 apply하지 않았습니다.

## 다시 검사하기

저장소 루트에서:

```bash
python3 -m pip install -r aws/requirements-dev.txt
PYTHON=python3 bash aws/scripts/validate.sh
python3 -m pytest -q aws/tests skeleton/tests/test_unit.py
(cd lab && LAB_IT=0 python3 -m unittest discover -s tests)
```

빌드·삭제 권한 점검·실제 실행·잔존 확인은 [OPERATIONS.md](OPERATIONS.md)를 따릅니다.

참고: [AWS 입출력 크기 제한](https://docs.aws.amazon.com/step-functions/latest/dg/service-quotas.html), [오류 처리](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html), [Lambda VPC ENI](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc.html).
