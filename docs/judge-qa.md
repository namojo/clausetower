# ClauseTower 심사 예상 질문

발표자와 팀원이 심사 전에 읽는 문서다. 심사장의 까다로운 질문에 30초 안에 근거와 함께 답하도록 심사 기준 4개([README](../README.md) 11절)별로 질문 28개를 모았다.
숫자의 출처는 2026-11-02 게이트 결과(`_workspace/04_qa_gates_r2.json`의 `facts`)와 추적 측정 파일(`eval/results/`)이다. 실제 모델 숫자는 2회차(`eval/results/real/`) 기준이고, 1회차(`eval/results/real_prev/`)를 쓸 때는 회차를 밝힌다. 보안 답은 2026-11-02 코드 수정 후의 상태다. `_workspace/`는 팀 PC의 게이트 출력이라 저장소에 없다. `facts.*`는 그 파일의 키이며, 같은 숫자는 [README 8절](../README.md) 검증 절차의 명령이나 추적 파일(`eval/results/robustness.md`, `eval/results/extraction_*.json`, `eval/results/real*/run.log`)로 다시 확인할 수 있다.

함께 보는 문서: [README](../README.md)(숫자 기준 6절), [평가 방법](evaluation.md)(지표 정의·재현 명령), [아키텍처](architecture.md), [설치·실행 가이드](setup-guide.md), [3분 데모 대본](demo-script.md)(짧은 답), [2일 구현 계획](hackathon-plan.md), [기획서](proposal.md).

---

## 0. 쓰는 법

- 질문마다 **말로 하는 답**(2~3문장), **근거**(숫자와 경로), **보여 줄 화면**을 둔다. 답은 그대로 읽어도 30초 안에 끝난다.
- 재지 않은 것은 "재지 않았습니다", 조사로 확인하지 못한 것은 "찾지 못했습니다"라고 답한다. 아직 답이 없는 질문은 6절에 모았다.
- 화면은 세 가지를 미리 열어 둔다(명령은 [설치·실행 가이드](setup-guide.md)).

| 화면 | 여는 방법 | LLM 호출 |
| --- | --- | --- |
| 정답지 대시보드 | `python -m clausetower demo --llm mock` → `out/demo/dashboard.html` | 없음 |
| 실제 모델 대시보드 | `python -m clausetower demo --from-reports eval/results/real --out out/real` → `out/real/dashboard.html` | 없음(저장된 보고서) |
| 웹 데모 | https://namojo.github.io/clausetower/ | 계약서를 올릴 때만 |

## 1. 먼저 외울 숫자

| 항목 | 값 | 출처 |
| --- | --- | --- |
| 정책 비교(mock, 정답지) | 태풍 12,834,000원 → 2,996,500원(76.7%), 항만 적체 4,770,000원 → 1,842,500원(61.4%), WMS 장애 18,640,000원 → 7,765,500원(58.3%) | `facts.scenarios_mock` (측정) |
| 탐색 근사 최적(참고) | 태풍 2,921,000원, 항만 적체 1,222,500원, WMS 장애 6,930,500원 | 같은 곳 (측정) |
| 다중 시드 | 시드 30개 × 3종 90/90 승, 절감 평균 69.1%(태풍)·58.7%(항만)·62.4%(WMS), 최소 32.4% | `facts.robustness`, `eval/results/robustness.md` (측정) |
| 실제 모델 추출 정확도 | 2회차 95.3%(101/106), 1회차 96.2%(102/106) | `eval/results/extraction_*.json`, `eval/results/real_prev/extraction_*.json` (측정) |
| 면책 판단 필드 정확도(32필드) | 2회차 태풍 100%, 항만 적체 93.8% | `facts.real_model_scores` (측정) |
| 최종 적용 여부 정확도(고객 8곳) | 2회차 태풍 8/8, 항만 적체 6/8 | 같은 곳(`applies_accuracy` 1.0, 0.75) (측정) |
| 인용 원문 일치율(고객 8곳) | 2회차 100%(엄격 기준도 100%) | 같은 곳, `eval/run_eval.py` (측정) |
| 실제 모델 비용·시간 | 2회차 호출 24회, CLI 보고 비용 $2.06, 호출 시간 합계 283초, 병렬 4개로 실제 소요 약 101초 | `eval/results/real/run.log` (측정) |
| 시험·대조 | pytest 71 passed, 웹 엔진 대조 36/36, 패널 입력 75케이스 일치 | `facts.tests_passed`, `facts.engine_parity`, `tests/test_web.py` (측정) |

---

## 2. AI 활용 수준 (Q1~Q7)

### Q1. LLM은 정확히 무엇을 하고, 왜 돈 계산은 맡기지 않나요?

**말로 하는 답.** "LLM은 계약서를 읽어 조건을 구조화하고, 이번 사건이 면책 사유에 해당하는지 판단하는 두 가지만 합니다. 금액은 결정적 계산기가 내고, 최종 면책 적용 여부도 모델의 답이 아니라 네 조건의 논리곱으로 코드가 다시 만듭니다. 그래서 틀리면 어느 항목이 틀렸는지 추적되고, 사람이 그 항목만 뒤집을 수 있습니다."

**근거.**
- 읽기: `prompts/extract.md` → pydantic 스키마 `PenaltyTerms`(`src/clausetower/schemas.py`). 항목마다 조항 번호·원문 인용·확신도·해석이 갈리는 지점(`ambiguities`)을 받는다.
- 판단: `prompts/judge.md` → `has_clause`, `event_covered`, `notice_ok`, `conditions_met`. 최종 `applies`는 `src/clausetower/extract.py`의 `judge_from_text`가 `조항 있음 ∧ 사유 해당 ∧ 통지 충족 ∧ 조건 충족`으로 다시 만든다. 모델이 빠뜨린 조건은 미충족으로 본다(`tests/test_sim_and_agent.py::test_judge_missing_condition_key_fails_closed`).
- 계산: `src/clausetower/exposure.py`의 `compute_penalty`. 유예 → 단위 올림 → 요율·누진·정액 → 건별 상한 → 고객 합계 상한 순서로 금액과 계산 단계 문장을 낸다.

**보여 줄 화면.** 계약 상세 서랍의 판단 체크리스트(`docs/screenshots/typhoon_drawer.png`). 청람제약이 "대체 운송수단 확보 노력 입증" 조건에서 끊긴 것이 보인다.

### Q2. 정답지를 팀이 직접 썼는데 정확도를 믿을 수 있나요?

