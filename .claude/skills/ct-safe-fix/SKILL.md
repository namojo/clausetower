---
name: ct-safe-fix
description: "사용자가 승인한 ClauseTower 구성 지적(설치·경로·인코딩·프록시·CORS·CI·시험·계산 엔진)을 출품작의 숫자와 설계 원칙을 지키며 최소 변경으로 고치는 방법. ct-fixer가 '승인 항목 적용', 'QA 미해결 항목 재수정'을 할 때 읽는다. 문서 문장 수정, 새 기능 개발, 승인되지 않은 리팩터링에는 쓰지 않는다."
---

# ClauseTower 안전 수정

해커톤 직전의 수정은 고친 문제보다 새로 만든 문제가 더 위험하다. 데모 숫자가 슬쩍 바뀌거나 웹 엔진과 파이썬이 갈라지면 문서·스크린샷·발표가 한꺼번에 틀린다. 그래서 범위를 승인 목록으로 묶고, 불변 조건을 먼저 확인한 뒤 고친다.

## 절차

1. `_workspace/03_approved.json`에서 `fix_owner: code`인 지적만 읽는다. 2라운드부터는 QA 보고서의 미해결·회귀 항목만 다룬다.
2. 지적마다 `repro`를 먼저 실행해 문제가 지금도 재현되는지 확인한다. 재현되지 않으면 고치지 않고 `skipped`(이미 해소)로 기록한다.
3. 아래 불변 조건 가운데 수정이 닿는 것을 확인한다.
4. 최소 변경으로 고친다. 지적 하나에 수정 하나가 대응하게 한다.
5. 가능하면 회귀 시험을 추가한다. 시험 이름에 무엇을 막는지 드러낸다.
6. 빠른 게이트로 확인한다: `python .claude/skills/ct-quality-gates/scripts/run_gates.py --only pytest verify_engine --out _workspace/04_fixer_gates_r{n}.json`
7. `_workspace/04_fixer_changes.md`에 라운드별로 기록한다.

## 불변 조건

| 불변 조건 | 깨지면 | 확인 방법 |
| --- | --- | --- |
| 돈 계산은 `exposure.py`의 결정적 코드가 한다. LLM은 읽기와 판단만 한다 | 출품작의 핵심 주장이 무너진다 | 계산 경로에 LLM 호출이 생기지 않았는지 diff 확인 |
| 면책 적용 = `has_clause ∧ event_covered ∧ notice_ok ∧ all(conditions_met)` | 모델 답이 그대로 금액을 바꾼다 | `extract.py`와 `engine.js`의 `deriveJudgment` 둘 다 확인 |
| `engine.js` ≡ 파이썬 계산·시뮬레이터 | 웹 데모 숫자가 문서·대시보드와 달라진다 | `verify_engine` 31/31(항목 수가 늘면 전부 통과) |
| mock 데모 숫자는 의도하지 않으면 바뀌지 않는다 | 문서·스크린샷·발표 숫자가 틀린다 | 게이트 `facts.scenarios_mock`을 기준선 `_workspace/01_qa_gates.json`과 비교 |
| `eval/results/`, `contracts/golden/`, `docs/screenshots/`는 측정·정답 기록이다 | 재현성 주장이 무너진다 | 지적이 명시하지 않으면 `git diff`에 나타나면 안 된다 |
| LLM 실패는 정답지로 대체하고 횟수를 보고서에 남긴다 | 데모가 네트워크 장애에 멈춘다 | mock 데모와 서버 시험 통과 |
| 표준 라이브러리 + `pydantic`, `pyyaml`, `anthropic`만으로 돈다 | 심사위원 PC 설치가 무거워진다 | `pyproject.toml` 의존성 변화 확인 |

## 수정 유형별 지침

승인된 지적에 해당할 때만 적용한다. 지적의 `fix`와 다르면 지적의 `fix`를 우선하되, 불변 조건과 충돌하면 고치지 말고 `skipped`로 두고 이유를 적는다.

