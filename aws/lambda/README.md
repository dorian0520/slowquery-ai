# aws/lambda — Lambda 핸들러 코드

AWS 버전의 각 단계(수집 · 검출 · 티켓 · AI 분석 · 실측 검증 · 첨부 · 추적 · 발행 · 리포트 …)를 실행하는 **Lambda 함수 코드**입니다. 판단 로직은 `skeleton/slowq` 를 그대로 가져다 쓰고, 이 폴더에는 AWS 와 이어 주는 부분만 있습니다.

## 파일

| 파일 | 역할 | 언제 쓰나 (Lambda 이름) |
|---|---|---|
| `requirements.txt` | 레이어에 넣을 의존성 (`pymysql` · `cryptography`, lab · skeleton 과 같은 버전) | `scripts/build.sh` 가 읽음 |
| `slowq_aws/common.py` | 환경 변수 · Secrets Manager 에서 비밀 읽기 · TLS 접속 · `log_date` 결정(없으면 어제) | 모든 함수가 씀 |
| `slowq_aws/init_db.py` | 샘플 데이터(`lab/mysql/init/01_shop.sql`) · 저장소 스키마 · 최소 권한 계정 6개 · CMDB 2행. 다시 실행해도 안전 | `slowq-init-db` (처음 한 번) |
| `slowq_aws/workload.py` | `lab/scripts/workload.py` 와 같은 부하 쿼리 | `slowq-workload` (선택 스케줄) |
| `slowq_aws/collect.py` | CMDB 의 `collect=1` 클러스터 수집 → `slowq.collect` | `slowq-collect` |
| `slowq_aws/detect.py` | 검출 규칙 → `slowq.detect` | `slowq-detect` |
| `slowq_aws/issue_tickets.py` | 티켓 발행(`slowq.tickets.issue`) + AI 분석 후보 상위 `analyze_max` 개 | `slowq-issue-tickets` |
| `slowq_aws/analyze.py` | Bedrock Converse API 로 도구를 쓰며 분석, 엄격한 JSON 파싱 | `slowq-analyze` |
| `slowq_aws/prompt.md` | 분석 규칙 (lab 의 `ai/CLAUDE.md` 에 해당) | `analyze` 가 읽음 |
| `slowq_aws/tools.py` | AI 근거 도구 4개 (`top_queries` · `table_info` · `explain` · `query_trend`, 읽기 전용) | `analyze` 가 씀 |
| `slowq_aws/guards.py` | AI 가 넘긴 SQL 을 SELECT 한 문장만 통과 · 실행 계획 마스킹 | `analyze` · `tools` 가 씀 |
| `slowq_aws/verify.py` | 검증 DB 에서 `ADD INDEX` 한 절만 만들고 측정 후 **반드시 되돌림** | `slowq-verify` |
| `slowq_aws/attach.py` | 분석 · 검증 결과를 `tuning_ticket.recommendation` 에 기록 | `slowq-attach` |
| `slowq_aws/track.py` | 해결 · 재발 판정 → `slowq.tickets.track` | `slowq-track` |
| `slowq_aws/publish.py` | Jira · Slack 발행 (기본 dry-run, 토큰은 로그에서 가림) | `slowq-publish` |
| `slowq_aws/report.py` | 주간 리포트 → S3 `reports/<날짜>/weekly.md · .html` | `slowq-report` (주 1회) |
| `slowq_aws/apply_plan.py` | 운영 반영 **계획서만** S3 `plans/ticket-<번호>.md` 에 (DDL 실행 없음) | `slowq-apply-plan` (수동) |
| `slowq_aws/__init__.py` | 패키지 표시 | — |

함수 이름의 `slowq-` 는 Terraform 변수 `name_prefix` 기본값입니다.

## 준비물

- 코드를 읽거나 테스트만 할 때: Python 3.12 이상, `pytest`
- 실제로 돌릴 때: [terraform/README.md](../terraform/README.md) 로 배포가 끝난 상태 + AWS CLI

이 폴더의 파일은 직접 실행하지 않습니다. `scripts/build.sh` 가 `slowq_aws/` 와 `skeleton/slowq/` 를 묶어 `build/function.zip` 을 만들고, Terraform 이 그것을 12개 함수에 올립니다.

## 따라 하기

1. **로컬에서 테스트로 동작 확인** — `aws` 폴더에서 (AWS · DB 없이 가짜로 돌림):

   ```bash
   cd aws
   python3 -m pytest -q tests
   ```

   끝에 실패 없이 테스트가 통과하면 정상입니다 ([tests/README.md](../tests/README.md)).

