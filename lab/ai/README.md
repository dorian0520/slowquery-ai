# lab/ai — Claude Code 로 원인 분석 · 실측 검증

느린 쿼리의 원인과 개선안을 **Claude Code 가 읽기 전용 도구만으로** 분석하고(`claude -p`), 그 개선안을 **검증 DB 에서 실제로 재 보는**(`verify.py`) 폴더입니다. 운영 DB 는 바꾸지 않습니다.

## 파일

| 파일 | 역할 | 언제 쓰나 |
|---|---|---|
| `CLAUDE.md` | 분석 규칙 7가지와 출력 형식(JSON 배열). `claude` 를 이 폴더에서 실행하면 자동으로 읽힘 | 규칙을 읽어 보거나 고칠 때 |
| `mcp.json` | MCP 서버 설정 — `../.venv/bin/python labdb_mcp.py` 를 띄움 | `claude -p … --mcp-config mcp.json` |
| `labdb_mcp.py` | 읽기 전용 MCP 서버 `labdb`. 도구 4개: `top_queries` · `table_info` · `explain`(SELECT 만) · `query_trend` | 직접 실행하지 않음 — Claude Code 가 띄움 |
| `verify.py` | AI 제안 중 `ADD INDEX` 한 절만 검증 DB(order-db 3307)에 만들어 전후 시간 · 결과 동일성 비교 후 **반드시 되돌림** | AI 분석 결과가 나온 뒤 |
| `run1.txt` · `run2.txt` · `run3.txt` | 강사가 같은 요청으로 세 번 돌린 AI 출력 (실행마다 결과가 다를 수 있다는 예) | 비교 · 연습용 (덮어쓰지 마세요) |
| `verify_run1.txt` | `run1.txt` 를 `verify.py` 로 검증한 출력 | `publish.py attach` 연습용 |

## 준비물

- [lab/README.md](../README.md) 1~2장 완료 (MySQL 두 대 · `lab/.venv` · simulate). `lab/requirements.txt` 의 `mcp` 패키지가 `.venv` 에 있어야 MCP 서버가 뜹니다.
- Claude Code 설치 후 터미널에서 `claude` 를 한 번 실행해 로그인.
- 시뮬레이션 표의 「마지막 날」 오른쪽 날짜 (아래 예에서는 `LAST`).

## 따라 하기

모든 명령은 **`lab/ai` 폴더**에서 칩니다(`CLAUDE.md` 와 `mcp.json` 의 상대 경로가 이 폴더 기준입니다).

1. **동봉 결과로 먼저 검증해 보기** — AI 호출 없이 바로 됩니다.

   ```bash
   cd lab/ai
   ../.venv/bin/python verify.py run1.txt
   ```

   ```
   [5e9245c3] 통과  ALTER TABLE orders ADD INDEX ix_orders_user_ordered (user_id, ordered_at)
       시간 261.5 ms → 0.15 ms (1785배) · 결과 동일 True
       전: -> Table scan on orders  (cost=201102 rows=1.99e+6) ...
       후: -> Index lookup on orders using ix_orders_user_ordered (user_id=1001) (reverse) ...
   [f54ce51c] 탈락  ALTER TABLE orders ADD INDEX ix_orders_ordered (ordered_at, order_id)
   ...
   ```

   ms 숫자는 PC 마다 다르고, 통과 · 탈락은 같아야 합니다.

2. **내 날짜로 AI 분석 실행** (몇 분 걸릴 수 있음)

   ```bash
   LAST=2026-10-13   # 시뮬레이션 표의 「마지막 날」 오른쪽 날짜
   claude -p "$LAST shop-db 슬로우 쿼리 상위를 분석해 줘" \
     --mcp-config mcp.json --strict-mcp-config --tools "" \
     --allowedTools mcp__labdb__top_queries mcp__labdb__table_info mcp__labdb__explain mcp__labdb__query_trend \
     --output-format text > run_my.txt < /dev/null
   ```

   `run_my.txt` 를 열어 `"qhash"` · `"cause"` · `"proposal"` 이 든 JSON 배열이 있으면 정상입니다(`run1.txt` 와 비슷한 모양).

3. **내 결과를 실측 검증**

   ```bash
   ../.venv/bin/python verify.py run_my.txt > verify_my.txt
   cat verify_my.txt
   ```

4. **티켓에 첨부** — `lab/scripts` 로 옮겨 실행합니다.

   ```bash
   cd ../scripts
   ../.venv/bin/python publish.py attach ../ai/run_my.txt ../ai/verify_my.txt --log-date $LAST
   ```

   `#1 [5e9245c3] 실측 통과` 같은 줄이 나오면 끝입니다. 다음은 [scripts/README.md](../scripts/README.md) 5단계(운영 반영 계획)입니다.

## 자주 막히는 곳

| 증상 | 원인 · 해결 |
|---|---|
| `AI 출력이 올바른 JSON 배열이 아닙니다 → 검증 중단` | AI 가 형식을 어겼습니다. 정상적인 안전장치입니다. 2단계를 다시 실행하거나 `run1.txt` 로 이어 갑니다 |
| `[xxxxxxxx] 건너뜀 — 테스트 쿼리 또는 DDL 없음` | `verify.py` 의 `TEST_SQL` 에는 실습 지문 3개만 있습니다. 그 밖의 지문 · 쿼리 재작성 제안은 자동 검증하지 않습니다 |
| `[xxxxxxxx] 건너뜀 — 되돌릴 수 없는 DDL: …` | `ADD INDEX` 한 절이 아닌 제안입니다. 사람이 검토합니다 |
| `run_my.txt` 가 비었거나 도구 오류 · MCP 서버가 안 뜸 | `lab/ai` 밖에서 실행했거나 `lab/.venv` 가 없습니다(`mcp.json` 이 `../.venv/bin/python` 을 씀). `cd lab/ai` 후 다시 |
| 검증이 중간에 끊겨 검증 DB 에 인덱스가 남음 | `lab` 에서 `.venv/bin/python scripts/sqlrun.py --port 3307 --keep-going < sql/reset.sql` |
| `run1.txt` 를 덮어썼다 | `git checkout -- lab/ai/run1.txt` 로 되돌립니다. 내 결과는 항상 `run_my.txt` 처럼 다른 이름으로 저장 |

## 다음 단계

- 첨부 뒤 운영 반영 · 다음 날 추적: [scripts/README.md](../scripts/README.md)
- 호출 옵션 · 도구 · 규칙의 상세: [docs/08-diagnosis.md](../../docs/08-diagnosis.md)
- 전체 순서도: [docs/GETTING_STARTED.md](../../docs/GETTING_STARTED.md)
