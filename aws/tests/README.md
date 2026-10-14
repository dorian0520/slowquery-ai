# aws/tests — Lambda 핸들러 단위 테스트

AWS 버전의 Lambda 코드를 **AWS · DB · Bedrock · 인터넷 없이** 가짜 객체로 돌려 보는 테스트입니다. 배포하지 않고도 "안전장치가 제대로 걸려 있나" 를 확인할 수 있습니다.

## 파일

| 파일 | 무엇을 확인하나 |
|---|---|
| `conftest.py` | 공통 준비 — `lambda/` 와 `skeleton/` 을 import 경로에 넣고, 가짜 DB 커서 등을 제공 |
| `test_analyze.py` | Bedrock 도구 호출 루프 · 엄격한 JSON 파싱 (형식이 어긋나면 `FORMAT_ERROR`, 예외 없이 사람 검토로) |
| `test_guards.py` | AI 가 넘긴 SQL 은 SELECT 한 문장만 실행 · 거부하면 DB 에 아무것도 보내지 않음 |
| `test_verify.py` | 검증 DB 에 `ADD INDEX` 한 절만 만들고 무슨 일이 있어도 되돌림 · 이미 있는 인덱스 이름은 실행 안 함 |
| `test_publish.py` | 기본 dry-run · 비밀이 있을 때만 실제 전송 · 토큰이 로그에 남지 않음 |
| `test_steps.py` | 수집 격리 · 검출 압축 · 첨부 · 리포트 · 변경 계획 · 초기화 계정 권한(`*.*` 없음) · 부하 |
| `test_static.py` | 상태 머신 정의 · 결정적 패키징 · AWS 저장소 스키마가 skeleton 스키마와 대시보드 열을 모두 포함 |

## 준비물

- Python 3.12 이상, `pytest` (`pip install pytest`)
- AWS 자격 증명은 **필요 없습니다** (테스트가 AWS 를 부르지 않음)

## 따라 하기

1. **`aws` 폴더에서** 실행합니다.

   ```bash
   cd aws
   python3 -m pytest -q tests
   ```

   실패 없이 모두 통과하는지 확인합니다. 테스트 수와 소스별 실행 범위는 [SOURCE_REVIEW.md](../SOURCE_REVIEW.md)에 기록합니다.

2. **한 파일만 · 한 테스트만** 돌리려면:

   ```bash
   python3 -m pytest -q tests/test_verify.py
   python3 -m pytest -q tests/test_verify.py -k existing_index   # 이름에 existing_index 가 들어간 테스트만
   ```

3. 배포 전 전체 정적 검증(Terraform · ASL · 셸 문법 포함)은 [scripts/README.md](../scripts/README.md) 의 `scripts/validate.sh` 가 이 테스트까지 함께 돌립니다.

## 자주 막히는 곳

| 증상 | 원인 · 해결 |
|---|---|
| `No module named pytest` | `python3 -m pip install pytest` |
| `ModuleNotFoundError: No module named 'slowq'` · `'slowq_aws'` | `aws` 폴더 밖에서 `tests` 경로를 잘못 줬거나 `skeleton/` 폴더가 없는 상태입니다. 저장소를 통째로 받은 뒤 `aws` 에서 실행 |
| `No module named 'pymysql'` | `python3 -m pip install -r lambda/requirements.txt` |
| 테스트 수가 기록과 다르다 | 코드를 고쳤거나 테스트가 추가된 경우입니다. `failed` 가 0 이면 괜찮습니다 |

## 다음 단계

- 빌드 · 정적 검증: [scripts/README.md](../scripts/README.md)
- Lambda 코드 안내: [lambda/README.md](../lambda/README.md)
- 전체 순서도: [docs/GETTING_STARTED.md](../../docs/GETTING_STARTED.md)

## 확장 검사

- `test_review_regressions.py`: 과거 리포트 기간, Slack 단독 실패, UTF-8 크기, 도구 총량, 연결 정리, 되돌리기 경고의 수정 전 실패 → 수정 후 통과.
- `test_handler_contracts.py`: 모든 주요 핸들러 경계, 초기화 권한 분리·시간 부족, 잘못된 입력, TLS·마스킹, 발행 기록 순서.
- `test_state_paths.py`: 실제 ASL의 데이터 전달·주간/비주간·각 단계 실패·SNS 실패 분기. AWS 시간·재시도·IAM을 에뮬레이션하지 않습니다.
- `test_grafana_provisioning.py`: 실제 렌더러의 특수문자 비밀번호·CA·설정 파일.
- `test_preflight.py`: 정확한 두 RDS ARN 및 삭제 거부·누락 컨텍스트 처리.

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m coverage run --branch --source=lambda/slowq_aws -m pytest -q tests
python3 -m coverage report -m
```

테스트의 네트워크 연결은 자동 차단합니다. 통과가 실제 Jira/Slack 전달·DB 강제 종료 복구·장기 운영 검증을 뜻하지 않습니다.
