// 브라우저 엔진(engine.js)이 파이썬 구현과 같은 총 배상금을 내는지 확인한다.
// 사용: node scripts/verify_engine.js   (먼저 python -m clausetower demo --llm mock, python scripts/build_site.py)
// 대조할 파이썬 보고서가 없으면 건너뛰지 않고 MISSING으로 실패한다(새로 받은 저장소에서 거짓 녹색을 막는다).
const fs = require('fs'), path = require('path'), vm = require('vm');
const ROOT = path.resolve(__dirname, '..');
const CT = require(path.join(ROOT, 'src/clausetower/web/engine.js'));
const dataPath = path.join(ROOT, 'site/data.js');
if (!fs.existsSync(dataPath)) { console.log('MISSING site/data.js (먼저 python scripts/build_site.py)'); process.exit(1); }
const ctx = { window: {} }; vm.runInNewContext(fs.readFileSync(dataPath, 'utf8'), ctx); const D = ctx.window.CT_DATA;
const POLICIES = ['deadline_first', 'fifo', 'value_first', 'exposure_first', 'exposure_abs'];
let fail = 0, checks = 0;
function missing(what, hint) { checks++; fail++; console.log(`MISSING ${what} (${hint})`); }
function compare(label, R, py) {
  for (const p of POLICIES) { checks++; const a = R.policies[p].total_penalty_krw, b = py.policies[p].total_penalty_krw; const ok = a === b; if (!ok) fail++;
    console.log(`${ok ? 'OK  ' : 'DIFF'} ${label} ${p.padEnd(15)} js=${a.toLocaleString()} py=${b.toLocaleString()}`); }
  checks++; const ra = R.ranking.map(r => r.shipment_id).join(','), rb = py.ranking.map(r => r.shipment_id).join(','); const okr = ra === rb; if (!okr) fail++;
  console.log(`${okr ? 'OK  ' : 'DIFF'} ${label} ranking order${okr ? '' : `\n   js=${ra}\n   py=${rb}`}`);
}
// 웹이 기본 설정에서 보여 주는 '탐색 근사 최적'(data.js에 실은 파이썬 탐색 순서)이 파이썬 보고서 값과 같은지
function compareSearch(label, S, src, terms, judgments, py) {
  const sb = (S.search_best || {})[src]; checks++;
  if (!sb) { fail++; console.log(`MISSING ${label} search_best in data.js (python scripts/build_site.py)`); return; }
  const R = CT.buildReport({ scenario: S.scenario, customers: D.customers, terms, extraction: {}, judgments, shipments: S.shipments_by_seed.A, llm_mode: src, withSearch: true, searchOpts: { order: sb.order } });
  const a = R.policies.search_best.total_penalty_krw, b = py.policies.search_best ? py.policies.search_best.total_penalty_krw : null; const ok = a === b && a === sb.total; if (!ok) fail++;
  console.log(`${ok ? 'OK  ' : 'DIFF'} ${label} search_best     js=${a.toLocaleString()} py=${b == null ? '없음' : b.toLocaleString()} data=${sb.total.toLocaleString()}`);
}
for (const S of D.scenarios) {
  const sid = S.scenario.id;
  const golden = path.join(ROOT, 'out/demo', `report_${sid}.json`);
  if (!fs.existsSync(golden)) missing(`out/demo/report_${sid}.json`, '먼저 python -m clausetower demo --llm mock');
  else {
    const py = JSON.parse(fs.readFileSync(golden, 'utf8'));
    if (py.llm_mode !== 'mock') missing(`out/demo/report_${sid}.json is llm_mode=${py.llm_mode}, not mock`, 'python -m clausetower demo --llm mock 로 다시 만든다');
    else { const judgments = {}; for (const c of D.customers) judgments[c.id] = CT.deriveJudgment(S.judgments.golden[c.id], D.sources.golden.terms[c.id], S.scenario.event, null);
      compare(`${sid}/golden`, CT.buildReport({ scenario: S.scenario, customers: D.customers, terms: D.sources.golden.terms, extraction: D.sources.golden.extraction, judgments, shipments: S.shipments_by_seed.A, llm_mode: 'golden' }), py);
      compareSearch(`${sid}/golden`, S, 'golden', D.sources.golden.terms, judgments, py); }
  }
  if (!S.judgments.real) continue;
  const real = path.join(ROOT, 'eval/results/real', `report_${sid}.json`);
  if (!fs.existsSync(real)) { missing(`eval/results/real/report_${sid}.json`, '추적 중인 실제 모델 보고서가 없다'); continue; }
  const py = JSON.parse(fs.readFileSync(real, 'utf8')); const judgments = {}; for (const c of D.customers) judgments[c.id] = CT.deriveJudgment(S.judgments.real[c.id], D.sources.real.terms[c.id], S.scenario.event, null);
  compare(`${sid}/real`, CT.buildReport({ scenario: S.scenario, customers: D.customers, terms: D.sources.real.terms, extraction: D.sources.real.extraction, judgments, shipments: S.shipments_by_seed.A, llm_mode: 'real' }), py);
  compareSearch(`${sid}/real`, S, 'real', D.sources.real.terms, judgments, py);
}
// 브라우저 탐색(설정을 바꿨을 때)은 난수·반복 횟수가 달라 값이 다를 수 있으니 '시작점보다 나쁘지 않다'만 본다
const S0 = D.scenarios[0]; const j0 = {}; for (const c of D.customers) j0[c.id] = CT.deriveJudgment(S0.judgments.golden[c.id], D.sources.golden.terms[c.id], S0.scenario.event, null);
const R0 = CT.buildReport({ scenario: S0.scenario, customers: D.customers, terms: D.sources.golden.terms, extraction: D.sources.golden.extraction, judgments: j0, shipments: S0.shipments_by_seed.A, llm_mode: 'golden', withSearch: true, searchOpts: { restarts: 2, sweeps: 1 } });
checks++; if (R0.policies.search_best.total_penalty_krw > R0.policies.exposure_first.total_penalty_krw) { fail++; console.log('DIFF search worse than start'); } else console.log(`OK   search ${R0.policies.search_best.total_penalty_krw.toLocaleString()} <= exposure_first ${R0.policies.exposure_first.total_penalty_krw.toLocaleString()}`);
// 기대 개수: 시나리오마다 정답지 7(정책 5 + 순위 + 탐색), 실제 보고서가 있는 시나리오마다 7, 브라우저 탐색 1
const expected = D.scenarios.length * 7 + D.scenarios.filter(S => S.judgments.real).length * 7 + 1;
if (checks < expected) { fail++; console.log(`FAIL checks ${checks} < expected ${expected}`); }
console.log(`\n${checks - fail}/${checks} checks passed (expected ${expected})`);
process.exit(fail ? 1 : 0);