**말로 하는 답.** "그 한계는 맞습니다. 계약서와 정답지를 같은 팀이 썼기 때문에 이 정확도는 '팀이 의도한 해석과 얼마나 같은가'이고 독립 검증은 아닙니다. 대신 정답지와 항목별 채점 결과를 모두 저장소에 공개해 어느 항목이 갈렸는지 누구나 확인할 수 있고, 실제 계약서 블라인드 평가를 다음 목표로 둡니다."

**근거.**
- 정답지: `contracts/golden/*.yaml`(계약 8부, 106항목, 판단 32필드). 채점 코드: `eval/run_eval.py`의 `extraction`.
- 2회차에 틀린 5항목은 모두 면책 조항의 개수였다(`eval/results/extraction_typhoon.json`의 `rows`): 한빛전자 사유 7개(정답 8), 세움건설 조건 3개(정답 0), 바로유통 조건 1개(정답 0), 누리에너지 조건 2개(정답 0)와 사유 4개(정답 5). 요율·유예·상한·기준금액은 8부 모두 맞았다.
- 절감률(1절 첫 줄)은 정답지로 계산한 값이라 모델 정확도와 따로 선다. 태풍은 실제 모델이 읽은 조건으로 돌려도 총 배상금이 같다(`eval/results/real/report_typhoon.json`: 12,834,000원 → 2,996,500원).
- 한계와 다음 평가 계획: [평가 방법](evaluation.md), README 10절.

**보여 줄 화면.** 없음. 물으면 `eval/results/extraction_typhoon.json`을 연다.

### Q3. 실제 모델 정확도는 얼마나 되나요?

**말로 하는 답.** "Claude가 계약서 8부를 읽은 2회차 결과는 조건 106항목 중 101개, 95.3%가 정답지와 같았습니다. 면책 판단은 필드 단위로 태풍 100%, 항만 적체 93.8%이고, 고객 단위 최종 적용 여부로 보면 항만 적체는 8곳 중 6곳이 맞았습니다. 틀린 2곳은 모두 면책을 보류하는 쪽, 즉 배상금을 더 잡는 쪽으로 틀렸습니다."

**근거.** `claude-code` 모드, 모델 claude-opus-5-5(`eval/results/real/run.log`).

| 지표 | 1회차(`eval/results/real_prev/`) | 2회차(현재, `eval/results/real/`) |
| --- | --- | --- |
| 계약 조건 추출 정확도(106항목) | 96.2% (102/106) | 95.3% (101/106) |
| 면책 판단 필드 정확도(32필드) | 태풍 100%, 항만 적체 96.9% | 태풍 100%, 항만 적체 93.8% |
| 최종 적용 여부 정확도(고객 8곳) | 태풍 8/8, 항만 적체 7/8 | 태풍 8/8, 항만 적체 6/8 |
| 인용 원문 일치율(고객 8곳) | 100% | 100% |

- 필드 정확도는 고객 8곳 × 4필드(조항 유무, 사유 해당, 통지 충족, 최종 적용)를 센 값이고, 최종 적용 여부 정확도는 고객 단위다. 둘을 같은 이름으로 부르지 않는다. 정의는 [평가 방법](evaluation.md).
- 2회차 항만 적체에서 틀린 곳: 누리에너지(1회차에도 틀림), 세움건설("서면" 통지 여부가 사건 설명에 없어 조건 미충족으로 보류). 둘 다 정답은 면책 적용이다(`eval/results/extraction_port_congestion.json`).
- 이 점수는 프롬프트에 주입 방어 규칙을 넣기 전에 잰 값이다(Q24).

**보여 줄 화면.** 실제 모델 대시보드의 계약 케이스(`docs/screenshots/real/typhoon_board.png`). 카드 오른쪽 위 "읽기 N%"가 모델이 보고한 확신도다.

### Q4. LLM이 틀리면 어떻게 되나요?

**말로 하는 답.** "형식이 틀리면 한 번 재시도하고, 그래도 실패하면 그 결과를 쓰지 않고 대체한 횟수를 보고서와 화면에 드러냅니다. 내용이 틀리면 원문 인용 검사와 조건 결합에서 걸리고, 판단 이유와 미충족 조건이 카드에 그대로 나와 사람이 '사람 결정'으로 뒤집습니다. 실제로 틀린 2건은 면책을 보류한 쪽이라 배상금을 덜 잡지는 않았습니다."

**근거.**
- 형식 오류: `src/clausetower/llm.py`가 pydantic으로 검증하고 1회 재시도한다. 실패하면 파이프라인은 정답지로 대체하고 `Report.llm_fallbacks`에 횟수를 남긴다. 로컬 도우미는 응답에 `"fallback": true`를 붙이고, 웹은 그 결과로 고객을 추가하거나 판단을 바꾸지 않는다(`tests/test_server_and_openai.py::test_helper_marks_fallback_when_real_model_fails`, `tests/test_dashboard_and_cli.py::test_report_records_llm_fallbacks`). 2회차 실제 실행의 대체는 0회다(`run.log`의 `fallbacks=0`).
- 내용 오류: 인용 검사(Q5), 조건 결합과 빠진 조건의 미충족 처리(Q1).
- 금액 영향(측정): 태풍은 정답지와 총 배상금이 같다. 항만 적체는 판단 2건이 보수적으로 틀려 실제 모델 출처의 총 배상금이 기존 8,925,000원 → ClauseTower 3,213,500원(64.0%)이다. 정답지 출처는 4,770,000원 → 1,842,500원이다(`eval/results/real/report_port_congestion.json`, `facts.scenarios_mock.port_congestion`).

**보여 줄 화면.** 웹 데모 왼쪽 패널의 면책 판단(고객별 "자동 / 적용 / 미적용 + 이유"). 뒤집으면 카드에 "사람 결정"이 붙는다.

### Q5. 모델이 붙인 인용이 진짜 원문인지 어떻게 아나요?

**말로 하는 답.** "모델이 낸 인용을 코드가 계약서 원문과 대조합니다. 2회차 실제 보고서 2종에서 고객 8곳의 인용이 모두 원문에 있었고, 인용 조각 전체를 대조하는 엄격 기준으로도 100%였습니다. 웹에서 계약서를 올릴 때도 브라우저가 같은 엄격 규칙으로 검사해 맞지 않는 항목을 알려 줍니다."

