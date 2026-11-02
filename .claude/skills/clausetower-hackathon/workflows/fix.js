export const meta = {
  name: 'ct-fix',
  description: '승인된 ClauseTower 구성 지적을 ct-fixer가 고치고 ct-qa가 게이트로 확인하는 반복(최대 3라운드)',
  whenToUse: 'clausetower-hackathon 오케스트레이터 4단계. args: {approvedPath, baselinePath, maxRounds, roleFromFile}',
  phases: [
    { title: '수정', detail: 'ct-fixer가 승인 항목을 최소 변경으로 고친다' },
    { title: 'QA', detail: 'ct-qa가 게이트와 재현 명령으로 해소 여부·회귀를 확인한다' },
  ],
}

const A = args || {}
const APPROVED = A.approvedPath || '_workspace/03_approved.json'
const BASE = A.baselinePath || '_workspace/01_qa_gates.json'
const MAX = Math.min(Math.max(Number(A.maxRounds) || 2, 1), 3)

// 사용자 정의 에이전트가 아직 등록되지 않은 세션에서는 roleFromFile: true로 정의 파일에서 역할을 불러온다.
const ROLE_FROM_FILE = A.roleFromFile === true
const ROLE_MODEL = { 'ct-qa': 'sonnet' }
function call(type, prompt, opts) {
  if (!ROLE_FROM_FILE) return agent(prompt, Object.assign({ agentType: type }, opts))
  const p = `먼저 .claude/agents/${type}.md를 읽고 그 역할·작업 원칙·입출력 규칙을 그대로 따르라. ` +
    '이 세션에는 사용자 정의 에이전트 유형이 아직 등록되지 않아 정의 파일로 역할을 불러온다. ' +
    '정의 파일의 tools에 Edit·Write가 없으면 어떤 파일도 고치지 마라.\n\n' + prompt
  return agent(p, Object.assign(ROLE_MODEL[type] ? { model: ROLE_MODEL[type] } : {}, opts))
}

const FIX_REPORT = {
  type: 'object',
  required: ['items', 'tests_run', 'summary'],
  properties: {
    items: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'status', 'files_changed', 'note'],
        properties: {
          id: { type: 'string' },
          status: { type: 'string', enum: ['fixed', 'partial', 'skipped'] },
          files_changed: { type: 'array', items: { type: 'string' } },
          tests_added: { type: 'array', items: { type: 'string' } },
          note: { type: 'string' },
          doc_impact: { type: 'string' },
        },
      },
    },
    tests_run: { type: 'string' },
    summary: { type: 'string' },
  },
}

