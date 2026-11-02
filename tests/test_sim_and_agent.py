import json

import pytest

from clausetower.agent import run
from clausetower.contracts import list_scenarios, load_customers, load_golden_judgment, load_golden_terms, load_scenario
from clausetower.llm import LLM
from clausetower.schemas import Report
from clausetower.sim import POLICIES, Context, build_shipments, run_policy, search_best_order


def make_ctx(scenario_id):
    scenario = load_scenario(scenario_id)
    customers = load_customers()
    terms = {c.id: load_golden_terms(c.id) for c in customers}
    judg = {c.id: load_golden_judgment(c.id, scenario_id) for c in customers}
    return scenario, customers, Context(scenario=scenario, terms=terms, judgments=judg, customers={c.id: c for c in customers})


def test_golden_files_are_consistent_with_contract_texts():
    from clausetower.contracts import load_contract_text
    for c in load_customers():
        t = load_golden_terms(c.id)
        text = load_contract_text(c.id)
        for key, cit in t.citations.items():
            head = cit.quote.split("…")[0].strip()[:25]
            assert head in text, f"{c.id} {key} 인용이 계약서에 없다: {head}"
        if t.force_majeure:
            assert t.force_majeure.citation.quote.split("…")[0].strip()[:20] in text


def test_shipments_are_deterministic_and_disruption_applies():
    scenario, customers, ctx = make_ctx("typhoon")
    a = build_shipments(scenario, customers)
    b = build_shipments(scenario, customers)
    assert [s.model_dump() for s in a] == [s.model_dump() for s in b]
    assert len(a) == len(customers) * scenario.shipments_per_customer
    pc, _, _ = make_ctx("port_congestion")
    ships = build_shipments(pc, customers)
    plain = build_shipments(pc.model_copy(update={"disruption": pc.disruption.model_copy(update={"ready_delay_h": 0})}), customers)
    by_id = {s.id: s for s in plain}
    delayed = [s for s in ships if s.ready_h > by_id[s.id].ready_h]
    assert delayed and all(s.route in pc.disruption.ready_delay_routes for s in delayed), "항만 적체는 항만 노선 화물의 출고 준비만 늦춰야 한다"


@pytest.mark.parametrize("sid", list_scenarios())
def test_every_shipment_dispatched_once_and_curve_monotone(sid):
    scenario, customers, ctx = make_ctx(sid)
    ships = build_shipments(scenario, customers)
    for pid, (label, fn) in POLICIES.items():
        r = run_policy(scenario, ships, ctx, fn, pid, label)
        assert sorted(x.shipment_id for x in r.records) == sorted(s.id for s in ships)
        assert all(x.delivered_h > x.dispatched_h for x in r.records)
        assert all(b <= a2 for (_, b), (_, a2) in zip(r.penalty_curve, r.penalty_curve[1:]))
        assert r.total_penalty_krw == sum(x.penalty_krw for x in r.records) == sum(r.per_customer_krw.values())


@pytest.mark.parametrize("sid", list_scenarios())
def test_exposure_first_beats_deadline_first(sid):
    scenario, customers, ctx = make_ctx(sid)
    ships = build_shipments(scenario, customers)
    base = run_policy(scenario, ships, ctx, POLICIES["deadline_first"][1], "d", "d").total_penalty_krw
    ours = run_policy(scenario, ships, ctx, POLICIES["exposure_first"][1], "e", "e").total_penalty_krw
    assert ours < base


def test_search_never_worse_than_its_start():
    scenario, customers, ctx = make_ctx("typhoon")
    ships = build_shipments(scenario, customers)
    ours = run_policy(scenario, ships, ctx, POLICIES["exposure_first"][1], "e", "e")
    best = search_best_order(scenario, ships, ctx, restarts=2, sweeps=1, start=[r.shipment_id for r in ours.records])
    assert best.total_penalty_krw <= ours.total_penalty_krw


def test_blocked_shipments_never_charged():
    scenario, customers, ctx = make_ctx("typhoon")
    ships = build_shipments(scenario, customers)
    r = run_policy(scenario, ships, ctx, POLICIES["deadline_first"][1], "d", "d")
    fm_customers = {cid for cid, j in ctx.judgments.items() if j.applies}
    assert fm_customers == {"A", "F", "G"}
    assert all(x.penalty_krw == 0 for x in r.records if x.customer_id in fm_customers)


