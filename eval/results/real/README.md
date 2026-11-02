# 실제 모델 실행 보고서

이 폴더는 실제 모델 2회차(현재) 측정 기록이다. 1회차(프롬프트 수정 전) 보고서와 채점은 `../real_prev/`에 그대로 두었다. 숫자의 해석은 [README 6절](../../../README.md), 지표 정의와 재현 방법은 [평가 방법](../../../docs/evaluation.md)에 있다. 이 폴더와 `../real_prev/`의 json·log는 측정 기록이라 고치지 않는다.

## 파일

- `report_*.json`: `claude-code` 모드(claude-opus-5-5)로 계약서 8부를 읽고 두 시나리오의 면책을 판단한 보고서. 2회차(추출 프롬프트의 "지연 페널티 조건"을 "지연 배상 조건"으로 고친 뒤 실행). 실행 직후 그대로 두었고 `--resim`을 거치지 않았다. 그래서 기존·ClauseTower 총액(`policies.deadline_first`·`exposure_first`)이 `run.log` 시나리오 줄의 `base=`·`ours=`와 같다. 2회차 `run.log`에는 정책 이름이 없어 이름은 대조할 수 없다.
  - 태풍 상륙: 마감 임박 순(기존) 12,834,000원 → 배상 노출 순(ClauseTower) 2,996,500원, 76.7%
  - 항만 적체: 8,925,000원 → 3,213,500원, 64.0%
- `run.log`: 원 실행 기록. 실행에 쓴 스크립트의 표준 출력이지만 지금 저장소의 `scripts/real_run.py`와 출력 형식이 다르다(시나리오 줄에 `base=`·`ours=`가 있고 agent_log 줄이 없다). 어느 버전의 스크립트였는지는 확인 필요. 호출 24회(추출 8 + 판단 16), 대체 0회, CLI 보고 비용 $2.06, 호출 시간 합계 283초(4개 병렬), 시나리오별 경과 70초 + 31초. 시나리오 줄의 `calls`·`cost`는 누적값이다. 태풍 줄의 16회·$1.78은 추출 8회와 태풍 판단 8회이고, 항만 적체는 추출을 재사용해 판단 8회만 더했다. 마지막 줄의 JSON이 전체 합계다(입력 토큰 459,771, 출력 토큰 28,740).
- 채점 파일은 이 폴더가 아니라 한 단계 위 `../extraction_typhoon.json`, `../extraction_port_congestion.json`에 있다.

## 채점 파일의 출처

추적 중인 채점 파일(`../extraction_*.json`)은 `out/real_v2/report_*.json`을 `eval/run_eval.py extraction` 하위 명령으로 채점해 `--save`로 저장한 것이다(`report` 필드에 채점한 보고서 경로가 그대로 기록된다, `eval/run_eval.py`의 `"report": str(report_path)`). `--save`가 없으면 화면에 출력만 하고 파일을 쓰지 않는다. 아래는 추적 파일을 덮어쓰지 않는 재현 명령이다.

```bash
# 이 폴더의 보고서를 다시 채점해 out/ 아래에 저장(out/ 폴더가 있어야 한다)
python eval/run_eval.py extraction eval/results/real/report_typhoon.json --save out/extraction_typhoon.json
python eval/run_eval.py extraction eval/results/real/report_port_congestion.json --save out/extraction_port_congestion.json
```

- 채점 파일의 `report` 필드(`out/real_v2/report_*.json`)는 채점 당시의 보고서 경로다. 그 보고서가 이 폴더의 `report_*.json`이며 `out/real_v2/`는 저장소에 없다.
- 다시 확인할 때는 추적 파일을 덮어쓰지 말고 화면 출력만 보거나 `out/` 아래에 저장한다(예: `--save out/extraction_typhoon.json`, `out/` 폴더가 있어야 한다). 2026-11-02에 다시 채점한 결과는 `report` 경로와 그 뒤에 추가된 키 두 개(`llm_fallbacks` 0, `citations_strict_rate` 1.0)를 빼면 추적 파일과 같았다.

## 1회차(`../real_prev/`)의 로그와 보고서가 다른 이유

`../real_prev/run.log`와 `../real_prev/report_*.json`은 정책 이름과 총액이 다르다. 보고서는 정책 정의를 바꾼 뒤 `python -m clausetower demo --from-reports <폴더> --resim`으로 시뮬레이션만 다시 돌렸고, LLM 결과(계약 조건 추출, 면책 판단)는 그대로다. 로그는 원 실행 기록이라 바꾸지 않았다. `--resim`은 보고서 파일을 제자리에서 덮어쓰므로 추적 폴더에 직접 돌리지 않는다.

| 시나리오 | `../real_prev/run.log`(원 실행) | `../real_prev/report_*.json`(재시뮬레이션) |
| --- | --- | --- |
| 태풍 상륙 | 절감 76.8%. 옛 이름 `물리는 순서(ClauseTower)` 2,979,000원은 지금의 배상 노출 순(절대값 변형)에 해당 | 절감 76.7%. 배상 노출 순(ClauseTower) 2,996,500원 |
| 항만 적체 | 절감 72.5%. 옛 이름 `물리는 순서(ClauseTower)` 2,224,500원은 지금의 배상 노출 순(절대값 변형)에 해당하고, 지금의 배상 노출 순 2,083,500원은 로그의 `물리는 순서(시간당 변형)`와 같다 | 절감 74.3%. 배상 노출 순(ClauseTower) 2,083,500원 |

- 마감 임박 순(기존)·도착 순·고액 화물 순의 총액은 로그와 보고서가 같다.
- 보고서의 `agent_log` 끝 줄에 "시뮬레이션 비교(재실행)"와 "LLM 결과는 원 실행(claude-code, N회)을 그대로 사용"이 남아 있다. `generated_at`(2026-10-29)은 재시뮬레이션한 시각이다.
- 1회차 채점 파일(`../real_prev/extraction_*.json`)의 `report` 필드는 원 실행 경로(`out/real/<시나리오>/report.json`)다. 재시뮬레이션은 LLM 결과를 바꾸지 않으므로 채점 값과 무관하다.

## 측정 조건과 한계

- 이 폴더와 `../real_prev/`의 실제 모델 수치는 모두 프롬프트에 주입 방어 규칙을 넣기 **전**에 잰 값이다. 그 뒤 `prompts/extract.md`·`prompts/judge.md`에 계약서 본문(`<contract>` … `</contract>`) 속 지시를 따르지 않는 규칙이 들어갔고, 본문을 `<contract>`로 감싸 넘기게 바뀌었다. `claude` 호출 인자에도 `--tools ""`, `--strict-mcp-config`가 추가됐다(`src/clausetower/llm.py`). 바뀐 뒤로는 다시 재지 않았다([README 6절 프롬프트 변경 이력](../../../README.md)).
- 한 모델(claude-opus-5-5)로 회차마다 한 번씩, 두 번 실행한 값이다. 같은 프롬프트로 반복했을 때의 편차는 재지 않았다.
- 정답지는 팀이 작성했고 계약서 8부는 가상 데이터다.