const QA_REPORT = {
  type: 'object',
  required: ['gates_ok', 'gates_path', 'resolved', 'unresolved', 'regressions', 'numbers_changed', 'summary'],
  properties: {
    gates_ok: { type: 'boolean' },
    gates_path: { type: 'string' },
    resolved: { type: 'array', items: { type: 'string' } },
    unresolved: {
      type: 'array',
      items: { type: 'object', required: ['id', 'reason'], properties: { id: { type: 'string' }, reason: { type: 'string' }, repro: { type: 'string' } } },
    },
    regressions: {
      type: 'array',
      items: { type: 'object', required: ['what', 'evidence'], properties: { what: { type: 'string' }, evidence: { type: 'string' } } },
    },
    numbers_changed: { type: 'boolean' },
    changed_facts: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
}

function fixPrompt(round, qa) {
  const lines = [
    `라운드 ${round}. 승인 목록 ${APPROVED}에서 fix_owner가 code인 지적을 고쳐라.`,
    '.claude/skills/ct-safe-fix/SKILL.md의 절차·불변 조건·변경 기록 형식을 따르라.',
    `기준선 게이트 결과: ${BASE}. 넘기기 전에 run_gates.py --only pytest verify_engine --out _workspace/04_fixer_gates_r${round}.json으로 스스로 확인하라.`,
    `변경 기록은 _workspace/04_fixer_changes.md에 "## 라운드 ${round}"로 덧붙여라. 커밋·푸시는 하지 마라.`,
  ]
  if (qa) {
    lines.push('직전 QA가 남긴 미해결·회귀 항목만 다뤄라. 이미 해소된 수정은 건드리지 마라.')
    lines.push(JSON.stringify({ unresolved: qa.unresolved || [], regressions: qa.regressions || [] }, null, 1))
  }
  return lines.join('\n')
}

function qaPrompt(round, fix) {
  return [
    `라운드 ${round} 수정 결과를 독립적으로 확인하라. .claude/skills/ct-quality-gates/SKILL.md를 따르라.`,
    `1. 전체 게이트: python .claude/skills/ct-quality-gates/scripts/run_gates.py --out _workspace/04_qa_gates_r${round}.json`,
    `2. 승인 목록 ${APPROVED}의 code 지적마다 repro를 다시 실행하거나 동작을 직접 시험해 해소 여부를 판정하라(파일 존재만 보지 마라).`,
    `3. 기준선 ${BASE}과 facts를 비교해 바뀐 숫자를 changed_facts에 모두 적어라.`,
    '4. git status와 git diff --stat으로 승인 목록·변경 기록(_workspace/04_fixer_changes.md) 밖의 변경, 추적 측정 파일(eval/results, contracts/golden, docs/screenshots) 변경을 찾아 regressions에 넣어라.',
    `gates_path에는 ${'_workspace/04_qa_gates_r' + round + '.json'}을 넣어라. 코드는 고치지 마라.`,
    '수정자 보고(참고용, 그대로 믿지 마라):',
    JSON.stringify(fix, null, 1),
  ].join('\n')
}

const rounds = []
let qa = null
for (let round = 1; round <= MAX; round++) {
  const fix = await call('ct-fixer', fixPrompt(round, qa), { label: `수정:r${round}`, phase: '수정', schema: FIX_REPORT })
  if (!fix) {
    log(`라운드 ${round}: 수정 에이전트가 결과를 돌려주지 못해 반복을 멈춘다.`)
    rounds.push({ round, fix: null, qa: null })
    break
  }
  qa = await call('ct-qa', qaPrompt(round, fix), { label: `QA:r${round}`, phase: 'QA', schema: QA_REPORT })
  rounds.push({ round, fix, qa })
  if (!qa) {
    log(`라운드 ${round}: QA 결과가 없어 반복을 멈춘다.`)
    break
  }
  const open = (qa.unresolved || []).length + (qa.regressions || []).length
  log(`라운드 ${round}: 해소 ${(qa.resolved || []).length}건, 미해결 ${(qa.unresolved || []).length}건, 회귀 ${(qa.regressions || []).length}건, 게이트 ${qa.gates_ok ? '통과' : '실패'}`)
  if (qa.gates_ok && open === 0) break
  const progressed = (fix.items || []).some(i => i.status !== 'skipped')
  if (round > 1 && !progressed) {
    log(`라운드 ${round}: 수정자가 더 고칠 수 있는 항목이 없다고 보고해 반복을 멈춘다.`)
    break
  }
  if (round === MAX) log(`최대 ${MAX}라운드에 도달했다. 남은 항목은 사용자 판단으로 넘긴다.`)
}

const last = rounds.length ? rounds[rounds.length - 1] : null
const fixes = rounds.map(r => r.fix).filter(Boolean)
const docImpacts = fixes.flatMap(f => (f.items || []).filter(i => i.doc_impact).map(i => ({ id: i.id, doc_impact: i.doc_impact })))

return {
  rounds: rounds.length,
  done: !!(last && last.qa && last.qa.gates_ok && !(last.qa.unresolved || []).length && !(last.qa.regressions || []).length),
  final_qa: last ? last.qa : null,
  items: fixes.flatMap(f => f.items || []),
  doc_impacts: docImpacts,
  gates_path: last && last.qa ? last.qa.gates_path : null,
}
