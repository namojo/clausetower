// render.js를 가짜 DOM에서 돌려 조치 보드와 계약 카드의 HTML을 검사한다(브라우저 없이, tests/test_web.py가 호출).
// 사용: node tests/js/render_harness.js <site/data.js>  → JSON 한 줄
const fs = require('fs'), path = require('path'), vm = require('vm');
const ROOT = path.resolve(__dirname, '..', '..');
const CT = require(path.join(ROOT, 'src/clausetower/web/engine.js'));
const dctx = { window: {} }; vm.runInNewContext(fs.readFileSync(process.argv[2], 'utf8'), dctx); const D = dctx.window.CT_DATA;

function el() { return { innerHTML: '', textContent: '', style: {}, dataset: {}, className: '', classList: { toggle() {}, add() {}, remove() {} },
  querySelectorAll: () => [], querySelector: () => el(), addEventListener() {}, scrollIntoView() {} }; }
const els = {};
const document = { querySelector: s => (els[s] = els[s] || el()), getElementById: id => (els['#' + id] = els['#' + id] || el()), addEventListener() {} };
const sandbox = { document, window: { CT_DATA: D, CT_APP: {}, innerWidth: 1200 }, CT, console };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(ROOT, 'src/clausetower/web/render.js'), 'utf8') + '\n;globalThis.__R = { renderActions, renderBoard, esc };', sandbox);
const { renderActions, renderBoard } = sandbox.__R;

function report(S, src, event) {
  const terms = D.sources[src].terms, judgments = {};
  for (const c of D.customers) judgments[c.id] = CT.deriveJudgment(S.judgments[src][c.id], terms[c.id], event, null);
  return CT.buildReport({ scenario: Object.assign({}, S.scenario, { event }), customers: D.customers, terms, extraction: D.sources[src].extraction, judgments, shipments: S.shipments_by_seed.A, llm_mode: src });
}

const out = { buttons: [], broken: [], items: {} };
for (const S of D.scenarios) for (const src of Object.keys(S.judgments)) {
  const ev = S.scenario.event; const R = report(S, src, ev);
  renderActions(R); const html = els['#actions'].innerHTML;
  // 화면이 약속한 버튼마다 실제로 그 값을 넣고 엔진으로 다시 결합해, 그 고객의 면책이 성립하는지 확인한다
  const re = /data-act="(notice|fact)" data-cid="([^"]+)" data-(h|k)="([^"]*)"/g; let m;
  while ((m = re.exec(html))) {
    const [, act, cid, , raw] = m; const val = raw.replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
    const ev2 = Object.assign({}, ev, act === 'notice' ? { notice_sent_after_hours: +val } : { facts: Object.assign({}, ev.facts, { [val]: true }) });
    const applies = CT.deriveJudgment(S.judgments[src][cid], D.sources[src].terms[cid], ev2, null).applies;
    const after = report(S, src, ev2).policies.exposure_first.per_customer_krw[cid] || 0;
    const rec = { scenario: S.scenario.id, src, act, cid, val, applies, after }; out.buttons.push(rec); if (!applies || after !== 0) out.broken.push(rec);
  }
  // 고객별 통지 항목 HTML(세움건설 C 등 개별 검사용)
  for (const li of html.split('<li').slice(1)) { const mm = /<b>([^<]+)<\/b> <span class="s">(\d+(?:\.\d+)?)h 이내 통지 조건/.exec(li); if (mm) out.items[`${S.scenario.id}/${src}/${mm[1]}`] = li; }
}

// 계약 카드: 모델 출력(basis)·업로드 고객 이름이 HTML로 해석되지 않아야 한다
const S0 = D.scenarios[0]; const R0 = report(S0, 'golden', S0.scenario.event);
const evil = '<img src=x onerror=alert(1)>';
R0.terms = Object.assign({}, R0.terms, { A: Object.assign({}, R0.terms.A, { basis: evil }) });
R0.customers = R0.customers.map(c => c.id === 'B' ? Object.assign({}, c, { name: evil }) : c);
sandbox.BOARD_MODE = 'cards'; renderBoard(R0); const cards = els['#board'].innerHTML;
vm.runInContext("BOARD_MODE = 'matrix'", sandbox); renderBoard(R0); const matrix = els['#board'].innerHTML;
out.xss = { cards: cards.includes('<img'), matrix: matrix.includes('<img') };
console.log(JSON.stringify(out));