**근거.**
- 지표 두 개를 구분한다(`eval/run_eval.py`). `citations_verbatim_rate`는 각 인용의 첫 조각 앞 20자가 원문에 있는지 본다(문서의 "인용 원문 일치율"). `citations_strict_rate`는 조각 전체가 원문에 있는지 본다(공백·줄바꿈 차이만 무시).
- 2회차 실제 보고서 2종은 두 지표 모두 1.0이다. 확인: `python eval/run_eval.py extraction eval/results/real/report_typhoon.json`(저장된 보고서 채점, LLM 호출 없음).
- 팀이 쓴 정답지 인용은 조항을 줄여 적어 엄격 기준에서 8곳 중 2곳(미래식품, 청람제약)이 맞지 않는다(mock 보고서 채점 0.75). 그래서 문서의 기존 지표는 앞 20자 기준을 유지했다.
- 웹 검사와 같은 규칙인지: 파이썬 규칙(`eval/run_eval.py`의 `quote_is_verbatim`)은 `tests/test_dashboard_and_cli.py::test_quote_check_rejects_tampered_tail_but_allows_line_breaks`가 확인한다. 웹 `src/clausetower/web/app.js`의 `verbatim`은 같은 분리·정규화 규칙으로 작성했지만 JS를 직접 대조하는 시험은 없다.

**보여 줄 화면.** 계약 상세 서랍의 전문 탭(`docs/screenshots/typhoon_drawer_text.png`). "원문에서 보기"를 누르면 인용 문장으로 건너뛴다.

### Q6. 계약서 안에 "앞의 규칙을 무시하라" 같은 문장을 심으면요? (프롬프트 주입)

**말로 하는 답.** "계약서 본문은 `<contract>` 태그 안의 데이터로만 넘기고, 그 안의 지시는 따르지 말고 기록하라고 프롬프트에 적었습니다. Claude Code 호출은 내장 도구와 사용자 MCP를 모두 끄고 임시 폴더에서 돌아서 주입이 파일이나 명령에 닿을 길이 없습니다. 주입으로 흔들 수 있는 것은 추출 값뿐인데, 금액은 코드가 계산하고 면책은 조건 결합으로 정해지며 모든 값에 원문 인용이 붙어 사람이 확인합니다."

**근거.**
- 프롬프트: `prompts/extract.md`, `prompts/judge.md`의 마지막 규칙. 본문 감싸기: `src/clausetower/extract.py`의 `contract_block`.
- 호출 옵션: `src/clausetower/llm.py`의 `claude_command`(`--tools ""`, `--strict-mcp-config`, `--disallowedTools`, `--no-session-persistence`, 임시 작업 폴더). 시험: `tests/test_llm_claude_code.py::test_claude_command_disables_tools_and_user_mcp`.
- 웹: 모델이 돌려준 값은 허용된 과금 방식·숫자·선택지만 받고, 이름 같은 문자열은 화면에 넣기 전에 이스케이프한다(`src/clausetower/web/app.js`의 `normalizeTerms`, `tests/test_web.py::test_action_board_promises_only_what_the_engine_delivers`).
- **아직 안 한 것.** 주입 문장을 심은 계약서로 평가한 적은 없다. 실제 모델 점수는 이 규칙을 넣기 전에 잰 값이다. `--tools ""`와 구조화 출력(`--json-schema`)이 함께 동작하는지는 과금 실행 1회(태풍 1종, 호출 16회, 2회차 기준 약 $1.78)로 확인해야 한다(6절). 깨지면 정답지 대체로 떨어지고 `fallback`·`llm_fallbacks`로 드러난다.

**보여 줄 화면.** 없음.

### Q7. 사내 LLM이나 다른 모델로 바꿀 수 있나요?

**말로 하는 답.** "LLM 호출은 `llm.py` 한 곳을 지나고 모드가 네 가지라, 사내 OpenAI 호환 게이트웨이는 `--llm openai`와 환경 변수로 붙습니다. 웹 데모도 사내·호환 엔드포인트를 직접 부르거나 로컬 도우미로 중계합니다. 다만 정확도는 Claude로만 쟀고, 다른 모델은 같은 채점 명령으로 다시 재야 합니다."

**근거.**

| 모드 | 무엇 | 설정 |
| --- | --- | --- |
| `mock` | 정답지 사용, 네트워크 없음 | – |
| `codex` | Codex CLI(`codex exec`). **기본 연결** | `CLAUSETOWER_CODEX_BIN`, `CLAUSETOWER_CODEX_MODEL`, `CLAUSETOWER_CODEX_TIMEOUT` |
| `claude-code` | Claude Code CLI(구독) | `CLAUSETOWER_CLAUDE_BIN`, `CLAUSETOWER_CLAUDE_TIMEOUT` |
| `anthropic` | Anthropic SDK | `ANTHROPIC_API_KEY` |
| `openai` | OpenAI 호환 chat/completions + 강제 tool call | `CLAUSETOWER_OPENAI_BASE_URL`, `CLAUSETOWER_OPENAI_API_KEY`, `CLAUSETOWER_MODEL` |

- `auto`(기본)는 Codex CLI → API 키 → 사내 엔드포인트 → claude CLI → mock 순으로 고른다. `--llm`을 생략했는데 실제 LLM이 골라지면 비용 경고를 낸다(`src/clausetower/cli.py`). 환경 변수 전체는 [설치·실행 가이드](setup-guide.md).
- 추적 중인 실제 모델 측정은 Codex 연결 도입 전 claude-opus-5-5 한 모델이다(`eval/results/real/run.log`). Codex로는 판단 1회·추출 1회만 확인했고 시나리오 전체는 다시 재지 않았다.

**보여 줄 화면.** 웹 데모 "실제 케이스 분석"의 연결 방식 선택(`docs/screenshots/web/web_live_helper.png`).

---

## 3. 문제 해결 방식 (Q8~Q14)

### Q8. 마감 임박 순으로 보내면 무엇이 문제인가요?

**말로 하는 답.** "교란 때 물어야 할 것은 '어느 화물이 급한가'가 아니라 '한 사이클 더 보류하면 어느 계약에서 얼마가 더 나오는가'입니다. 태풍에서 마감 1위인 세움건설 C05는 이미 지연돼 일 단위로 배상금이 잡혀 있어 한 사이클 보류해도 늘지 않으므로 14위로 내려가고, 마감 40위인 가온헬스케어 E06은 건당 정액 위약금 50만 원 때문에 2위로 올라옵니다. 대기 45건 중 32건의 순위가 3계단 이상 갈렸습니다."

**근거.**
- `facts.scenarios_mock.typhoon`: 순위 시점 +15.9시간, 대기 45건, 3계단 이상 변동 32건.
- `out/demo/report_typhoon.json`의 `ranking`(mock 데모가 만든다): C05 마감 1위 → 노출 14위(즉시 배차 시·보류 시 모두 219,000원, 배상 노출액 0원), E06 마감 40위 → 노출 2위(배상 노출액 500,000원), 노출 1위는 청람제약 H02(184,500원).
- 배상 노출액 정의: README 2절, [아키텍처](architecture.md).

