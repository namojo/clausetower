---
name: clausetower-hackathon
description: "ClauseTower 해커톤 준비 하네스의 오케스트레이터. 저장소의 시스템 구성(설치·재현성·패키징·CI·보안·LLM 연동·계산 엔진 정합성)과 문서를 관점별로 검토·적대적 검증하고, 사용자가 승인한 문제를 고친 뒤 QA로 확인하고, 해커톤용 상세 문서(README, 기획서, 양식 답안, 데모 대본, 설치 가이드, 아키텍처, 평가 방법, 심사 예상 질문, 2일 계획)를 측정값 근거로 작성·사실 검증한다. '해커톤 준비', '해커톤 점검', '심사 전 점검', '시스템 구성 검토', '출품작 검토', '해커톤 문서 만들어줘', '문서 상세화', '검토만 다시', 'security만 다시 검토', '승인한 것 적용', '개선 적용', '문서만 다시', 'README만 다시', '이전 결과를 바탕으로 보완', '최종 점검', '다시 실행' 요청에 사용한다. 테스트만 돌리는 요청은 ct-quality-gates, 단일 버그 수정이나 기능 개발, 실제 LLM 재측정(scripts/real_run.py)에는 사용하지 않는다."
---

# ClauseTower 해커톤 준비 오케스트레이터

출품작이 심사위원 PC에서 그대로 돌고, 데모가 끝까지 가고, 문서의 숫자가 맞고, 위험한 노출이 없는 상태를 만든다. 검토 → 승인 → 수정·QA → 문서화 → 최종 점검 순서로 진행한다. 사용자가 이 스킬을 불러오면 `Workflow` 사용에 동의한 것으로 본다.

## 실행 모드: 혼합

| 단계 | 실행 모드 | 선택 이유 |
| --- | --- | --- |
| 0. 기존 작업 확인 | 메인 직접 | `_workspace/` 상태로 처음·부분·재실행을 가른다 |
| 1. 기준선 측정 | 메인 직접(스크립트) | 결정적 스크립트라 에이전트가 필요 없다 |
| 2. 검토·적대적 검증 | 워크플로(`workflows/review.js`) | 관점 목록·검증 규칙·다수결을 코드로 정할 수 있다 |
| 3. 승인 | 메인 + 사용자 | 출품 코드를 바꾸는 결정은 사용자의 몫이다 |
| 4. 수정·QA 반복 | 워크플로(`workflows/fix.js`) | 수정 → 검사 → 재수정 반복 조건을 코드로 정할 수 있다 |
| 5. 문서화·사실 검증 | 워크플로(`workflows/docs.js`) | 문서 목록을 미리 정하고 문서마다 작성 → 검증 → 보완을 파이프라인으로 돌린다 |
| 6. 최종 점검·보고 | 메인 직접 | 게이트 재실행과 결과 정리 |

## 에이전트 구성

| 역할 | `agentType` | 모델 | 스킬 | 반환 |
| --- | --- | --- | --- | --- |
| 관점별 검토 | `ct-config-reviewer` | opus | `ct-config-review`, `ct-quality-gates` | `{findings[], checked[]}` |
| 적대적 검증·문서 사실 검증·교차 검토 | `ct-verifier` | opus | `ct-config-review`, `ct-hackathon-docs` | `{verdicts[]}` / `{issues[]}` |
| 승인 항목 수정 | `ct-fixer` | opus | `ct-safe-fix`, `ct-quality-gates` | `{items[], tests_run}` |
| 게이트·회귀 확인 | `ct-qa` | sonnet | `ct-quality-gates` | `{gates_ok, resolved[], unresolved[], regressions[]}` |
| 문서 작성·보완 | `ct-doc-writer` | opus | `ct-hackathon-docs` | `{path, status, sources_used[], open_questions[]}` |

## 작업 공간

모든 중간 산출물은 저장소 루트의 `_workspace/`(gitignore 대상)에 둔다. 최종 산출물은 저장소 파일(코드 수정, `README.md`, `docs/*.md`)이다.

