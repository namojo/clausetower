# ClauseTower 설치·실행 가이드

저장소를 처음 받은 심사위원과 팀원이 읽는다. 대상 PC에는 한국어 Windows 사내 PC(프록시, cp949 콘솔)도 포함된다. 순서대로 따라 하면 mock 데모, 웹 데모, 검증 절차를 끝까지 돌릴 수 있다.
숫자의 출처는 2026-11-02 품질 게이트 측정(팀 작업 폴더 `_workspace/04_qa_gates_r2.json`, 커밋하지 않음), 실제 모델 실행 로그(`eval/results/real/run.log`, `eval/results/real_prev/run.log`), 코드(`pyproject.toml`, `src/clausetower/cli.py`, `llm.py`, `server.py`)다.

**차례**

1. [요구 사항](#1-요구-사항)
2. [설치](#2-설치)
3. [3분 확인: mock 데모](#3-3분-확인-mock-데모)
4. [웹 데모 로컬 조립과 엔진 대조](#4-웹-데모-로컬-조립과-엔진-대조)
5. [실제 모드: LLM 연결](#5-실제-모드-llm-연결)
6. [로컬 도우미](#6-로컬-도우미)
7. [검증 절차](#7-검증-절차)
8. [문제 해결](#8-문제-해결)

---

## 1. 요구 사항

| 항목 | 필요한가 | 버전·비고 | 근거 |
| --- | --- | --- | --- |
| Python | 필수 | 3.11 이상. CI는 3.12, 이 문서의 측정 PC는 3.14.6 | `pyproject.toml`의 `requires-python = ">=3.11"`, `.github/workflows/pages.yml` |
| Python 패키지 | 필수 | `pydantic>=2.6`, `pyyaml>=6.0`, `anthropic>=1.0`, 시험용 `pytest>=8.0`. 사내망이면 PyPI 미러나 프록시 설정이 있어야 설치된다 | `pyproject.toml` |
| Node.js | 엔진 대조·스모크용 | CI는 22, 측정 PC는 v24.18.0. 없으면 JS 대조 시험은 건너뛴다(skipped) | `pages.yml`, `tests/test_web.py` |
| Playwright + Chromium | 선택(브라우저 스모크) | `package.json`이 없어 따로 설치한다(2절 끝) | `scripts/smoke_web.js` |
| Codex CLI | 실제 모드(기본 연결) | `codex` CLI 설치·로그인(측정 PC 0.154.0). 대안: `claude` CLI, `ANTHROPIC_API_KEY`, 사내 OpenAI 호환 주소 | `src/clausetower/llm.py` |

mock 모드(정답지 사용)만 쓰면 네트워크도 API 키도 필요 없다. 심사용 숫자는 모두 mock 모드와 저장된 실제 모델 보고서로 다시 나온다.

## 2. 설치

**반드시 편집 설치(`pip install -e`)를 한다.** 계약서(`contracts/`)·시나리오(`scenarios/`)·프롬프트(`prompts/`)가 패키지 밖 저장소 루트에 있어서다. 저장소 루트에서 `python -m clausetower ...`를 실행하는 경우는 설치 없이도 동작한다(루트의 `clausetower/` 연결 패키지가 `src/clausetower`를 가리킨다). 다만 의존성(`pydantic`, `pyyaml`, `anthropic`)은 있어야 하고, 저장소 밖 폴더나 `clausetower` 콘솔 명령으로 실행하려면 편집 설치가 필요하다. 다른 방식으로 설치했다면 `CLAUSETOWER_ROOT`에 저장소 루트를 지정한다(`src/clausetower/contracts.py`).

**macOS·Linux(bash)**

```bash
cd clausetower
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
```

**Windows(PowerShell).** Windows PowerShell 5.1은 `&&`를 지원하지 않으므로 한 줄씩 실행한다.

```powershell
cd clausetower
python -m venv .venv
.\.venv\Scripts\Activate.ps1
$env:PYTHONUTF8 = "1"                       # cp949 콘솔에서 한글·기호 출력 오류 방지
$env:NO_PROXY += ',127.0.0.1,localhost'     # 사내 프록시가 로컬 도우미 요청을 가로채지 않게
python -m pip install -e ".[dev]"
```

- `$env:` 설정은 그 PowerShell 창에서만 유지된다. 새 창을 열면 다시 넣는다.
- `PYTHONUTF8=1`은 콘솔 출력용이다. `codex`·`claude-code` 모드가 CLI와 주고받는 한글은 이 설정 없이도 UTF-8로 처리된다(`llm.py`의 `encoding="utf-8"`).
- `NO_PROXY`는 `pytest`에는 더 이상 필요 없다. 시험 프로세스가 스스로 `127.0.0.1,localhost`를 더한다(`tests/conftest.py`). 손으로 `curl`이나 파이썬 클라이언트로 로컬 도우미를 부를 때, 사내 LLM 주소가 프록시를 거치면 안 될 때 필요하다.
- bash에서 사내 프록시를 쓰면 같은 설정을 `export NO_PROXY="$NO_PROXY,127.0.0.1,localhost"`로 넣는다.

**Playwright(선택).** 저장소 안에 `node_modules`를 만들지 않도록 저장소 밖 폴더에 설치하고 `NODE_PATH`로 가리킨다. `scripts/smoke_web.js`는 `require('playwright')`로 불러오므로 `NODE_PATH`가 있으면 찾는다.

```bash
mkdir -p ~/ct-tools && cd ~/ct-tools
npm i -D playwright && npx playwright install chromium
export NODE_PATH="$HOME/ct-tools/node_modules"
```

```powershell
mkdir $HOME\ct-tools; cd $HOME\ct-tools
npm i -D playwright
npx playwright install chromium
$env:NODE_PATH = "$HOME\ct-tools\node_modules"
```

## 3. 3분 확인: mock 데모

```bash
python -m clausetower demo --llm mock        # 3개 시나리오 실행 + out/demo/dashboard.html
open out/demo/dashboard.html                 # Linux: xdg-open
```

```powershell
python -m clausetower demo --llm mock
Start-Process out\demo\dashboard.html
```

- 네트워크를 쓰지 않는다. 측정 PC(Windows)에서 탐색 근사 최적 계산을 포함해 36~51초 걸렸다(2026-11-02 게이트 36.3초, 수동 실행 50.7초).
- 콘솔 마지막에 시나리오별 정책 비교가 나온다. 태풍 상륙이면 마감 임박 순(기존) 12,834,000원, 배상 노출 순(ClauseTower) 2,996,500원, 절감 76.7%다. 세 시나리오의 전체 표는 [README 6절](../README.md#6-측정-결과)과 같아야 한다(결정적).
- `--llm mock`을 빼지 않는다. `--llm`도 `CLAUSETOWER_LLM`도 없으면 `auto`가 PC에 있는 API 키나 `claude` CLI를 골라 실제 호출(과금)을 한다. 이때 CLI가 "주의: --llm을 지정하지 않아 auto가 실제 LLM(…)을 골랐다"를 출력한다.
- 시나리오 하나만 보려면 `python -m clausetower run typhoon --llm mock`(산출물 `out/typhoon/`).

## 4. 웹 데모 로컬 조립과 엔진 대조

배포본은 https://namojo.github.io/clausetower/ 이다. 같은 사이트를 로컬에서 조립하고, 브라우저 엔진(`engine.js`)이 파이썬과 같은 숫자를 내는지 확인한다.

```bash
python -m clausetower demo --llm mock        # 대조 기준인 out/demo/report_*.json (3절에서 했으면 생략)
python scripts/build_site.py                 # site/ 조립(측정 data.js 208KB)
node scripts/verify_engine.js                # 끝 줄: 36/36 checks passed (expected 36)
python -m http.server 8000 --directory site  # 브라우저에서 http://localhost:8000
```

PowerShell에서도 명령은 같다.

- `verify_engine.js`는 대조할 파이썬 보고서가 없으면 건너뛰지 않고 `MISSING`으로 실패한다. 그래서 mock 데모를 먼저 돌린다.
- 대조 36개는 시나리오·출처 조합 5개(정답지 3종, 실제 모델 보고서가 있는 태풍 상륙·항만 적체 2종)마다 7개(정책 5개 총 배상금, 배상 노출 순위, 탐색 근사 최적)와 브라우저 탐색이 시작점보다 나쁘지 않은지 1개다(`scripts/verify_engine.js`).
- 웹 화면의 탐색 근사 최적은 기본 설정(화물 배치 A, 패널 기본값)일 때만 README 6절 표와 같다. 패널 값을 바꾸면 브라우저가 다시 탐색한 참고값이라 문서 표와 다를 수 있다.
- 웹 데모의 기본 출처는 실제 Claude 추출이다. 이 출처에서는 세움건설이 통지 외 조건까지 미충족이라 조치 보드에 "통지 12h로 시뮬레이션" 버튼이 나오지 않는다. "시한을 지켰다면 0원" 장면을 보려면 계약 읽기 출처를 정답지로 바꾼다([데모 대본](demo-script.md)).
- `site/index.html`을 파일로 바로 열어도 시뮬레이션은 돈다. 다만 파일로 연 페이지는 출처가 `null`이라 로컬 도우미가 403으로 거절한다. 도우미를 쓸 때는 위처럼 `http.server`로 연다.

## 5. 실제 모드: LLM 연결

파이썬의 모든 LLM 호출은 `src/clausetower/llm.py` 한 곳을 지난다. 모드는 `--llm` 옵션이 먼저이고, 없으면 `CLAUSETOWER_LLM`, 그것도 없으면 `auto`다.

| 모드 | 무엇 | 준비 |
| --- | --- | --- |
| `mock` | 정답지를 그대로 사용. 네트워크 없음 | 없음 |
| `codex` | Codex CLI(`codex exec`)를 하위 프로세스로 호출. **기본 연결** | `codex` CLI 설치·로그인. 모델은 기본 `gpt-6.1-sol`(`CLAUSETOWER_CODEX_MODEL`로 변경) |
| `claude-code` | Claude Code CLI를 하위 프로세스로 호출(Claude 구독) | `claude` CLI 설치·로그인. 못 찾으면 경고 후 mock으로 전환 |
| `anthropic` | Anthropic SDK | `ANTHROPIC_API_KEY`(사내 호환 게이트웨이면 `ANTHROPIC_BASE_URL`도) |
| `openai` | OpenAI 호환 `/chat/completions` + 강제 tool call(사내 LLM) | `CLAUSETOWER_OPENAI_BASE_URL`, 필요하면 `CLAUSETOWER_OPENAI_API_KEY`, `CLAUSETOWER_MODEL` |
| `auto` | Codex CLI → API 키 → 사내 엔드포인트 → `claude` CLI → mock 순으로 고른다 | – |

**환경 변수**

| 변수 | 기본값 | 뜻 |
| --- | --- | --- |
| `CLAUSETOWER_LLM` | 없음(`auto`) | 위 모드 이름. `--llm`이 있으면 무시된다 |
| `CLAUSETOWER_MODEL` | `claude-opus-5-5` | 모델 이름. `openai` 모드에서는 사내 모델 이름을 넣는다 |
| `CLAUSETOWER_CONCURRENCY` | `4`(mock은 1) | 동시 호출 수 |
| `CLAUSETOWER_CODEX_BIN` | `codex` | Codex CLI 실행 파일 경로. PATH에 없을 때 |
| `CLAUSETOWER_CODEX_MODEL` | `gpt-6.1-sol` | Codex 모델. 빈 문자열이면 config.toml의 `model`을 쓴다. 로그인한 계정이 지원하지 않으면 `model_not_found`가 난다 |
| `CLAUSETOWER_CODEX_TIMEOUT` | `600` | Codex 호출 하나의 제한 시간(초) |
| `CLAUSETOWER_CLAUDE_BIN` | `claude` | CLI 실행 파일 경로. PATH에 없을 때 |
| `CLAUSETOWER_CLAUDE_TIMEOUT` | `600` | 호출 하나의 제한 시간(초). `openai` 모드에도 쓰인다 |
| `CLAUSETOWER_OPENAI_BASE_URL` | 없음 | 예: `https://llm.company.local/v1`. 값이 있으면 `auto`가 `openai`를 고른다 |
| `CLAUSETOWER_OPENAI_API_KEY` | 없음 | `Authorization: Bearer` 토큰. 없으면 인증 헤더 없이 부른다 |
| `ANTHROPIC_API_KEY` | 없음 | 값이 있으면 `auto`가 `anthropic`을 고른다(`ANTHROPIC_AUTH_TOKEN`도 같다) |
| `ANTHROPIC_BASE_URL` | SDK 기본 | Anthropic SDK가 읽는다. 사내 Anthropic 호환 게이트웨이 주소 |
| `CLAUSETOWER_ROOT` | 패키지 위치에서 계산 | 저장소 루트. 편집 설치가 아닐 때만 |
| `CLAUSETOWER_ALLOWED_ORIGINS` | 없음 | 로컬 도우미 허용 출처 추가(쉼표 구분, 6절) |

**실행 예**

```bash
python -m clausetower run typhoon --llm codex --no-search   # 시나리오 하나, 탐색 근사 최적 생략
CLAUSETOWER_LLM=codex python scripts/real_run.py typhoon port_congestion   # 추적 보고서와 같은 구성, out/real/에 저장
```

```powershell
python -m clausetower run typhoon --llm codex --no-search
$env:CLAUSETOWER_LLM = "codex"; python scripts/real_run.py typhoon port_congestion
Remove-Item Env:CLAUSETOWER_LLM      # 남겨 두면 이 창의 다음 명령이 --llm 없이도 실제 호출을 한다
```

**비용·시간(측정).** 계약 추출은 시나리오 사이에 공유하므로 호출은 추출 8회 + 시나리오당 판단 8회다.

| 실행 | 호출 | CLI 보고 비용 | 시간 | 출처 |
| --- | ---: | ---: | --- | --- |
| 태풍 상륙 하나(추출 8 + 판단 8) | 16회 | $1.78 | 70초 | `eval/results/real/run.log` |
| 태풍 상륙 + 항만 적체(2회차, 현재 보고서) | 24회 | $2.06 | 시나리오별 70초·31초, 호출 시간 합계 283초(4개 병렬), 대체 0회 | `eval/results/real/run.log` |
| 같은 구성 1회차 | 24회 | $1.98 | 호출 시간 합계 270초, 대체 0회 | `eval/results/real_prev/run.log` |

- 측정은 `claude-code` 모드(claude-opus-5-5)만 했다. `anthropic`·`openai` 모드의 비용·시간은 측정하지 않았다. 시나리오 3종을 모두 도는 `demo --llm claude-code`는 32회 호출(계산)이며 비용은 재지 않았다.
- 실패하면 `claude-code`·`openai`는 한 번 다시 시도하고, 그래도 안 되면 그 항목을 정답지로 대체한 뒤 횟수를 남긴다(`run.log`의 `fallbacks`, 보고서의 `llm_fallbacks`). 대체가 0이 아니면 그 실행의 숫자는 일부가 정답지 값이다.
- `eval/results/real/`의 실제 모델 측정은 프롬프트에 주입 방어 규칙과 `<contract>` 감싸기를 추가하기 전에 잰 값이다. 지금 다시 돌리면 값이 달라질 수 있다([평가 방법](evaluation.md)).
- `claude-code` 모드는 CLI의 내장 도구를 모두 끄고(`--tools ""`) 사용자 MCP 서버를 싣지 않는다(`--strict-mcp-config`). 이 옵션 조합으로 구조화 출력이 동작하는지는 수정 뒤 실제 호출로 아직 확인하지 않았다(확인 필요). 깨지면 대체 횟수로 드러난다.

## 6. 로컬 도우미

웹 데모(정적 페이지)가 이 PC의 LLM 연결(기본 Codex CLI, 사내 LLM)로 계약을 읽게 하는 작은 서버다(`src/clausetower/server.py`).

**실행**

```bash
python -m clausetower serve --llm codex                # Codex CLI(기본 연결)
CLAUSETOWER_OPENAI_BASE_URL=https://llm.company.local/v1 python -m clausetower serve --llm openai   # 사내 LLM
curl http://127.0.0.1:8787/health                      # {"ok": true, "mode": ..., "model": ..., "calls": ..., "fallbacks": ...}
```

```powershell
python -m clausetower serve --llm codex
$env:CLAUSETOWER_OPENAI_BASE_URL = "https://llm.company.local/v1"; python -m clausetower serve --llm openai
curl.exe http://127.0.0.1:8787/health
```

기본 주소는 `http://127.0.0.1:8787`이다(`--host`, `--port`로 바꾼다). 시작할 때 모드·모델·허용 출처를 출력하고, mock 모드면 "자리표시자 결과가 나온다"고 경고한다.

**웹 데모에서 연결.** 화면 아래 "실제 케이스 분석" → "AI 연결"에서 "로컬 도우미"를 고르고 주소를 넣은 뒤 "연결 확인"을 누른다. 도우미가 실제 모델 호출에 실패해 자리표시자를 돌려주면 응답에 `"fallback": true`가 붙고, 웹은 그 결과로 고객을 추가하거나 판단을 바꾸지 않고 오류를 띄운다.

**보안 주의**

| 항목 | 동작 |
| --- | --- |
| 바인딩 | 기본 `127.0.0.1`. `--host`를 루프백 밖(예: `0.0.0.0`)으로 두면 경고를 출력한다. 인증이 없어 같은 네트워크의 누구나 이 PC의 구독·사내 토큰을 쓸 수 있으니 시연 중에만 쓴다 |
| 허용 출처 | 기본 `https://namojo.github.io`, `http://localhost`, `http://127.0.0.1`, `http://[::1]`(로컬은 포트 무관). `--allow-origin <출처>`(여러 번 가능)나 `CLAUSETOWER_ALLOWED_ORIGINS`(쉼표 구분)로 더한다 |
| 거절 | 목록 밖 출처(파일로 연 페이지의 `null` 포함)는 OPTIONS·GET·POST 모두 403이고 CORS 헤더를 붙이지 않는다. POST의 `Content-Type`이 `application/json`이 아니면 415. 동시 LLM 요청이 `max(4, CLAUSETOWER_CONCURRENCY)`를 넘으면 429. Origin 헤더가 없는 요청(`curl`)은 브라우저 밖이라 허용한다 |
| 계약서 본문 | 메모리에서만 다루고 디스크에 쓰지 않는다. 요청 로그에는 메서드와 경로만 남는다. 오류 응답에는 예외 이름과 필드 위치만 싣는다 |
| 키 보관(웹) | 웹 데모에 넣은 API 키·사내 토큰은 기본으로 그 탭(sessionStorage)에만 남고 탭을 닫으면 지워진다. "이 브라우저에 기억"을 켜면 localStorage에 남으며 같은 출처(namojo.github.io)의 다른 페이지와 저장소를 공유한다. 끝나면 "지움"을 누른다. 브라우저 직접 호출은 Anthropic이 `dangerous-direct-browser-access`로 표시한 방식이라 개인용·사용량 제한 키를 쓴다 |

2026-11-02에 mock 도우미로 확인한 응답: Origin 없음 200, `https://namojo.github.io` 200, `https://evil.example`·`null` 403, 허용 출처의 `text/plain` POST 415. 도우미 API의 구조는 [아키텍처](architecture.md)에 있다.

## 7. 검증 절차

모든 명령은 mock 모드이거나 저장된 보고서를 다시 채점하므로 과금이 없다. PowerShell에서도 명령은 같다(2절의 `$env:` 설정을 유지한 창에서).

```bash
python -m pytest -q                                    # 71 passed (Node가 없으면 JS 시험은 skipped)
python -m clausetower demo --llm mock                  # README 6절 정책 비교표가 그대로 나온다
python eval/run_eval.py robustness --seeds 30 --out out/eval
git diff --no-index --stat eval/results/robustness.json out/eval/robustness.json   # 출력이 없으면 추적 결과와 같다
python eval/run_eval.py extraction eval/results/real/report_typhoon.json
python eval/run_eval.py extraction eval/results/real/report_port_congestion.json
python scripts/build_site.py
node scripts/verify_engine.js                          # 36/36 checks passed (expected 36)
node scripts/smoke_web.js site/index.html out/smoke                                 # 선택: Playwright(2절), API는 가짜 응답
```

| 명령 | 기대값(2026-11-02 측정) |
| --- | --- |
| `pytest` | 71 passed, 측정 PC 약 76초 |
| `robustness` | 시나리오 3종 모두 30/30 승. 절감 평균 태풍 69.1%, 항만 적체 58.7%, 자사 WMS 장애 62.4%. 추적 중인 `eval/results/robustness.json`과 바이트 단위로 같다 |
| `extraction` 태풍 | 추출 0.953(106항목), 판단 필드 1.0(32항목), 고객 단위 적용 1.0, 인용 일치 1.0, 엄격 인용 1.0, 대체 0 |
| `extraction` 항만 적체 | 추출 0.953, 판단 필드 0.938, 고객 단위 적용 0.75, 인용 일치 1.0, 엄격 인용 1.0, 대체 0 |
| `verify_engine` | `36/36 checks passed (expected 36)` |

- `robustness`에 `--out`을 빼면 기본값이 추적 중인 `eval/results/`라 측정 기록을 덮어쓴다. 반드시 `--out out/eval`을 붙인다. `python -m clausetower eval`은 기본이 `out/eval`이다.
- 지표 이름(`judgment_accuracy`와 `applies_accuracy`, `citations_verbatim_rate`와 `citations_strict_rate`)의 차이는 [평가 방법](evaluation.md)에 있다.
- mock 모드의 추출 정확도 100%는 정답지를 그대로 쓰기 때문이라 의미가 없다. 실제 모델 수치는 저장된 보고서로만 확인한다.
- `smoke_web.js`는 측정 PC에 Playwright가 없어 이번 게이트에서 건너뛰었다. 출력 폴더를 `docs/screenshots/`로 주면 추적 중인 스크린샷을 덮어쓴다.
- 팀 PC에 하네스(`.claude/`)가 있으면 위 명령을 환경 보정과 함께 한 번에 돌린다: `python .claude/skills/ct-quality-gates/scripts/run_gates.py --out _workspace/qa_gates.json`(약 2분).

## 8. 문제 해결

| 증상 | 원인 | 해결 |
| --- | --- | --- |
| `No module named clausetower`, `tests/test_web.py` 6건 ERROR(Node가 없으면 2건) | 저장소 루트가 아닌 폴더에서 실행했거나 패키지 미설치(가상 환경 활성화 전 설치 포함) | 가상 환경을 켜고 `pip install -e ".[dev]"`. 급하면 그 창에서만 `PYTHONPATH=src` |
| `FileNotFoundError: ClauseTower 데이터 폴더 'contracts/'를 찾지 못했다` | 편집 설치가 아님(사이트 패키지에 복사됨) | 저장소 루트에서 `pip install -e .` 또는 `CLAUSETOWER_ROOT`에 저장소 루트 지정 |
| 로컬 도우미 `/health`가 502나 HTML 오류 페이지 | 사내 프록시가 127.0.0.1 요청을 가로챔(`NO_PROXY`에 127.0.0.1 없음) | `$env:NO_PROXY += ',127.0.0.1,localhost'`(bash는 `export NO_PROXY=…`). `pytest`는 스스로 보정한다 |
| `UnicodeEncodeError`, 콘솔이나 리디렉션한 파일의 한글이 깨짐 | 한국어 Windows 콘솔 인코딩 cp949 | `$env:PYTHONUTF8 = "1"` |
| `&&` 토큰이 올바른 문 구분 기호가 아니라는 PowerShell 오류 | Windows PowerShell 5.1 | 2절 PowerShell 블록처럼 한 줄씩, 또는 `;`로 잇는다 |
| `Activate.ps1`을 실행할 수 없음(스크립트 실행 정책) | PowerShell 실행 정책 | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` 뒤 다시 활성화 |
| `Cannot find module 'playwright'` | Playwright 미설치 또는 `NODE_PATH` 없음 | 2절 끝대로 설치하고 `NODE_PATH` 지정 |
| Playwright가 브라우저 실행 파일이 없다고 함 | Chromium 미설치 | 설치 폴더에서 `npx playwright install chromium` |
| `verify_engine.js`가 `MISSING out/demo/report_*.json` 또는 `llm_mode=… not mock` | mock 데모를 안 돌렸거나 실제 모드로 덮어씀 | `python -m clausetower demo --llm mock` 뒤 다시 |
| `verify_engine.js`가 `MISSING site/data.js` | 사이트 미조립 | `python scripts/build_site.py` |
| 로그에 `codex CLI를 찾지 못해 mock으로 전환한다.` | `codex` CLI 미설치 또는 PATH 밖 | Codex CLI 설치·로그인, 또는 `CLAUSETOWER_CODEX_BIN`에 경로 지정 |
| 로그에 `codex 종료 코드 1 (model_not_found)` | config.toml의 기본 모델을 이 계정(ChatGPT 로그인)이 지원하지 않음 | `CLAUSETOWER_CODEX_MODEL`에 계정이 지원하는 모델 지정. `codex exec -m <모델> "hi"`로 먼저 확인 |
| 로그에 `claude CLI를 찾지 못해 mock으로 전환한다.` | `claude` CLI 미설치 또는 PATH 밖 | CLI 설치·로그인, 또는 `CLAUSETOWER_CLAUDE_BIN`에 경로 지정. 전환된 실행의 숫자는 정답지 값이다 |
| `주의: --llm을 지정하지 않아 auto가 실제 LLM(…)을 골랐다` | `--llm` 생략, PC에 키나 CLI가 있음 | 비용 없이 보려면 `--llm mock` 또는 `CLAUSETOWER_LLM=mock` |
| `run.log`의 `fallbacks`나 보고서 `llm_fallbacks`가 0보다 큼 | 실제 모델 호출 실패(시간 초과, 인증, 출력 형식) | 도우미·CLI 로그(stderr)를 확인. 시간 초과면 `CLAUSETOWER_CLAUDE_TIMEOUT`을 늘린다 |
| 도우미가 403 "허용되지 않은 출처다" | 페이지 출처가 목록 밖(파일로 연 `null`, 사내 주소 등) | `python -m http.server 8000 --directory site`로 열거나 `serve --allow-origin <출처>` |
| 도우미가 415 | 요청 `Content-Type`이 `application/json`이 아님(직접 만든 클라이언트) | JSON으로 보낸다 |
| 도우미가 429 | 동시 LLM 요청이 상한(`max(4, CLAUSETOWER_CONCURRENCY)`) 초과 | 잠시 뒤 다시. 필요하면 `CLAUSETOWER_CONCURRENCY`를 올린다 |
| 웹에 "도우미의 실제 모델 호출이 실패해 자리표시…" | 도우미 응답에 `fallback: true` | 도우미 창의 로그 확인(CLI 로그인, 사내 주소·토큰) |
| `eval/results/`가 바뀌었다고 `git status`에 나옴 | `run_eval.py robustness`를 `--out` 없이 실행 | `git checkout -- eval/results` 뒤 `--out out/eval`로 다시 |

관련 문서: [README](../README.md), [3분 데모 대본](demo-script.md), [심사 예상 질문](judge-qa.md), [아키텍처](architecture.md), [평가 방법](evaluation.md).