**보여 줄 화면.** 배상 노출 순위 표(`docs/screenshots/typhoon_ranking.png`).

### Q9. 왜 배상 노출액을 시간으로 나누나요? 절대값 변형과 무엇이 다른가요?

**말로 하는 답.** "먼 노선 화물은 트럭을 오래 묶어 그동안 다른 화물이 기다리므로, 배상 노출액을 트럭 왕복 시간으로 나눠 '트럭 1시간당 막는 배상금'이 큰 화물부터 보냅니다. 기본 시나리오 3종에서는 나누지 않은 절대값 변형이 오히려 0.6~2.9% 낮았습니다. 그러나 시드 30개 평균으로는 시간당이 세 시나리오 모두 1.4~3.6% 낮아서 시간당을 기본으로 둡니다."

**근거.**
- 정의: `src/clausetower/sim.py`의 `_exposure_key`. 점수 = 배상 노출액 ÷ (2 × 노선 이동시간). 절대값 변형은 나누지 않는다.

| 시나리오 | 기본 시드: 시간당 / 절대값 | 시드 30개 평균: 시간당 / 절대값 |
| --- | ---: | ---: |
| 태풍 상륙 | 2,996,500 / 2,979,000 | 3,885,116 / 4,028,116 |
| 항만 적체 | 1,842,500 / 1,803,500 | 2,300,583 / 2,332,816 |
| 자사 WMS 장애 | 7,765,500 / 7,544,000 | 6,377,866 / 6,565,616 |

- 출처: `facts.scenarios_mock.*.policies`(기본 시드), `eval/results/robustness.md`(평균). WMS 장애의 정책별 최댓값(서로 다른 시드)은 시간당 7,765,500원(시드 23), 절대값 9,316,000원(시드 13)이다(`eval/results/robustness.md`의 최대 열, 시드 1~30 재실행으로 시드 확인). 같은 시드끼리 보면 시드 23은 시간당 7,765,500원 / 절대값 7,544,000원, 시드 13은 7,508,500원 / 9,316,000원이다.
- 한계: 고를 때 본 30개 시드로 그대로 보고했으므로 독립 검증이 아니다. 시드별 맞대결 승패는 집계하지 않았다. 차이가 작아 핵심 효과(기존 대비 58~77%)는 어느 변형이든 거의 같다.

**보여 줄 화면.** 정책 비교 차트(`docs/screenshots/typhoon_charts.png`). 정책 5개와 탐색 근사 최적(참고)이 나란히 있다.

### Q10. 탐색 근사 최적과는 얼마나 차이 나나요? 왜 탐색을 쓰지 않나요?

**말로 하는 답.** "탐색 근사 최적은 사건 전체를 미리 안 상태에서 배차 순서를 바꿔 가며 시뮬레이션을 반복해 찾은 사후 참고값이라, 사건이 진행 중인 현장에서는 쓸 수 없고 진짜 최적도 아닙니다. 단순 규칙인 배상 노출 순은 기존 대비 줄일 수 있는 금액 중 태풍 99.2%, WMS 장애 92.9%, 항만 적체 82.5%를 확보합니다. 항만 적체는 탐색보다 62만 원 높아 개선 여지가 가장 크다는 점도 그대로 공개합니다."

**근거.**

| 시나리오 | 기존 | ClauseTower | 탐색 근사 최적 | 차이 | 줄일 수 있는 몫 중 확보 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 태풍 상륙 | 12,834,000 | 2,996,500 | 2,921,000 | 75,500 | 99.2% |
| 항만 적체 | 4,770,000 | 1,842,500 | 1,222,500 | 620,000 | 82.5% |
| 자사 WMS 장애 | 18,640,000 | 7,765,500 | 6,930,500 | 835,000 | 92.9% |

- 출처: `facts.scenarios_mock`. "확보" = (기존 − ClauseTower) ÷ (기존 − 탐색).
- 탐색: `src/clausetower/sim.py`의 `search_best_order`(우선순위 순열의 지역 탐색, 재시작 12회, 교환 반복 최대 3회).
- 웹 데모는 기본 설정이면 파이썬이 찾은 순서를 그대로 돌려 위 표와 같은 값을 보인다. 패널 설정을 바꾸면 브라우저가 더 가벼운 탐색(재시작 6회, 교환 반복 2회)을 돌리므로 참고값이 문서 표와 다를 수 있다.

**보여 줄 화면.** 관제 요약(`docs/screenshots/typhoon_kpi.png`)과 정책 비교 차트.

### Q11. 시뮬레이터가 작은데 절감률이 의미 있나요?

**말로 하는 답.** "절감률 숫자는 이 모형(허브 1곳, 노선 8개, 트럭 8대, 화물 56건) 안의 값이라 실제 네트워크의 절감액으로 쓰면 안 됩니다. 이 모형이 보이는 것은 방향입니다. 화물 가액·노선·마감을 시드 30개로 바꿔도 90번 모두 기존보다 낮았고 가장 나쁜 경우도 32.4% 줄었습니다. 실제 규모는 TMS 배차 기록을 다시 돌려 재는 것이 다음 목표입니다."

**근거.**
- 모형 규모: README 4-2절, `src/clausetower/sim.py`의 `build_shipments`(세 시나리오 모두 트럭 8대, 화물 56건, 노선 8개).
- 다중 시드: `facts.robustness`, `eval/results/robustness.md`. 승률 30/30 × 3종, 동률 0. 절감 범위 태풍 49.6~82.1%, 항만 적체 32.4~83.5%, WMS 장애 41.7~72.2%.
- 없는 것: 교란 동시 발생, 부분 적재, 환적(README 10절).

**보여 줄 화면.** 없음. 물으면 `eval/results/robustness.md`를 연다.

### Q12. 결과가 갈리도록 계약을 일부러 설계했으니 당연한 결과 아닌가요?

**말로 하는 답.** "맞습니다. 마감 순서와 배상 순서가 갈리도록 고객 8곳의 조항 구조를 일부러 다르게 만들었고, README에도 그렇게 적었습니다. 다만 면책이 하나도 서지 않는 자사 WMS 장애에서도 유예·상한·요율 차이만으로 58.3%가 줄었습니다. 실제 고객사 계약의 분포에서 효과가 얼마나 되는지는 재지 않았습니다."

**근거.**
- README 4-1절 "조항 구조를 일부러 다르게 설계해"와 고객별 조항 표.
- WMS 장애: `facts.scenarios_mock.wms_outage.judgments_applies`가 8곳 모두 미적용, 절감 18,640,000원 → 7,765,500원(58.3%).
- 계약서 형태는 표준계약서와 실무 관행을 참고했다고 양식 답안 6번에 적었다([양식 답안](ax-hackathon-form.md)). 계약 구성에 대한 민감도 분석은 하지 않았다.

