---
name: ct-quality-gates
description: "ClauseTower의 검증 명령(pytest, mock 데모, 웹 사이트 조립, JS≡Python 엔진 대조, 다중 시드 견고성, 실제 모델 보고서 채점, 브라우저 스모크)을 환경 보정과 함께 한 번에 실행하고 측정값을 JSON으로 남긴다. ClauseTower 테스트 실행, 기준선 측정, 수정 후 회귀 확인, 문서에 쓸 숫자 재측정, '게이트 돌려줘', '테스트 다 통과해?', '숫자 다시 재 줘' 요청에 사용한다. 실제 LLM으로 계약을 다시 읽히는 재측정(scripts/real_run.py, 과금 발생)에는 사용하지 않는다."
---

# ClauseTower 품질 게이트

문서의 숫자와 "재현된다"는 주장은 모두 이 게이트의 측정값에 기대야 한다. 사람이 명령을 하나씩 돌리면 환경 보정을 빠뜨리거나 추적 중인 측정 파일을 덮어쓰기 쉬우므로, 항상 `scripts/run_gates.py`로 실행한다.

## 실행

```bash
# 전체(약 2분). 결과 JSON과 같은 이름의 폴더에 견고성 결과·스모크 캡처가 생긴다
python .claude/skills/ct-quality-gates/scripts/run_gates.py --out _workspace/01_qa_gates.json

# 일부만(의존 게이트는 자동 포함: verify_engine → demo, build_site / smoke_web → build_site)
python .claude/skills/ct-quality-gates/scripts/run_gates.py --only pytest verify_engine --out _workspace/04_qa_gates_r1.json
```

종료 코드 0이면 실행한 게이트가 모두 통과했다. 건너뛴 게이트(`ok: null`)는 실패로 세지 않는다.

## 게이트

| 게이트 | 명령 | 확인하는 것 |
| --- | --- | --- |
| `pytest` | `python -m pytest -q` | 계산기·시뮬레이터·대시보드·서버·웹 조립 시험 |
| `demo` | `python -m clausetower demo --llm mock --out out/demo` | 3개 시나리오가 끝까지 돌고 정책별 총 배상금이 나온다(결정적) |
| `build_site` | `python scripts/build_site.py` | `site/` 정적 웹 데모 조립 |
| `verify_engine` | `node scripts/verify_engine.js` | 브라우저 엔진이 파이썬과 같은 총 배상금·순위를 낸다 |
| `robustness` | `python eval/run_eval.py robustness --seeds 30 --out <결과 폴더>/robustness` | 시드 30개 × 3 시나리오 승률·절감률. 추적 중인 `eval/results/robustness.json`과 같은지 비교 |
| `extraction` | `python eval/run_eval.py extraction eval/results/real/report_*.json` | 저장된 실제 모델 보고서의 추출·판단 정확도(재호출 없음) |
| `smoke_web` | `node scripts/smoke_web.js site/index.html <폴더>` | Playwright 브라우저 스모크(가짜 API 응답). Playwright가 없으면 건너뜀 |

실행 전후 `git status`를 비교해 게이트가 추적 중인 파일을 바꾸면 `no_tracked_changes` 실패로 표시한다.

## 환경 보정과 진단

스크립트는 게이트를 돌릴 때 아래를 적용하고, 보정하지 않은 원래 환경의 상태를 `env`에 따로 기록한다. 보정 덕분에 통과했더라도 `env` 경고는 심사위원 PC에서 실제로 생길 문제이므로 검토자가 다룬다.

| 보정 | 이유 | `env` 진단 키 |
| --- | --- | --- |
| `PYTHONPATH=src` | `pip install -e .` 없이도 `python -m clausetower`가 돈다 | `package_installed` |
| `PYTHONUTF8=1` | 한국어 Windows 콘솔(cp949)에서 출력 인코딩 오류 방지 | `raw_stdout_encoding` |
| `NO_PROXY`에 `127.0.0.1,localhost` 추가 | 사내 프록시가 로컬 도우미·서버 시험 요청을 가로채 HTML 오류 페이지를 돌려준다 | `loopback_through_proxy_risk` |
| `CLAUSETOWER_LLM=mock` | 네트워크·과금 없이 결정적으로 돈다 | – |