| 파일 | 만드는 쪽 | 내용 |
| --- | --- | --- |
| `00_input.md` | 메인 | 요청 원문, 범위, 사용자 관심사 |
| `01_qa_gates.json` | 메인(스크립트) | 기준선 게이트 결과와 `facts` |
| `02_review_findings.json` | 메인 | `review.js` 반환값 그대로 |
| `02_review_report.md` | 메인 | 사용자 승인용 표 |
| `03_approved.json` | 메인 | 승인한 지적과 문서 목록 |
| `04_fixer_changes.md` | ct-fixer | 라운드별 변경 기록과 문서 영향 |
| `04_fixer_gates_r{n}.json`, `04_qa_gates_r{n}.json` | ct-fixer, ct-qa | 수정 후 게이트 결과 |
| `04_fix_result.json` | 메인 | `fix.js` 반환값 |
| `05_docs_result.json` | 메인 | `docs.js` 반환값 |
| `06_qa_gates_final.json`, `06_final_report.md` | 메인 | 최종 게이트와 보고서 |
| `run_meta.json` | 메인 | 워크플로 실행 기록 `{runs: [{stage, runId, scriptPath, args, status}]}` |

워크플로 스크립트는 파일 시스템에 쓸 수 없으므로, 반환값은 메인이 받아 위 경로에 저장한다.

## 작업 절차

### 0단계: 기존 작업 확인

**실행 모드:** 메인 직접

1. `_workspace/`가 없으면 1단계부터 전부 실행한다.
2. 있으면 요청을 다음과 같이 나눈다.

| 요청 | 할 일 |
| --- | --- |
| "검토만 다시", "{관점}만 다시 검토" | 1단계 후 2단계를 `dimensions`를 좁혀 실행하고 `priorFindingsPath: _workspace/02_review_findings.json`을 넘긴다 |
| "승인한 것 적용", "개선 적용", "{id} 고쳐줘" | `03_approved.json`이 없으면 3단계, 있으면 4단계부터 |
| "문서만 다시", "{문서}만 다시" | 5단계를 그 문서만으로 실행한다 |
| "최종 점검" | 6단계 |
| "처음부터 다시", 새 해커톤 라운드 | `_workspace/`를 `_workspace_{YYYYMMDD-HHMM}/`로 옮기고(시각은 `date +%Y%m%d-%H%M`) 1단계부터 |

3. `run_meta.json`에 `status: running`으로 끝난 실행이 있으면 같은 `scriptPath`와 `resumeFromRunId`로 재개할 수 있다. 바뀌지 않은 `agent()` 호출은 캐시 결과를 즉시 돌려준다.

### 1단계: 기준선 측정

**실행 모드:** 메인 직접(스크립트)

```bash
python .claude/skills/ct-quality-gates/scripts/run_gates.py --out _workspace/01_qa_gates.json
```

약 2분 걸린다. 종료 코드가 1이어도 멈추지 않는다. 실패한 게이트와 `env` 경고는 검토 단계의 입력이다. 요청 원문과 범위를 `_workspace/00_input.md`에 적는다.

### 2단계: 검토와 적대적 검증

**실행 모드:** 워크플로 조율

`Workflow`에 `scriptPath`로 `.claude/skills/clausetower-hackathon/workflows/review.js`의 절대 경로를 넘긴다.

| `args` 키 | 기본값 | 설명 |
| --- | --- | --- |
| `dimensions` | `["runtime","security","engine","docs"]` | 검토 관점 |
| `factsPath` | `_workspace/01_qa_gates.json` | 기준선 |
| `priorFindingsPath` | 없음 | 재검토 시 이전 지적 목록 |
| `focus` | 없음 | 사용자가 특히 보라고 한 점 |
| `thorough` | `false` | `true`면 지적마다 렌즈 3개(reproduce·counter-evidence·impact)로 검증하고 2표 이상 `confirmed`만 확정 |
| `roleFromFile` | `false` | `true`면 사용자 정의 유형 대신 기본 워크플로 에이전트가 `.claude/agents/{type}.md`를 읽어 역할을 불러온다. 세 워크플로 모두 같은 키를 받는다(오류 처리 표 참고) |

- 규모: 기본은 검토 4명 + 검증 4명(관점별 일괄 검증)으로 에이전트 8명이다. 사용자가 "철저히", "전수", "꼼꼼히"를 요청할 때만 `thorough: true`(검토 4명 + 지적 수 × 3명)로 바꾸고, 시작 전에 예상 규모를 알린다.
- 실행 후 `runId`와 `scriptPath`를 `run_meta.json`에 기록하고 완료 알림을 기다린다. 알림 전에 결과를 단정하지 않는다.
- 반환값을 `_workspace/02_review_findings.json`에 저장한다. `failed_dimensions`가 있으면 보고서에 밝힌다.

### 3단계: 사용자 승인

**실행 모드:** 메인 + 사용자