**보여 줄 화면.** WMS 장애 탭의 관제 요약(`docs/screenshots/wms_outage_kpi.png`).

### Q13. 지연 건수는 별로 줄지 않았는데요?

**말로 하는 답.** "맞습니다. 태풍에서 지연은 52건에서 43건으로 줄었을 뿐인데 배상금은 약 4분의 1이 됐습니다. 이 방식은 지연을 없애는 것이 아니라 어느 지연을 감수할지를 계약 기준으로 고르는 것입니다. 지연이 똑같이 43건인 고액 화물 순은 17,610,500원이라 지연 건수가 같아도 배상금은 약 5.9배 차이 납니다."

**근거.** `facts.scenarios_mock.*.policies`의 `late_count`와 `total_penalty_krw`.

| 시나리오 | 마감 임박 순(기존) | 고액 화물 순 | ClauseTower |
| --- | --- | --- | --- |
| 태풍 상륙 | 52건, 12,834,000원 | 43건, 17,610,500원 | 43건, 2,996,500원 |
| 항만 적체 | 41건, 4,770,000원 | 31건, 9,660,500원 | 34건, 1,842,500원 |
| 자사 WMS 장애 | 51건, 18,640,000원 | 47건, 20,681,500원 | 45건, 7,765,500원 |

**보여 줄 화면.** 배차 간트(`docs/screenshots/typhoon_gantt.png`). 빨간 테두리가 지연이다.

### Q14. 비교가 공정한가요? 기존 정책을 약하게 둔 것은 아닌가요?

**말로 하는 답.** "모든 정책은 같은 트럭, 같은 화물, 같은 결항과 노선 지연에서 돌고, 다른 것은 '트럭이 빌 때 무엇을 먼저 보내는가' 하나뿐입니다. 기존 관행인 마감 임박 순 외에 도착 순과 고액 화물 순도 함께 비교했고, 위쪽 기준으로 탐색 근사 최적까지 두었습니다. 기존 정책 중 가장 나은 것과 비교해도 세 시나리오 모두 ClauseTower가 낮습니다."

**근거.**
- 정책 정의: `src/clausetower/sim.py`의 `POLICIES`와 `run_policy`. 시나리오마다 같은 화물 목록(`build_shipments`)을 쓴다.
- 기존 정책 중 최저: 태풍 도착 순 11,732,000원, 항만 적체 도착 순 4,559,500원, WMS 장애 마감 임박 순 18,640,000원. ClauseTower는 각각 2,996,500원, 1,842,500원, 7,765,500원(`facts.scenarios_mock`).
- 기존 관행을 마감 임박 순으로 본 것은 팀의 가정이다. 현장 관행 조사는 하지 않았다.

**보여 줄 화면.** 정책 비교 차트(`docs/screenshots/typhoon_charts.png`).

---

## 4. 실제 업무 적용 가능성 (Q15~Q21)

### Q15. 기존 TMS나 CLM과 무엇이 다른가요?

**말로 하는 답.** "계약 관리 도구(CLM)는 조항을 찾아 주고, TMS 배차 엔진은 마감과 거리로 순서를 정합니다. ClauseTower는 그 사이에서 조항 구조를 사건별 배상 노출액으로 바꿔 배차 순서에 넣고, 그 돈의 근거를 조항 원문으로 보여 줍니다. 검색 9회로 조사했을 때 SLA 긴급도 배차와 배상금 조항 추출은 각각 있었지만 둘을 잇는 것, 특히 한국어 지체상금 맥락의 도구는 찾지 못했습니다."

**근거.** README 1-2절, 7절(찾은 것: SLA 긴급도를 가중치로 쓰는 현장서비스 배차, SLA 배상금을 비용 함수에 넣는 클라우드 스케줄링 연구, 배상금 조항 추출 특허, SLA 위반 예측 재배차 벤더 자료. 링크는 README 7절). "없다"는 증명할 수 없어 "찾지 못했다"로 답한다.

**보여 줄 화면.** 없음.

### Q16. 계약 해석의 책임은 누구에게 있나요?

**말로 하는 답.** "최종 책임은 사람에게 있습니다. 이 도구는 노출액과 그 근거 조항을 보여 주는 참모이고, 모든 판단에 조항 번호와 원문 인용, 그리고 모델이 해석이 갈린다고 적은 지점이 붙습니다. 운영자는 고객별 면책을 적용이나 미적용으로 뒤집고 이유를 남길 수 있고, 그 판단은 화면에 '사람 결정'으로 표시됩니다."

**근거.**
- README 10절 한계("계약 해석의 최종 책임은 사람에게 있다").
- 해석이 갈리는 지점: 추출 결과의 `ambiguities`. 예: 한빛전자 "'매 1일'이 역일인지 영업일인지 명시되어 있지 않다"(`eval/results/extraction_typhoon.json`의 `rows`).
- 사람 결정: `src/clausetower/web/app.js`(고객별 "자동 / 적용 / 미적용 + 이유", 카드에 "사람 결정: …"으로 표시).
- 실제 적용 시 법무 검수를 거친 정답지로 바꾸는 것은 목표다([양식 답안](ax-hackathon-form.md) 6번).

**보여 줄 화면.** 웹 데모 왼쪽 패널의 면책 판단 표와 카드의 "사람 결정" 표시.

### Q17. 실제 모델의 비용과 속도는 얼마인가요?

**말로 하는 답.** "2회차 실측으로 계약서 8부 추출과 시나리오 2종의 면책 판단에 호출 24회, CLI 보고 비용 $2.06이 들었습니다. 호출 시간 합계는 283초지만 4개를 병렬로 돌려 실제 소요는 약 101초였습니다. 계약 추출은 시나리오끼리 공유하므로 시나리오 하나를 더하면 판단 8회, 약 $0.28이 더 들고, 통지 시점이나 사실 관계가 바뀌면 LLM을 다시 부르지 않고 조건 결합만 다시 계산합니다."

**근거.** `eval/results/real/run.log`, `eval/results/real_prev/run.log`.

| 회차 | 호출 | CLI 보고 비용 | 호출 시간 합계 | 실제 소요(벽시계) | 토큰(입력 / 출력) |
| --- | --- | --- | --- | --- | --- |
| 1회차 | 24회(추출 8 + 판단 16) | $1.98 | 270초 | 약 85초(태풍 54초 + 항만 31초) | 437,324 / 26,070 |
| 2회차 | 24회(추출 8 + 판단 16) | $2.06 | 283초 | 약 101초(태풍 70초 + 항만 31초) | 459,771 / 28,740 |