## 결과 JSON 읽는 법

- `summary.ok`, `summary.failed`, `summary.skipped`: 전체 판정.
- `gates.<이름>.tail`: 실패 시 출력 끝 40줄. `gates.pytest.failing`은 실패한 시험 ID.
- `facts`: 문서에 쓰는 측정값의 1차 출처.

| `facts` 키 | 문서에서 뒷받침하는 주장 |
| --- | --- |
| `tests_passed` | "시험 N개 통과" |
| `scenarios_mock.<sid>.policies.<정책>.total_penalty_krw`, `late_count` | 정책 비교표, 기존 대비 금액, 지연 건수 |
| `scenarios_mock.<sid>.savings_vs_deadline_pct` | "절감 76.7%" 같은 시나리오별 절감률 |
| `scenarios_mock.<sid>.ranking_at_h`, `ranking_rows`, `rank_moves_ge3` | "+15.9시간, 대기 45건, 32건이 3계단 이상" |
| `scenarios_mock.<sid>.per_customer_krw` | 고객별 배상금 표 |
| `engine_parity` | "웹 엔진 31/31 일치" |
| `robustness.scenarios.<sid>` | "30/30 승, 평균·최소·최대 절감률" |
| `real_model_scores.<sid>` | 실제 모델 추출·판단 정확도, 인용 일치율. `judgment_accuracy`는 판단 필드 단위, `applies_accuracy`는 고객 단위 최종 적용 여부라 서로 다른 지표다 |
| `counts` | 계약서·정답지·시나리오·문서·스크린샷 수 |

정책 키: `deadline_first`(마감 임박 순, 기존), `fifo`(도착 순), `value_first`(고액 화물 순), `exposure_first`(배상 노출 순, ClauseTower), `exposure_abs`(배상 노출 순 절대값), `search_best`(탐색 근사 최적, 참고).

실제 모델의 호출 횟수·비용·시간은 게이트가 다시 재지 않는다. `eval/results/real/run.log`, `eval/results/real_prev/run.log`가 출처다.

## 실패 해석

| 증상 | 원인 후보 | 판단 |
| --- | --- | --- |
| `No module named clausetower` | 패키지 미설치, `PYTHONPATH` 없음 | 환경. 스크립트 밖 원래 환경에서 재현되면 문서·설정으로 막을 문제 |
| 서버 시험이 HTML 본문과 함께 실패 | 프록시가 127.0.0.1 요청을 가로챔 | 환경. 시험 코드가 프록시를 우회하지 않는 것은 코드 문제 후보 |
| `UnicodeEncodeError`, 깨진 한글 출력 | cp949 콘솔 | 환경. CLI가 출력 인코딩을 보정하지 않는 것은 코드 문제 후보 |
| `verify_engine`에 `DIFF` | 파이썬과 JS 계산이 갈라짐 | 코드 결함. 블로커 |
| `robustness.matches_tracked_results: false` | 계산·시드 처리 변경 | 의도한 변경이면 문서·추적 파일 갱신 필요, 아니면 회귀 |
| `scenarios_mock` 숫자가 기준선과 다름 | 계산·시뮬레이터 변경 | 의도한 변경인지 변경 기록과 대조 |
| `no_tracked_changes` 실패 | 게이트나 수정이 측정 기록을 덮어씀 | 회귀. 덮어쓴 파일을 확인 |

## 지키는 것

- 게이트를 통과시키려고 시험이나 `eval/results/`를 고치지 않는다. 측정 기록을 고치면 재현성 주장이 무너진다.
- 실제 LLM 재측정(`scripts/real_run.py`, `--llm claude-code|anthropic|openai`)은 1회 약 $2와 5분이 들므로 사용자가 요청할 때만 실행한다.
- 결과 JSON은 `_workspace/` 아래에 둔다. 저장소 첫 화면에 남기지 않는다.
