# 해커톤 문서 목록

문서 9종의 명세다. 작성자는 맡은 문서의 절만 읽는다. `우선순위` P1은 심사 전에 반드시 맞아야 하는 문서, P2는 상세 문서화를 위한 문서다.

## 목차

1. [README.md](#readmemd) — 갱신, P1
2. [docs/proposal.md](#docsproposalmd) — 갱신, P1
3. [docs/ax-hackathon-form.md](#docsax-hackathon-formmd) — 갱신, P1
4. [docs/demo-script.md](#docsdemo-scriptmd) — 갱신, P1
5. [docs/setup-guide.md](#docssetup-guidemd) — 신규, P1
6. [docs/judge-qa.md](#docsjudge-qamd) — 신규, P1
7. [docs/architecture.md](#docsarchitecturemd) — 신규, P2
8. [docs/evaluation.md](#docsevaluationmd) — 신규, P2
9. [docs/hackathon-plan.md](#docshackathon-planmd) — 신규, P2

## 문서 세트 공통

- 모든 문서는 README 11절 「문서」 목록에서 링크된다. 새 문서를 만들면 README 갱신 항목에 그 링크가 들어가야 한다.
- 같은 숫자는 모든 문서에서 같다. 숫자의 기준 문서는 README 6절이며, 다른 문서는 같은 `facts`에서 가져온다.
- 문서마다 맨 위 한두 줄에 "누가 언제 읽는 문서인지"와 "숫자의 출처"를 적는다.

---

## README.md

- **목적:** 저장소 첫 화면. 1분 안에 문제·해법·결과를 보이고, 10분 안에 돌려 보게 한다.
- **독자:** 심사위원, 사내 동료, 저장소 방문자.
- **필수 구성:** 현재 11절 구조 유지(한눈에 표, 왜, 핵심 아이디어, 화면, 데모 데이터, 동작, 측정 결과, 선행 조사, 빠른 시작과 검증, 구조와 원칙, 한계와 다음, 심사 기준과 문서).
- **갱신 초점:** 한눈에 표와 6절 숫자를 최신 `facts`로 맞춘다. 8절 빠른 시작에 Windows·사내망 주의 한 줄과 `docs/setup-guide.md` 링크. 5-5절 LLM 모드와 로컬 도우미 설명을 코드(옵션·환경 변수)와 맞춘다. 11절 문서 목록에 새 문서 링크. 코드 수정의 `doc_impact`가 있으면 반영.
- **근거:** `facts` 전체, `cli.py`, `llm.py`, `server.py`, `pages.yml`.
- **분량:** 현행 ±15%. 늘리지 말고 상세는 새 문서로 보낸다.

## docs/proposal.md

- **목적:** 기획서 전문. 문제·통찰·해법·데모 장면·증거·위험을 한 흐름으로.
- **독자:** 심사위원(사전 심사), 사업 담당.
- **필수 구성:** 현행 구조 유지(문제, 통찰과 해법, 데모 장면, 견고성, 실제 모델 결과, 웹 데모, 화면 설계, 아키텍처, 사업 연결, 위험과 대응, 지금 안 되는 것, 작업 분담, 부록).
- **갱신 초점:** 실제 모델 측정 횟수·결과를 README와 같은 회차 기준으로 통일. LLM 모드 4종(`openai` 포함), 아키텍처에 웹 엔진 경로 포함. "지금 안 되는 것"을 현재 구현 상태와 맞춤.
- **근거:** `facts`, `eval/results/real*/`, `eval/results/extraction_*.json`.
- **분량:** 현행 ±10%.

## docs/ax-hackathon-form.md

- **목적:** AX해커톤 아이디어 기획서 양식의 7개 문항 답안.
- **독자:** 해커톤 운영·심사위원.
- **필수 구성:** 문항 1~7. **문항 제목은 원문 그대로 둔다.**
- **갱신 초점:** 4번 기대효과 표의 측정값을 최신으로. 3번 "2일 동안 구현할 기능"이 이미 구현된 것(예: 조치 보드)을 새 기능처럼 쓰지 않게 고치고 `docs/hackathon-plan.md`와 맞춘다. 7번 한계를 최신으로.
- **근거:** `facts`, `docs/hackathon-plan.md`(같은 실행에서 쓰는 경우 문서 세트 목록의 작성 지시).
- **분량:** 문항별 현행 수준. 양식 칸에 붙여 넣을 수 있는 길이.

## docs/demo-script.md

- **목적:** 3분 발표 대본과 준비 절차.
- **독자:** 발표자.
- **필수 구성:** ① 준비(어떤 화면을 어떤 명령으로 열어 두는가, 오프라인 대체 경로) ② 시각표(시각·화면·말) ③ 실패 대비(네트워크 없음, 웹 데모가 안 열림, 프로젝터 해상도, 로컬 도우미 연결 실패) ④ 예상 질문 짧은 답 4~6개와 `judge-qa.md` 링크.
- **갱신 초점:** 대본 숫자를 최신 `facts`와 실제 모델 현재 회차로 맞춘다(예: 추출 일치 항목 수, 보수적으로 틀린 건수). 웹 데모(`namojo.github.io/clausetower`)를 쓰는 동선을 넣을지 판단해 준비 절에 적는다.
- **근거:** `facts`, `eval/results/real/`, 화면 순서(README 3절).
- **분량:** 시각표 8~10행, 전체 1~2쪽.

## docs/setup-guide.md

- **목적:** 처음 받은 사람이 어떤 PC에서든 데모·검증을 끝까지 돌리게 한다.
- **독자:** 심사위원, 팀원(한국어 Windows 사내 PC 포함).
- **필수 구성:**
  1. 요구 사항: Python(`requires-python`), Node(엔진 대조용), Playwright(선택), Claude Code CLI 또는 API 키(실제 모드, 선택).
  2. 설치: macOS·Linux(bash)와 Windows(PowerShell) 블록을 따로.
  3. 3분 확인: mock 데모 → `out/demo/dashboard.html` 열기.
  4. 웹 데모 로컬 조립과 엔진 대조.
  5. 실제 모드: LLM 모드 4종과 환경 변수 표(`CLAUSETOWER_LLM`, `CLAUSETOWER_MODEL`, `CLAUSETOWER_CONCURRENCY`, `CLAUSETOWER_CLAUDE_BIN`, `CLAUSETOWER_CLAUDE_TIMEOUT`, `CLAUSETOWER_OPENAI_BASE_URL`, `CLAUSETOWER_OPENAI_API_KEY`, `ANTHROPIC_API_KEY`). 비용·시간(측정값) 안내.
  6. 로컬 도우미: 실행, 웹 데모에서 연결, 보안 주의(바인딩, 허용 출처, 키 보관).
  7. 검증 절차: 게이트 스크립트 또는 README 8절 명령.
  8. 문제 해결 표: 증상 → 원인 → 해결(사내 프록시와 `NO_PROXY`, cp949 콘솔, `No module named clausetower`, Playwright 미설치, `claude` CLI 미설치 시 mock 전환).
- **근거:** 게이트 결과의 `env`, `cli.py`, `llm.py`, `server.py`, `ct-quality-gates` 스킬의 「실패 해석」.
- **분량:** 2~4쪽.

## docs/judge-qa.md

- **목적:** 심사장의 까다로운 질문에 30초 안에 근거와 함께 답한다.
- **독자:** 발표자, 팀원.
- **필수 구성:** 심사 기준 4개(AI 활용 수준, 문제 해결 방식, 실제 업무 적용 가능성, 재현성)별로 질문 5~8개. 질문마다 "말로 하는 답(2~3문장, ~습니다)" + "근거(숫자와 경로)" + "보여 줄 화면(있으면)". 반드시 다룰 질문: 정답지를 팀이 썼는데 정확도를 믿을 수 있나, 시뮬레이터가 작은데 절감률이 의미 있나, 계약 해석 책임은 누구에게 있나, LLM이 틀리면 어떻게 되나, 실제 모델 비용·속도, 계약서 보안, 기존 TMS·CLM과 무엇이 다른가, 왜 시간당으로 나누나(절대값 변형과의 차이), 탐색 근사 최적과의 차이, 프롬프트 주입.
- **근거:** `facts`, README 7·10절, `eval/results/`, 코드.
- **분량:** 질문 25~35개.

## docs/architecture.md

- **목적:** 기술 심사위원과 개발자가 코드를 열기 전에 구조와 설계 결정을 이해하게 한다.
- **독자:** 기술 심사위원, 이어서 개발할 팀원.
- **필수 구성:** 시스템 개요도(Mermaid 가능), 모듈 책임표(`src/clausetower/*`, `web/*`, `scripts/*`), 데이터 계약(`schemas.py` 주요 모델과 필드), 배상금 계산 규칙(단계와 실제 정답지 계약 하나로 손 계산 예시), 면책 판단의 조건 결합, 시뮬레이터와 정책 정의(수식), LLM 경로(모드 선택, 구조화 출력, 재시도, 대체와 기록), 웹 데모 구조(`data.js` 조립, `engine.js` 이식, 대조 검증), 로컬 도우미 API(`/health`, `/extract`, `/judge`), 데이터 흐름과 보안, 설계 결정과 대안(왜 LLM이 계산하지 않나, 왜 조건을 결합하나, 왜 정적 사이트인가), 확장 지점(TMS 우선순위 입력 API).
- **근거:** 코드 전체. 손 계산 예시는 `exposure.py`로 다시 계산해 확인한다.
- **분량:** 4~7쪽.

## docs/evaluation.md

- **목적:** 숫자가 어떻게 만들어졌고 어디까지 믿을 수 있는지 밝힌다.
- **독자:** 기술 심사위원.
- **필수 구성:** 평가 질문(무엇을 증명하려 하나), 정답지 구성(계약 8부 106항목, 판단 32항목의 세는 방법), 지표 정의(`term_field_accuracy`, `judgment_accuracy`, `applies_accuracy`, `citations_verbatim_rate`를 구분), 실제 모델 결과(1·2회차 표와 틀린 항목의 성격), 정책 비교와 다중 시드 방법·결과, 웹 엔진 대조, 재현 명령, 타당성 위협(정답지 동일 저자, 2회 실행, 작은 모형, 한국어 계약만), 다음 평가 계획(CI 평가 루프, 블라인드 평가).
- **근거:** `eval/run_eval.py`, `eval/results/`, `facts.real_model_scores`, `facts.robustness`.
- **분량:** 3~5쪽.

## docs/hackathon-plan.md

- **목적:** 해커톤 2일을 시간 단위로 쓰는 실행 계획.
- **독자:** 팀원.
- **필수 구성:** 출발점(지금 되는 것과 안 되는 것, 코드 근거), 목표 기능(양식 3번과 같은 목록)마다 작업 분해·완료 기준(측정 가능)·담당 역할(기획서 10절 역할 이름, 실명 없음)·예상 시간, Day 1/Day 2 시간표, 위험과 대응, 코드 동결 시점과 이후 할 일(스크린샷 재촬영, 문서 숫자 재측정은 게이트로), 제출·발표 리허설 체크리스트.
- **근거:** 양식 3번, README 10절, 현재 코드 상태(구현 여부를 코드로 확인).
- **분량:** 2~4쪽. 계획은 "제안"이며 팀이 고칠 수 있다고 밝힌다.