- 2회차 누적 비용은 추출 8회와 태풍 판단 8회까지 $1.78, 항만 적체 판단 8회를 더해 $2.06이다(`run.log`의 시나리오별 줄). 시나리오당 추가 비용은 이 차이로 계산했다.
- 웹 데모의 로컬 도우미(구독 경로)로 예시 계약서 1부를 추출하는 데 22초가 걸렸다(README 3-8절, `docs/screenshots/web/web_live_helper_real.png`).
- `claude-code` 모드는 구독 경로라 실제 청구는 요금제에 따른다. 비용은 CLI가 보고한 값이다.

**보여 줄 화면.** 없음. 물으면 `eval/results/real/run.log`를 연다.

### Q18. 계약서는 민감 문서인데 보안은 어떻게 하나요?

**말로 하는 답.** "계약서 본문은 고른 LLM 엔드포인트 외에는 어디에도 보내지 않고, 사내 게이트웨이(`--llm openai`)를 쓰면 본문은 그 게이트웨이로만 갑니다. 웹 데모를 PC의 LLM에 잇는 로컬 도우미는 기본으로 이 PC(127.0.0.1)에만 열리고, 허용한 웹 출처의 JSON 요청만 받으며, 본문을 디스크나 로그에 남기지 않습니다. 브라우저에 넣은 키는 기본으로 그 탭에만 두고 탭을 닫으면 지워집니다."

**근거.** 데모 계약서는 전부 가상이다. 경로별 상태(코드 수정 후):

| 경로 | 본문이 가는 곳 | 보호 장치 |
| --- | --- | --- |
| `mock` | 없음(네트워크 없음) | – |
| `codex` | Codex CLI → OpenAI | 읽기 전용 샌드박스, 셸·앱·플러그인·웹 검색 끔, 빈 임시 폴더, 세션 기록 안 남김(`src/clausetower/llm.py`의 `codex_command`) |
| `claude-code` | Claude Code CLI → Anthropic | 내장 도구·사용자 MCP 끔, 임시 작업 폴더, 세션 저장 안 함(`src/clausetower/llm.py`의 `claude_command`) |
| `anthropic` / `openai` | Anthropic API / 사내·호환 엔드포인트 | 경고 로그에 본문·모델 출력을 싣지 않음(오류 종류·필드 위치·길이만) |
| 웹 직접 호출 | 브라우저 → 고른 엔드포인트 | 키·토큰은 기본 `sessionStorage`. "이 브라우저에 기억"을 켤 때만 `localStorage`(같은 출처 `namojo.github.io`의 다른 페이지와 공유). Anthropic 직접 호출은 `anthropic-dangerous-direct-browser-access` 헤더가 필요해 개인용 키를 권한다 |
| 로컬 도우미(`serve`) | 이 PC → 위 LLM 경로 | 아래 목록 |

- 로컬 도우미(`src/clausetower/server.py`):
  - 기본 바인딩은 `127.0.0.1`이다. 다른 주소에 두면 인증이 없다는 경고를 낸다.
  - 허용 출처 기본값은 `https://namojo.github.io`와 `http://localhost`·`127.0.0.1`·`[::1]`(포트 무관)이다. `--allow-origin`(여러 번 가능)이나 `CLAUSETOWER_ALLOWED_ORIGINS`(쉼표 구분)로 더한다.
  - 목록 밖 출처는 403으로 거절한다. 파일로 연 페이지의 `null` 출처도 기본으로는 거절한다.
  - POST는 `Content-Type: application/json`만 받고 나머지는 415로 거절한다. 동시 LLM 요청이 상한을 넘으면 429를 낸다.
  - 본문은 메모리에서만 다룬다. 요청 로그에는 메서드와 경로만, 오류 응답에는 예외 이름과 필드 위치만 남긴다.
- 시험: `tests/test_server_and_openai.py`의 `test_cors_rejects_unlisted_origin`, `test_post_requires_json_content_type`, `test_error_response_does_not_echo_input`, `test_bind_warning_only_for_non_loopback`, `test_concurrent_llm_requests_are_limited`. 웹의 외부 스크립트(mammoth)는 SRI 해시로 고정했다(`tests/test_web.py::test_external_scripts_are_pinned_with_sri`).
- **안 한 것.** 도우미 인증 토큰은 없다. LLM 제공자의 데이터 보관 정책은 회사 계약으로 정할 일이라 이 도구가 다루지 않는다.

**보여 줄 화면.** 없음. 물으면 `python -m clausetower serve --help`의 `--host`, `--allow-origin` 설명을 보인다.

### Q19. 실제 계약서(PDF, HWP, 수십 쪽)도 읽나요?

**말로 하는 답.** "지금은 txt·md·docx 파일과 붙여넣기만 됩니다. PDF(스캔본 OCR 포함)와 HWP 업로드, 긴 계약서에서 지체상금·면책 조항만 찾아내는 사전 분할은 다음 목표입니다. 데모 계약서 8부는 가상이고 한국어만 다뤘습니다."

**근거.** README 3-8절(업로드 형식), 10절(한계와 다음). docx는 브라우저에서 mammoth로 텍스트를 뽑는다(`scripts/build_site.py`).

**보여 줄 화면.** 웹 데모 "실제 케이스 분석"의 업로드(`docs/screenshots/web/web_live_upload.png`).

### Q20. 현장에 넣으려면 배차 엔진을 바꿔야 하나요?

**말로 하는 답.** "기존 배차 엔진은 그대로 두고, 우선순위 입력에 '배상 노출액(원/시간)' 열 하나를 넘기는 형태를 목표로 합니다. 지금 구현된 것은 그 값을 계산하는 엔진과 조치 보드, 대시보드, 웹 데모까지이고, TMS 연동 API와 사람의 승인 흐름은 아직 없습니다."

**근거.** README 10절 "다음(목표)", 11절. 확장 지점은 [아키텍처](architecture.md), 해커톤 2일 동안 할 일은 [2일 구현 계획](hackathon-plan.md).

**보여 줄 화면.** 없음.

### Q21. 조치 보드가 "통지하면 0원"이라고 하면 믿어도 되나요?

**말로 하는 답.** "조치 보드는 면책이 실제로 성립할 때만 금액을 약속하도록 고쳤습니다. 통지나 입증 자료를 가정해 조건 결합을 다시 돌려 보고, 다른 조건이 남아 있으면 '통지만으로는 면책 안 됨'이라고 적고 회피 가능 금액에서 뺍니다. 예를 들어 실제 모델이 읽은 세움건설 계약에는 통지 외 조건도 적혀 있어서, 기본 출처에서는 57만 원 면책을 약속하지 않습니다."