def test_agent_report_roundtrip_and_story(tmp_path):
    r = run("typhoon", llm=LLM("mock"), with_search=False)
    assert r.llm_mode == "mock" and r.savings_vs_deadline_pct > 0
    # 핵심 서사: 마감 순위 상위(5위 이내) 화물 중 불가항력 면책이나 유예로 노출이 0인 화물이 3계단 이상 뒤로 밀린다
    assert any(row.deadline_rank <= 5 and row.exposure_rank > row.deadline_rank + 2 for row in r.ranking)
    assert all(row.citations for row in r.ranking if row.penalty_if_deferred_krw > 0)
    js = r.model_dump_json()
    back = Report.model_validate_json(js)
    assert back.policies["exposure_first"].total_penalty_krw == r.policies["exposure_first"].total_penalty_krw
    (tmp_path / "r.json").write_text(js, encoding="utf-8")
    assert json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))["scenario"]["id"] == "typhoon"


def test_judge_recomputes_applies_mechanically(monkeypatch):
    """모델이 applies만 뒤집어도 조건 결합으로 되돌린다."""
    from clausetower import extract
    from clausetower.schemas import ForceMajeureJudgment

    llm = LLM("mock")
    bad = ForceMajeureJudgment(customer_id="C", has_clause=True, event_covered=True, notice_ok=False, applies=True, reasoning="x")
    monkeypatch.setattr(llm, "parse", lambda **kw: bad)
    j = extract.judge_force_majeure(llm, "C", load_golden_terms("C"), load_scenario("typhoon").event, "typhoon")
    assert j.applies is False and "기계적으로" in j.reasoning


def test_judge_missing_condition_key_fails_closed(monkeypatch):
    """계약에 정성 조건이 있는데 모델 판단(conditions_met)이 그 키를 빠뜨리면 충족으로 보지 않는다(fail-closed)."""
    from clausetower import extract
    from clausetower.schemas import ForceMajeureJudgment

    terms = load_golden_terms("H")
    assert terms.force_majeure and terms.force_majeure.conditions, "H는 입증 조건이 걸린 계약이어야 한다"
    llm = LLM("mock")
    lax = ForceMajeureJudgment(customer_id="H", has_clause=True, event_covered=True, notice_ok=True, conditions_met={}, applies=True, reasoning="x")
    monkeypatch.setattr(llm, "parse", lambda **kw: lax)
    event = load_scenario("port_congestion").event.model_copy(update={"facts": {}})
    j = extract.judge_from_text(llm, "H", terms, event, "본문")
    assert j.applies is False and "기계적으로" in j.reasoning
    # 사실(facts)이 조건을 충족하면 모델이 키를 빠뜨렸어도 면책이 성립한다
    cond = terms.force_majeure.conditions[0]
    j2 = extract.judge_from_text(llm, "H", terms, event.model_copy(update={"facts": {c: True for c in terms.force_majeure.conditions}}), "본문")
    assert j2.applies is True, cond


def test_ranking_uses_the_same_hold_cycle_as_the_policy():
    """결항이 대기열 최대 시점보다 먼저 끝나도 순위표는 정책과 같은 보류 기간(한 사이클)으로 계산한다."""
    from clausetower.agent import ranking_at
    from clausetower.sim import ROUTES, State, _exposure_key

    scenario, customers, ctx = make_ctx("typhoon")
    scenario = scenario.model_copy(update={"disruption": scenario.disruption.model_copy(update={"trucks_out_until_h": 6})})
    ctx.scenario = scenario
    ships = build_shipments(scenario, customers)
    base = run_policy(scenario, ships, ctx, POLICIES["deadline_first"][1], "d", "d")
    t = base.peak_queue_h
    assert t >= scenario.disruption.trucks_out_until_h, "이 시험은 결항이 끝난 뒤의 대기열 최대 시점을 다룬다"
    rows = ranking_at(ctx, ships, scenario, {c.id: c for c in customers}, t, base.peak_queue_ids)
    cycle = 2 * sum(ROUTES.values()) / len(ROUTES) / max(1, scenario.trucks - scenario.disruption.trucks_out)  # run_policy와 같은 식
    waiting = [s for s in ships if s.id in set(base.peak_queue_ids)]
    state = State(t=t, free_trucks=scenario.trucks, waiting=waiting, avg_cycle_h=cycle)
    policy_order = [s.id for s in sorted(waiting, key=lambda s: _exposure_key(state, ctx, s, per_hour=True))]
    assert [r.shipment_id for r in rows] == policy_order