| 유형 | 지침 |
| --- | --- |
| 로컬 도우미 CORS | 출처를 반사하지 말고 허용 목록으로 판정한다. 기본 목록은 배포 출처(`https://namojo.github.io`)와 로컬 개발 출처(`http://localhost:*`, `http://127.0.0.1:*`, `file://`의 `null`)로 두고, 사내 출처는 옵션·환경 변수로 추가한다. 목록 밖 출처에는 CORS·PNA 허용 헤더를 붙이지 않고 POST를 거부한다. 허용·거부 시험을 함께 추가한다 |
| 바인딩 노출 | 기본은 127.0.0.1을 유지한다. 외부 바인딩 옵션에는 실행 시 경고를 출력한다 |
| 시험의 프록시 의존 | 로컬 서버에 붙는 시험은 `urllib.request.build_opener(urllib.request.ProxyHandler({}))`처럼 프록시를 우회하는 오프너를 쓴다. 전역 환경 변수를 바꾸지 않는다 |
| 미설치 실행 | 시험의 하위 프로세스는 `PYTHONPATH`에 `src`를 넣거나 `sys.executable -m`과 함께 `env`를 명시한다. 설치를 전제로 한다면 README와 시험 실패 메시지에 그 사실을 드러낸다 |
| 저장소 루트 경로 | `Path(__file__).parents[n]` 대신 패키지 자원(`importlib.resources`)으로 옮기거나, 루트를 찾지 못했을 때 무엇을 해야 하는지 알려 주는 오류를 낸다. `package-data` 경로를 실제 위치와 맞춘다. 데이터 파일을 옮기면 `build_site.py`, `run_eval.py`, 시험의 경로도 함께 확인한다 |
| 콘솔 인코딩 | CLI 진입점에서 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`를 시도한다(실패해도 무시). 파일 쓰기는 항상 `encoding="utf-8"` |
| CI | 시험 실패 시 배포가 막히는 순서를 유지한다. 권한은 필요한 작업에만, 같은 브랜치 동시 배포는 `concurrency`로 막는다. 브라우저 스모크를 넣는다면 Playwright 설치 단계와 캐시를 함께 넣는다 |
| LLM 대체의 가시성 | 실제 모드에서 대체가 일어나면 보고서·대시보드·서버 응답에 대체 횟수와 대상이 드러나게 한다. 대체 동작 자체는 유지한다 |
| 외부 스크립트 | 버전 고정 URL에 `integrity`와 `crossorigin`을 붙인다. 해시는 실제 파일에서 계산한다 |

## 변경 기록 형식

`_workspace/04_fixer_changes.md`에 라운드마다 덧붙인다.

```markdown
## 라운드 {n}

| 지적 ID | 상태 | 변경 파일 | 추가·수정 시험 | 메모 |
| --- | --- | --- | --- | --- |
| runtime-2 | fixed | src/clausetower/server.py | tests/test_server_and_openai.py::test_cors_allowlist | 허용 목록 기본값과 --allow-origin 옵션 |

**실행한 확인:** `run_gates.py --only pytest verify_engine` → pytest 41 passed, verify_engine 31/31

**문서 영향:** README 5-5절과 docs/setup-guide.md에 `--allow-origin` 옵션 설명 필요. mock 숫자 변화 없음.

**발견했지만 고치지 않은 것:** (승인 목록 밖) ...
```

## 하지 않는 것

- 커밋·푸시·브랜치 생성. 사용자가 diff를 보고 결정한다.
- 승인 목록 밖의 리팩터링, 포매팅 일괄 변경, 의존성 업그레이드.
- 시험을 통과시키려고 단언을 느슨하게 바꾸거나 측정 기록을 고치는 것.
- 실제 LLM 호출로 확인하는 것. mock과 가짜 응답 시험으로 확인한다.