**근거.**
- `src/clausetower/web/render.js`, `src/clausetower/web/app.js`가 `CT.deriveJudgment`로 다시 결합한다. 시험: `tests/test_web.py::test_action_board_promises_only_what_the_engine_delivers`.
- 세움건설 태풍 배상금: 기존 909,000원, ClauseTower 570,000원(`facts.scenarios_mock.typhoon.per_customer_krw`). "12h 통지를 지켰다면 0원"은 정답지 출처에서만 성립한다. 실제 모델은 세움건설 면책 조건을 3개 적었다(정답 0개, `eval/results/extraction_typhoon.json`).
- 웹의 기본 계약 읽기 출처는 실제 Claude 추출이다. 정답지 장면은 출처를 정답지로 바꿔 보여 준다([데모 대본](demo-script.md)).
- `docs/screenshots/`의 조치 보드 화면은 이 수정 전에 찍었으므로 현재 화면과 다를 수 있다.

**보여 줄 화면.** 정답지 대시보드의 관제 요약(`docs/screenshots/typhoon_kpi.png`). 웹 데모 조치 보드는 사이트를 직접 열어 보여 준다. `docs/screenshots/web/web_actions.png`는 수정 전 화면이라 쓰지 않는다.

---

## 5. 재현성 (Q22~Q28)

### Q22. 문서의 숫자를 어떻게 다시 내나요?

**말로 하는 답.** "네트워크 없이 `python -m clausetower demo --llm mock` 한 줄이면 README 6절 정책 비교 숫자가 그대로 나옵니다. 시뮬레이터와 계산기는 결정적이라 몇 번을 돌려도 같은 값입니다. 같은 게이트에서 시험 71개와 웹 엔진 대조 36/36이 통과했습니다."

**근거.**

```bash
pip install -e ".[dev]"
python -m clausetower demo --llm mock          # 6절 정책 비교(결정적), out/demo/dashboard.html
pytest -q                                      # 71 passed
python -m clausetower eval --seeds 30          # 다중 시드, 결과는 out/eval/ (추적 파일을 덮어쓰지 않음)
python eval/run_eval.py extraction eval/results/real/report_typhoon.json   # 실제 모델 보고서 채점(LLM 호출 없음)
python scripts/build_site.py && node scripts/verify_engine.js              # 웹 엔진 36/36 (mock 데모를 먼저 돌린다)
```

- 게이트 측정 시간: mock 데모 36.3초(시나리오 3종, 탐색 포함), pytest 76.3초(`_workspace/04_qa_gates_r2.json`의 `gates`).
- 다중 시드 게이트 결과가 추적 중인 `eval/results/robustness.json`과 같다(`gates.robustness.matches_tracked_results`).
- Windows·사내망 주의와 단계별 설명: [설치·실행 가이드](setup-guide.md). 명령별 설명: [평가 방법](evaluation.md).

**보여 줄 화면.** 시간이 있으면 터미널에서 mock 데모를 돌려 마지막 줄의 절감 금액을 보인다.

### Q23. 실제 모델 결과는 두 번뿐인데 재현되나요?

**말로 하는 답.** "실제 모델은 매번 조금씩 다르게 답하므로 같은 숫자가 다시 나온다고 약속할 수 없습니다. 그래서 두 번 돌린 보고서와 로그를 모두 저장했고, 두 회차 차이는 추출 1항목(102개에서 101개)과 항만 적체 판단 1건이었습니다. 2회로 분산을 통계로 말하기에는 부족하다는 점은 한계로 적었습니다."

**근거.**
- 저장 위치: 2회차 `eval/results/real/`, 1회차 `eval/results/real_prev/`. 저장된 보고서는 LLM 호출 없이 다시 채점하고(Q22의 채점 명령) 대시보드로 열 수 있다(`python -m clausetower demo --from-reports eval/results/real --out out/real`).
- 2회차는 추출 프롬프트의 한 구절("지연 페널티 조건" → "지연 배상 조건")을 고친 뒤 실행했다(`eval/results/real/README.md`). 두 회차의 차이는 순수한 모델 분산만은 아니다.
- 새로 재려면 `scripts/real_run.py typhoon port_congestion`(실제 LLM 호출, 2회차 기준 약 $2.06, Q17).
- README 10절 한계, [평가 방법](evaluation.md)의 타당성 위협.

**보여 줄 화면.** 없음.

### Q24. 실제 모델 점수는 지금 프롬프트로 잰 것인가요?

**말로 하는 답.** "아닙니다. 실제 모델 점수는 프롬프트에 주입 방어 규칙과 `<contract>` 감싸기를 넣기 전에 잰 값입니다. 바뀐 것은 규칙 한 줄과 본문 감싸기, Claude Code 호출의 도구 끄기 옵션, 그리고 판단에서 빠진 조건을 미충족으로 보는 조건 결합 규칙이지만 같은 조건으로 다시 재지 않았습니다. 저장된 보고서를 지금 결합 규칙으로 다시 계산하면 2회차 점수는 그대로이고, 1회차 항만 적체는 세움건설이 미적용으로 바뀌어 최종 적용 7/8이 6/8이 됩니다. 그래서 발표에서는 '이전 프롬프트 기준'이라고 밝히고, 재측정은 과금 호출이 필요해 남겨 두었습니다."

**근거.** 현재 프롬프트 `prompts/extract.md`, `prompts/judge.md`. 측정 기록 `eval/results/real/README.md`, `eval/results/real/run.log`. 조건 결합 규칙: `src/clausetower/extract.py`의 `conditions_satisfied`, `src/clausetower/web/engine.js`의 `condsOk`. 1회차 변화는 `eval/results/real_prev/report_port_congestion.json`의 세움건설(C) 판단을 `conditions_satisfied`로 다시 계산해 확인했다(판단 단계가 `conditions_met`에 적은 조건 키 3개가 추출 단계의 `force_majeure.conditions` 문구와 글자가 달라, 세 조건이 모두 판단에서 빠진 것으로 처리됨). 재측정 절차는 [평가 방법](evaluation.md).

**보여 줄 화면.** 없음.

### Q25. 웹 데모와 파이썬의 숫자가 정말 같나요?

**말로 하는 답.** "같은 입력이면 같습니다. `verify_engine.js`가 시나리오·출처별 총 배상금, 순위표, 탐색 근사 최적까지 36개 항목을 대조해 모두 일치했고, 웹 조작 패널이 만들 수 있는 입력 75케이스에서도 정책별 총액·고객별 금액·순위표가 파이썬과 같았습니다. 다만 패널 설정을 바꾼 뒤의 탐색 근사 최적은 브라우저가 더 가볍게 찾은 참고값이라 문서 표와 다를 수 있습니다."