1. `_workspace/02_review_report.md`를 만든다: 확정 지적을 심각도 순으로 표(ID, 제목, 심각도, 종류, 수정 담당, 노력, 검증 이유 한 줄)로 정리하고, 보류(`uncertain`) 지적과 기각 수를 따로 적는다. `fix_owner: user` 지적은 "사용자 조치 필요"로 분리한다.
2. 표를 사용자에게 보여 준 뒤 `AskUserQuestion`으로 묻는다. 질문만 보고도 판단할 수 있게 확정 건수와 심각도 분포를 질문에 넣는다.
   - 코드 수정 범위: "blocker·high + 노력 S인 medium (권장)" / "blocker·high만" / "확정 전부" / "고치지 않음". 특정 ID는 "Other"로 받는다.
   - 문서 범위: "지적된 문서 + P1 문서 (권장)" / "문서 9종 전부" / "지적된 문서만" / "문서 작업 안 함". P1·P2 구분은 `ct-hackathon-docs/references/doc-catalog.md`.
3. 승인 결과를 `_workspace/03_approved.json`에 쓴다.

```json
{
  "approved": [ { "...확정 지적 객체 그대로": "..." } ],
  "docs": [ { "path": "docs/setup-guide.md", "mode": "create", "brief": "작성 지시", "findings": ["docs-3"] } ],
  "deferred": ["보류·미승인 지적 ID"],
  "user_actions": ["fix_owner가 user인 지적 ID"]
}
```

`docs` 목록 만드는 법: 승인한 `docs` 지적을 파일별로 묶어 `update`로, `doc-gap` 지적과 사용자가 고른 미작성 문서를 `create`로 넣는다. `brief`에는 지적의 `fix`와 문서 목록 명세의 「갱신 초점」을 합쳐 적는다. 새 문서가 생기면 README를 반드시 `update` 목록에 넣는다(문서 링크).

### 4단계: 수정과 QA

**실행 모드:** 워크플로 조율. 승인한 `code` 지적이 없으면 건너뛴다.

`Workflow`에 `workflows/fix.js`의 절대 경로를 넘긴다. `args`: `{approvedPath: "_workspace/03_approved.json", baselinePath: "_workspace/01_qa_gates.json", maxRounds: 2}`.

- 수정자 1명과 QA 1명이 라운드마다 번갈아 일한다(최대 4명, `maxRounds` 상한 3).
- 반환값을 `_workspace/04_fix_result.json`에 저장한다. `done: false`면 남은 미해결·회귀 항목을 6단계 보고서에 넣는다.
- 파일을 동시에 고치는 에이전트가 없으므로 `isolation: 'worktree'`는 쓰지 않는다.

### 5단계: 문서화와 사실 검증

**실행 모드:** 워크플로 조율. 승인한 문서가 없으면 건너뛴다.

시작 전에 예상 규모(문서 수 × 2~3명 + 교차 검토 1명)를 사용자에게 알린다. `Workflow`에 `workflows/docs.js`의 절대 경로를 넘긴다.

| `args` 키 | 값 |
| --- | --- |
| `docs` | `03_approved.json`의 `docs` 배열(지적 ID 대신 지적 객체를 넣는다) |
| `factsPath` | 4단계를 했으면 `04_fix_result.json`의 `gates_path`, 아니면 `_workspace/01_qa_gates.json` |
| `changesPath` | 4단계를 했으면 `_workspace/04_fixer_changes.md` |

- 반환값을 `_workspace/05_docs_result.json`에 저장한다.
- `cross_issues`에 `error`·`misleading`이 있으면 해당 문서만 `docs.js`를 한 번 더 돌린다(`brief`에 문제를 넣는다). `nit`과 `open_questions`는 보고서에 나열한다.

### 6단계: 최종 점검과 보고

**실행 모드:** 메인 직접

1. `python .claude/skills/ct-quality-gates/scripts/run_gates.py --out _workspace/06_qa_gates_final.json`
2. `git status --short`와 `git diff --stat`으로 바뀐 파일을 모은다.
3. `_workspace/06_final_report.md`를 쓴다: 게이트 결과(기준선 대비), 고친 지적, 남은 지적(미승인·보류·미해결), 사용자 조치 필요 항목, 작성·갱신한 문서와 남은 질문, 바뀐 숫자.
4. 사용자에게 요약해 보고한다. **커밋·푸시는 하지 않는다.** 사용자가 diff를 검토한 뒤 결정한다.

## 오류 처리