2. **코드를 고쳤다면 다시 빌드 → 배포**

   ```bash
   cd aws
   scripts/build.sh                      # 마지막에 function.zip · layer.zip 해시 두 줄
   cd terraform && terraform apply       # 바뀐 zip 해시 때문에 Lambda 만 바뀌는 계획이 나옴
   ```

3. **배포된 함수 하나를 직접 불러 보기** — 예: 처음 한 번 하는 `init-db` (수 분)

   ```bash
   aws lambda invoke --function-name slowq-init-db --cli-read-timeout 910 \
     --payload '{}' --cli-binary-format raw-in-base64-out /dev/stdout
   ```

   응답 메타데이터에 `FunctionError`가 없고 결과 JSON에 target·verify 초기화 완료가 나오는지 확인합니다. `StatusCode: 200`만으로 함수 성공을 판정하지 않습니다. 두 번째 실행부터는 `skip (이미 있음)` 이 나옵니다.

4. **로그 보기**

   ```bash
   aws logs tail /aws/lambda/slowq-collect --since 1h
   ```

## 자주 막히는 곳

| 증상 | 원인 · 해결 |
|---|---|
| `init-db` 결과에 `시간 부족 — payload {"only": "verify"} 로 다시 실행하세요` | 15분 제한에 걸렸습니다. 안내대로 `--payload '{"only": "verify"}'` 로 한 번 더 |
| `init-db` 가 `덜 만들어져 있습니다 … {"reset_shop": true}` 오류 | 샘플 적재가 중간에 끊긴 상태. `--payload '{"reset_shop": true}'` 로 다시 (샘플 스키마만 지우고 새로 만듦) |
| `Read timeout on endpoint URL` | CLI 기본 대기 시간이 짧습니다. `--cli-read-timeout 910` 을 붙였는지 확인 |
| `Invalid base64` | `--cli-binary-format raw-in-base64-out` 이 빠졌습니다 |
| 분석 결과가 `FORMAT_ERROR` | AI 출력 JSON 형식이 어긋난 것으로, 그 티켓만 「사람 검토」로 넘어가는 정상 안전장치입니다 |

## 다음 단계

- 함수들이 어떤 순서로 불리는지: [statemachine/README.md](../statemachine/README.md)
- lab · skeleton · aws 단계 대응표: [aws/README.md](../README.md) 7장
- 전체 순서도: [docs/GETTING_STARTED.md](../../docs/GETTING_STARTED.md)

## 입력·출력과 실패 처리 보완

- `init-db`: `only`는 `target`/`verify`, `reset_shop`은 JSON boolean만 받습니다. `"false"` 문자열은 초기화 요청으로 해석하지 않습니다.
- `detect`: 한글을 포함한 UTF-8 JSON 크기를 계산해 hits를 최대 80KiB로 제한합니다. `count`는 전체 검출 수, `truncated`는 상태에서 생략한 수입니다. 전체 데이터는 DB에서 조회합니다.
- `analyze`: 최대 8턴·총 16도구 호출. 사용자 쿼리·도구 쿼리·DDL 기본 문자열을 마스킹하고 원시 DB 오류를 모델에 보내지 않습니다. 마스킹은 임의의 개인정보 제거를 보장하지 않습니다.
- `verify`: 공유 검증 DB를 위해 예약 동시 실행 수를 1로 설정합니다. 다른 실행의 호출은 throttling/재시도를 거칠 수 있습니다. 되돌리기 확인 오류 또는 보호 장치 개입은 사람 검토 대상입니다.
- `report`: 요청한 날짜와 days(1~366)의 실제 기간을 읽습니다. 현재 날짜에서 오래 지난 리포트도 보관 데이터가 있으면 재계산할 수 있습니다.
- `publish`: Slack만 사용할 때 전송 실패는 미발행으로 남깁니다. Jira 성공 이벤트는 Slack 호출 전에 저장합니다. 외부 API 성공과 DB 기록은 원자적이지 않아 exactly-once 보장이 아닙니다.
- DB 인증서 묶음이 없는 패키지는 연결을 거부합니다. 정상 빌드를 다시 수행하세요.

전체 검증 내역과 운영 한계: [SOURCE_REVIEW.md](../SOURCE_REVIEW.md), [OPERATIONS.md](../OPERATIONS.md).