**근거.**
- `facts.engine_parity` 36/36(`scripts/verify_engine.js`, 시나리오·출처별 탐색 근사 최적 대조 5건 포함). 보고서나 `site/data.js`가 없으면 통과로 치지 않고 실패한다.
- 패널 입력 75케이스: `scripts/verify_engine_panel.js`가 입력을 만들고 `tests/test_web.py::test_js_engine_matches_python_on_panel_inputs`가 대조한다.
- 계산 경계값의 JS·파이썬 일치: `tests/test_web.py::test_js_compute_penalty_matches_python_on_boundaries`.
- 탐색 차이: Q10.

**보여 줄 화면.** 웹 데모(https://namojo.github.io/clausetower/)의 태풍 기본 화면. 정답지 출처로 바꾸면 관제 요약 숫자가 대시보드와 같다.

### Q26. 실제 모델 로그와 보고서의 숫자가 다른 곳이 있던데요?

**말로 하는 답.** "1회차 로그는 정책 이름과 정의를 바꾸기 전의 원 실행 기록이라, 지금의 절대값 변형 값(2,979,000원)이 당시 이름인 '물리는 순서(ClauseTower)'로 적혀 있습니다. 저장된 보고서는 LLM 결과는 그대로 두고 시뮬레이션만 현재 정의로 다시 돌린 것이라 문서 숫자와 맞습니다. 이 경위는 `eval/results/real/README.md`에 적었습니다."

**근거.**
- `eval/results/real_prev/run.log`: 태풍 절감 76.8%, "물리는 순서(ClauseTower) 2,979,000원", "물리는 순서(시간당 변형) 2,996,500원". `eval/results/real_prev/report_typhoon.json`: 절감 76.7%, ClauseTower 2,996,500원, 절대값 변형 2,979,000원.
- 시뮬레이션만 다시 돌리는 옵션: `python -m clausetower demo --from-reports <폴더> --resim`(`src/clausetower/cli.py`).
- 2회차 로그(`eval/results/real/run.log`)의 시나리오별 숫자는 보고서와 같다(태풍 12,834,000 → 2,996,500원, 항만 적체 8,925,000 → 3,213,500원).
- 채점 파일(`eval/results/extraction_*.json`)의 `report` 필드는 채점 당시 경로(`out/real_v2/…`)다. 같은 점수가 `eval/results/real/report_*.json`을 채점해도 나온다.

**보여 줄 화면.** 없음.

### Q27. 사내 Windows PC에서도 그대로 돌아가나요?

**말로 하는 답.** "돌아가지만 세 가지를 맞춰야 합니다. 편집 설치(`pip install -e .`)를 하거나 `CLAUSETOWER_ROOT`를 저장소 경로로 지정하고, 한국어 콘솔에서는 `PYTHONUTF8=1`을 켜고, 사내 프록시가 있으면 `NO_PROXY`에 `127.0.0.1,localhost`를 더합니다. 이번 게이트도 이 보정을 넣은 한국어 Windows PC에서 통과했습니다."

**근거.**
- 게이트 환경(`_workspace/04_qa_gates_r2.json`의 `env`): win32, Python 3.14.6(요구 `>=3.11`), 콘솔 인코딩 cp949, 프록시 설정 있음, `NO_PROXY`에 루프백 없음. 적용한 보정: `PYTHONPATH=src`, `PYTHONUTF8=1`, `NO_PROXY+=127.0.0.1,localhost`, `CLAUSETOWER_LLM=mock`.
- CI는 Ubuntu·Python 3.12에서 시험 → mock 데모 → 사이트 조립 → 엔진 대조를 돌리고, PR에서도 돈다. 배포는 검증을 통과한 산출물만 별도 job이 올린다(`.github/workflows/pages.yml`).
- 브라우저 스모크(`scripts/smoke_web.js`)는 Playwright가 필요하다. 이번 게이트에서는 미설치로 건너뛰었다.
- 증상별 해결: [설치·실행 가이드](setup-guide.md)의 문제 해결 표.

**보여 줄 화면.** 없음.

### Q28. 시험 71개는 무엇을 보장하나요? mock의 정확도 100%는요?

**말로 하는 답.** "시험은 배상금 계산의 경계값, 조건 결합의 보수적 처리, 로컬 도우미의 출처 차단과 오류 응답, 웹 엔진과 파이썬의 일치를 확인합니다. mock 모드의 추출 정확도 100%는 정답지를 그대로 쓰기 때문이라 의미가 없고, 실제 모델 정확도는 저장된 실제 보고서로만 말합니다."

**근거.**
- `facts.tests_passed` 71(시험 함수 67개, 일부는 매개변수로 여러 번 돈다).
- 계산 경계값: `tests/test_exposure.py`(유예와 같은 지연, 누진 48h 경계, 가중 정액 시작점, 상한과 같은 금액, 주말을 넘는 영업일 유예, 고객 합계 % 상한).
- 조건 결합: `tests/test_sim_and_agent.py::test_judge_missing_condition_key_fails_closed`, `tests/test_web.py::test_js_derive_judgment_rules`.
- 도우미·LLM 경로: `tests/test_server_and_openai.py`, `tests/test_llm_claude_code.py`(실제 LLM 대신 가짜 CLI를 쓴다).
- mock 정확도의 뜻: README 8절.

**보여 줄 화면.** 없음.

---

## 6. 아직 답할 수 없는 것

물으면 "재지 않았습니다"라고 답하고 아래 계획을 말한다.

| 질문 | 현재 상태 | 다음 |
| --- | --- | --- |
| 실제 계약서에서도 정확한가 | 가상 계약 8부, 정답지 동일 저자, 한국어만 | 실제 계약서 블라인드 평가(목표) |
| 주입 방어가 실제로 막는가 | 프롬프트 규칙·도구 끄기는 적용, 주입 계약서 평가는 없음 | 주입 문장을 심은 계약서로 평가(목표) |
| 지금 프롬프트의 정확도 | 실제 모델 점수는 이전 프롬프트 기준 | 같은 계약·시나리오로 재측정(과금, 약 $2) |
| 도구를 끈 Claude Code 호출이 구조화 출력과 함께 도는가 | 코드와 CLI 도움말로 옵션은 확인, 실제 호출로는 확인 안 함 | `python -m clausetower run typhoon --llm claude-code --no-search` 1회(과금) 후 `llm_fallbacks`가 0인지 확인 |
| 실제 네트워크 규모의 효과 | 작은 모형 안의 값 | TMS 배차 기록 재생(목표) |
| 모델 분산 | 2회 실행 | 반복 실행과 CI 평가 루프(목표) |
