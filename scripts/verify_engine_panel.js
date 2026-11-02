// 웹 조작 패널이 만들 수 있는 입력(배치 A~E × 출처 × 트럭·결항·배율·통지·사실·사람 결정)으로 JS 엔진을 돌려 입력과 결과를 덤프한다.
// 파이썬 대조는 tests/test_web.py::test_js_engine_matches_python_on_panel_inputs가 한다(정책별 총액·지연 건수·고객별 금액·배차 레코드·순위표).
// 사용: node scripts/verify_engine_panel.js <출력.json> [변형 수(기본 4)]   (먼저 python scripts/build_site.py)
const fs = require('fs'), path = require('path'), vm = require('vm');
const ROOT = path.resolve(__dirname, '..');
const CT = require(path.join(ROOT, 'src/clausetower/web/engine.js'));
const ctx = { window: {} }; vm.runInNewContext(fs.readFileSync(path.join(ROOT, 'site/data.js'), 'utf8'), ctx); const D = ctx.window.CT_DATA;
const outPath = process.argv[2] || path.join(ROOT, 'out', 'engine_panel_cases.json'); const variants = +(process.argv[3] || 4);
let s = 12345; const rnd = () => { s = (s * 1103515245 + 12345) % 2147483648; return s / 2147483648; }; const pick = a => a[Math.floor(rnd() * a.length)];
const cases = [];
for (const S of D.scenarios) for (const seed of Object.keys(S.shipments_by_seed)) for (const src of Object.keys(S.judgments)) for (let k = 0; k < variants; k++) {
  const sc = JSON.parse(JSON.stringify(S.scenario)); const d = sc.disruption;
  if (k > 0) {
    sc.trucks = pick([4, 5, 6, 8, 10, 12]); d.trucks_out = Math.min(pick([0, 1, 2, 4, 6, 8]), sc.trucks); d.trucks_out_until_h = pick([0, 6, 16, 24, 36]);
    const aff = Object.keys(d.route_multipliers || {}); const m = pick([1, 1.3, 1.6, 2.5]); for (const r of aff) d.route_multipliers[r] = m;
    sc.event.notice_sent_after_hours = pick([null, 0, 6, 12, 13, 24, 48]);
    for (const f of Object.keys(sc.event.facts || {})) sc.event.facts[f] = rnd() < 0.5;
  }
  const terms = D.sources[src].terms; const judgments = {};
  for (const c of D.customers) { const ov = (k > 1 && rnd() < 0.2) ? rnd() < 0.5 : null; judgments[c.id] = CT.deriveJudgment(S.judgments[src][c.id], terms[c.id], sc.event, ov); }
  const shipments = S.shipments_by_seed[seed];
  const R = CT.buildReport({ scenario: sc, customers: D.customers, terms, extraction: D.sources[src].extraction, judgments, shipments, llm_mode: src });
  const js = {}; for (const [p, r] of Object.entries(R.policies)) js[p] = { total: r.total_penalty_krw, late: r.late_count, per_customer: r.per_customer_krw, records: r.records.map(x => [x.shipment_id, x.truck, x.penalty_krw]) };
  cases.push({ id: `${S.scenario.id}/${seed}/${src}/${k}`, scenario: sc, terms, judgments, shipments, js, ranking: R.ranking.map(r => [r.shipment_id, r.marginal_krw]) });
}
fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, JSON.stringify({ customers: D.customers, cases }));
console.log(`cases ${cases.length} → ${outPath}`);
