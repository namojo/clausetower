"""웹 데모: 사이트가 조립되고, 브라우저 엔진이 파이썬과 같은 숫자를 낸다."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def site():
    subprocess.run([sys.executable, "-m", "clausetower", "demo", "--llm", "mock", "--out", str(ROOT / "out" / "demo")], check=True,
                   capture_output=True, cwd=ROOT, env={**__import__("os").environ, "CLAUSETOWER_LLM": "mock"})
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_site.py")], check=True, capture_output=True, cwd=ROOT)
    return ROOT / "site"


def test_site_files_and_data(site):
    for f in ("index.html", "data.js", "engine.js", "render.js", "app.js", "style.css", ".nojekyll"):
        assert (site / f).is_file(), f
    data = json.loads((site / "data.js").read_text(encoding="utf-8").split("= ", 1)[1].rstrip(";\n"))
    assert len(data["scenarios"]) == 3 and set(data["scenarios"][0]["shipments_by_seed"]) == set("ABCDE")
    assert "golden" in data["sources"] and "extract" in data["prompts"] and data["schemas"]["judge"]["title"] == "ForceMajeureJudgment"
    html = (site / "index.html").read_text(encoding="utf-8")
    assert "실제 케이스 분석" in html and "AI 연결" in html and "면책 판단" in html
    import re
    for f in ("index.html", "app.js", "data.js"):
        assert not re.search(r"sk-ant-api\w{10,}", (site / f).read_text(encoding="utf-8")), f"{f}에 실제 키가 들어 있으면 안 된다"


@pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
def test_js_engine_matches_python(site):
    p = subprocess.run(["node", str(ROOT / "scripts" / "verify_engine.js")], capture_output=True, text=True, cwd=ROOT)
    assert p.returncode == 0, p.stdout[-1500:] + p.stderr[-500:]
    assert "DIFF" not in p.stdout


@pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
def test_js_files_parse(site):
    for f in ("engine.js", "render.js", "app.js"):
        p = subprocess.run(["node", "-e", "new Function(require('fs').readFileSync(0,'utf8'))"], input=(site / f).read_bytes(), capture_output=True)
        assert p.returncode == 0, f + ": " + p.stderr.decode()[:300]


needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")


def node_json(code: str, payload=None):
    p = subprocess.run(["node", "-e", code], input=json.dumps(payload or {}, ensure_ascii=False).encode("utf-8"), capture_output=True, cwd=ROOT)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")[-800:]
    return json.loads(p.stdout.decode("utf-8"))


def test_external_scripts_are_pinned_with_sri(site):
    """외부 CDN 스크립트는 버전 고정 URL에 integrity·crossorigin을 붙인다(같은 출처에 API 키가 저장될 수 있다)."""
    import re
    html = (site / "index.html").read_text(encoding="utf-8")
    tags = re.findall(r"<script[^>]+src=\"https?://[^\"]+\"[^>]*>", html)
    assert tags, "mammoth 외부 스크립트가 있어야 한다"
    for tag in tags:
        assert 'integrity="sha512-' in tag and 'crossorigin="anonymous"' in tag, tag


@needs_node
def test_js_derive_judgment_rules():
    """웹의 면책 결합: 통지 시한 경계, 사실이 조건을 덮어씀, 조건 키 누락은 미충족(fail-closed), 사람 결정은 결과만 바꾼다."""
    code = """
    const CT = require('./src/clausetower/web/engine.js');
    const terms = { force_majeure: { covered_events: ['태풍'], notice_hours: 12, conditions: ['입증'], citation: { clause: 'x', quote: 'y' } } };
    const base = { customer_id: 'X', has_clause: true, event_covered: true, notice_ok: false, conditions_met: { '입증': true }, applies: false, reasoning: 'r' };
    const ev = (n, facts) => ({ notice_sent_after_hours: n, facts: facts || {} });
    const d = (b, e, o) => CT.deriveJudgment(b, terms, e, o === undefined ? null : o);
    console.log(JSON.stringify({
      at_deadline: d(base, ev(12)).applies, just_late: d(base, ev(12.5)).applies, no_notice: d(base, ev(null)).applies,
      fact_false_overrides: d(base, ev(6, { '입증': false })).applies, fact_true_fills_missing: d(Object.assign({}, base, { conditions_met: {} }), ev(6, { '입증': true })).applies,
      missing_key_fails_closed: d(Object.assign({}, base, { conditions_met: {} }), ev(6)).applies,
      override: (() => { const j = d(base, ev(48), true); return [j.applies, j.derived_applies, j.manual_override]; })(),
    }));
    """
    r = node_json(code)
    assert r == {"at_deadline": True, "just_late": False, "no_notice": False, "fact_false_overrides": False,
                 "fact_true_fills_missing": True, "missing_key_fails_closed": False, "override": [True, False, True]}, r


@needs_node
def test_js_compute_penalty_matches_python_on_boundaries():
    """계산기 경계값(유예와 같은 지연, 누진 구간 경계, 가중 정액 경계, 상한과 같은 금액, 주말을 넘는 유예, 고객 합계 % 상한)을 JS도 같게 계산한다."""
    from datetime import datetime

    sys.path.insert(0, str(ROOT / "tests"))
    from conftest import FRI, MON
    from test_exposure import BOUNDARY_TERMS

    from clausetower.exposure import apply_customer_period_cap, compute_penalty
    from clausetower.schemas import Citation, ForceMajeure, PenaltyTerms

    daily = PenaltyTerms(customer_id="X", basis="per_calendar_day", rate_pct=0.1, grace_hours=24, cap_pct=10,
                         force_majeure=ForceMajeure(covered_events=["태풍"], notice_hours=24, citation=Citation(clause="c", quote="q")))
    cases = [(daily, 24, 100_000_000, MON), (daily, 24 + 24 * 100, 100_000_000, MON),
             (BOUNDARY_TERMS["tiered"], 48, 10_000_000, MON), (BOUNDARY_TERMS["tiered"], 48.01, 10_000_000, MON),
             (BOUNDARY_TERMS["flat"], 24, 1, MON), (BOUNDARY_TERMS["flat"], 24.01, 1, MON),
             (BOUNDARY_TERMS["bizday_grace"], 96, 10_000_000, FRI), (BOUNDARY_TERMS["period_pct_on_value"], 10, 10_000_000, MON)]
    payload = [{"terms": json.loads(t.model_dump_json()), "delay": d, "value": v, "due": due.isoformat() + "Z"} for t, d, v, due in cases]
    code = """
    const CT = require('./src/clausetower/web/engine.js'); const cs = JSON.parse(require('fs').readFileSync(0, 'utf8'));
    console.log(JSON.stringify(cs.map(c => { const b = CT.computePenalty(c.terms, { shipmentId: 'S', delayHours: c.delay, shipmentValue: c.value, dueAt: new Date(c.due), judgment: null });
      const p = CT.applyCustomerPeriodCap(c.terms, [b, b, b]).map(x => x.penalty_krw); return [b.penalty_krw, b.capped, b.units, b.blocked_by, p]; })));
    """
    js = node_json(code, payload)
    py = []
    for t, d, v, due in cases:
        b = compute_penalty(t, shipment_id="S", delay_hours=d, shipment_value_krw=v, due_at=due, judgment=None)
        py.append([b.penalty_krw, b.capped, b.units, b.blocked_by, [x.penalty_krw for x in apply_customer_period_cap(t, [b, b, b])]])
    assert js == py


@needs_node
def test_action_board_promises_only_what_the_engine_delivers(site):
    """조치 보드의 '통지 Nh로 시뮬레이션'·'충족으로 바꿔 보기' 버튼은 누르면 실제로 그 고객의 면책이 성립할 때만 나온다.
    실제 모델 추출에서 조건 문구가 달라 통지만으로 면책이 안 되는 세움건설(C)은 금액을 약속하지 않는다."""
    p = subprocess.run(["node", str(ROOT / "tests" / "js" / "render_harness.js"), str(site / "data.js")], capture_output=True, cwd=ROOT)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")[-800:]
    r = json.loads(p.stdout.decode("utf-8"))
    assert r["buttons"] and r["broken"] == [], r["broken"]
    golden, real = r["items"]["typhoon/golden/세움건설"], r["items"]["typhoon/real/세움건설"]
    assert 'data-act="notice"' in golden and "시한을 지켰다면 배상금" in golden
    assert 'data-act="notice"' not in real and "시한을 지켰다면" not in real and "통지만으로는 면책 안 됨" in real
    assert r["xss"] == {"cards": False, "matrix": False}, "모델이 돌려준 basis·고객 이름이 HTML로 해석되면 안 된다"


@needs_node
def test_js_engine_matches_python_on_panel_inputs(site, tmp_path):
    """조작 패널 입력(배치 A~E × 출처 × 트럭·결항·배율·통지·사실·사람 결정)에서 JS와 파이썬이 정책별 총액·지연 건수·고객별 금액·배차 레코드·순위표까지 같다."""
    from clausetower.agent import ranking_at
    from clausetower.schemas import Customer, ForceMajeureJudgment, PenaltyTerms, Scenario, Shipment
    from clausetower.sim import POLICIES, Context, run_policy

    out = tmp_path / "cases.json"
    p = subprocess.run(["node", str(ROOT / "scripts" / "verify_engine_panel.js"), str(out), "3"], capture_output=True, cwd=ROOT)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")[-800:]
    data = json.loads(out.read_text(encoding="utf-8"))
    customers = [Customer(**c) for c in data["customers"]]
    cmap = {c.id: c for c in customers}
    diffs = []
    for case in data["cases"]:
        sc = Scenario.model_validate(case["scenario"])
        ctx = Context(scenario=sc, terms={k: PenaltyTerms.model_validate(v) for k, v in case["terms"].items()},
                      judgments={k: ForceMajeureJudgment.model_validate(v) for k, v in case["judgments"].items()}, customers=cmap)
        ships = [Shipment.model_validate(s) for s in case["shipments"]]
        res = {}
        for pid, (label, fn) in POLICIES.items():
            r = res[pid] = run_policy(sc, ships, ctx, fn, pid, label)
            py = {"total": r.total_penalty_krw, "late": r.late_count, "per_customer": r.per_customer_krw, "records": [[x.shipment_id, x.truck, x.penalty_krw] for x in r.records]}
            bad = [k for k in py if py[k] != case["js"][pid][k]]
            if bad:
                diffs.append((case["id"], pid, bad))
        base = res["deadline_first"]
        rk = ranking_at(ctx, ships, sc, cmap, base.peak_queue_h, base.peak_queue_ids)
        if [[x.shipment_id, x.marginal_krw] for x in rk] != case["ranking"]:
            diffs.append((case["id"], "ranking"))
    assert len(data["cases"]) >= 60 and diffs == [], diffs[:5]