| 상황 | 대응 |
| --- | --- |
| 게이트 스크립트 자체가 실행되지 않음 | 출력 끝부분을 사용자에게 보이고, Python 경로·저장소 루트를 확인한 뒤 한 번 다시 실행한다 |
| `agent type 'ct-…' not found`로 모든 에이전트가 즉시 실패 | 에이전트 정의를 만들거나 고친 세션에서는 레지스트리에 아직 올라가지 않았다. 같은 `args`에 `roleFromFile: true`를 더해 다시 실행한다(토큰을 쓰기 전에 실패하므로 재개할 것이 없다). 새 세션에서는 기본값으로 돌린다 |
| 관점 하나의 검토가 `null` | `failed_dimensions`에 남는다. 그 관점만 `dimensions`로 좁혀 한 번 다시 실행하고, 또 실패하면 보고서에 "검토 못 함"으로 적는다 |
| 검증 판정 누락 | 스크립트가 `uncertain`으로 둔다. 승인 표에 "검증 못 함"으로 표시하고 기본 승인 범위에서 뺀다 |
| 수정 라운드가 상한에 도달 | 남은 항목을 사용자에게 넘긴다. 수정자가 `skipped`로 둔 불변 조건 충돌은 설계 결정이 필요한 항목으로 따로 보고한다 |
| QA 회귀 발견(측정 파일 변경, mock 숫자 변화) | 다음 라운드로 넘기되, 라운드가 끝나도 남으면 해당 변경 파일과 diff를 보고하고 되돌릴지 사용자에게 묻는다. 메인이 임의로 되돌리지 않는다 |
| 문서 작성 실패·검증 누락 | `failed`·`unchecked`에 남는다. 해당 문서만 한 번 다시 실행하고, 또 실패하면 보고서에 적는다 |
| 사용량 한도·인증 만료·권한 거부 | 다시 시도하지 않는다. `journal`과 `_workspace/`를 열어 실제 진행 범위를 확인하고, 누락 내용을 `_workspace/`에 기록해 보고한다. 한도라면 풀리는 시각을 알리고, 풀린 뒤 `resumeFromRunId`로 재개한다 |
| 결과가 비어 있음 | 성공으로 판단하지 않는다. 워크플로 `journal.jsonl`에서 각 에이전트의 실제 반환값을 확인한다 |
| 측정값이 서로 다름(게이트 vs 추적 파일) | 어느 쪽도 지우지 않고 두 값과 출처를 보고서에 나란히 적는다 |

메인은 에이전트가 남긴 빈칸을 채울 때 직접 확인한 사실만 반영한다. 에이전트의 판단(왜 기각했는지 등)은 추측해 채우지 않는다.

## 테스트 시나리오

### 정상 흐름

1. 사용자: "해커톤 전에 clausetower 점검하고 문서 정리해 줘."
2. 0단계: `_workspace/` 없음 → 1단계 게이트 실행, `01_qa_gates.json` 생성(시험 39개 통과, 엔진 31/31, `env` 경고 3건).
3. 2단계: `review.js` 기본 실행(에이전트 8명) → 확정 지적 N건을 `02_review_findings.json`에 저장.
4. 3단계: 승인표를 보이고 "blocker·high + S medium", "지적된 문서 + P1"을 받아 `03_approved.json` 작성.
5. 4단계: `fix.js` 1라운드에 QA 통과 → `04_fix_result.json`의 `done: true`.
6. 5단계: 문서 6종으로 `docs.js` 실행 → 사실 검증 문제 있는 2종만 보완, 교차 검토 `nit` 2건.
7. 6단계: 최종 게이트 통과, `06_final_report.md` 작성, 커밋하지 않고 보고.

### 오류 흐름

1. 2단계에서 `security` 검토 에이전트가 결과 없이 끝나 `failed_dimensions: ["security"]`가 돌아온다.
2. 메인은 `dimensions: ["security"]`, `priorFindingsPath`로 한 번 다시 실행한다.
3. 다시 실패하면 승인표 맨 위에 "security 관점 검토 못 함"을 적고 나머지 관점으로 3단계를 진행한다.
4. 4단계에서 QA가 `eval/results/robustness.json` 변경을 회귀로 보고하고 2라운드에도 남으면, 메인은 diff를 보여 주고 되돌릴지 사용자에게 묻는다.

### 부분 재실행 흐름

1. 사용자: "README랑 setup-guide만 다시 써 줘."
2. 0단계: `_workspace/03_approved.json`이 있으므로 그 `docs`에서 두 문서만 골라 5단계 `docs.js`를 실행한다. `factsPath`는 가장 최근 게이트 결과를 쓴다.
