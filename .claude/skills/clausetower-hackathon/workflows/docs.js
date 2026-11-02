export const meta = {
  name: 'ct-docs',
  description: 'ClauseTower 해커톤 문서를 측정값 근거로 작성·갱신하고 사실 검증 후 보완한다',
  whenToUse: 'clausetower-hackathon 오케스트레이터 5단계. args: {docs:[{path, mode, brief, findings}], factsPath, changesPath, roleFromFile}',
  phases: [
    { title: '작성', detail: '문서마다 ct-doc-writer가 작성·갱신' },
    { title: '사실 검증', detail: 'ct-verifier가 숫자·명령·경로·주장을 측정값과 코드에 대조' },
    { title: '보완', detail: '오류·오해 소지가 있는 문서만 ct-doc-writer가 해당 위치를 고침' },
    { title: '교차 검토', detail: '문서 사이 숫자·용어·링크 일관성 확인' },
  ],
}

const A = args || {}
const DOCS = (Array.isArray(A.docs) ? A.docs : []).filter(d => d && d.path)
const FACTS = A.factsPath || '_workspace/01_qa_gates.json'
const CHANGES = A.changesPath || null
if (!DOCS.length) return { error: 'args.docs가 비어 있어 작성할 문서가 없다', docs: [] }

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

const SET = DOCS.map(d => `- ${d.path} (${d.mode === 'create' ? '신규' : '갱신'}): ${d.brief || ''}`).join('\n')

const WRITE_REPORT = {
  type: 'object',
  required: ['path', 'status', 'sections', 'sources_used', 'open_questions', 'summary'],
  properties: {
    path: { type: 'string' },
    status: { type: 'string', enum: ['created', 'updated', 'unchanged', 'failed'] },
    sections: { type: 'array', items: { type: 'string' } },
    sources_used: { type: 'array', items: { type: 'string' } },
    open_questions: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
}

const ISSUE = {
  type: 'object',
  required: ['location', 'claim', 'problem', 'correct', 'severity'],
  properties: {
    location: { type: 'string' },
    claim: { type: 'string' },
    problem: { type: 'string' },
    correct: { type: 'string' },
    severity: { type: 'string', enum: ['error', 'misleading', 'nit'] },
  },
}
const FACTCHECK = {
  type: 'object',
  required: ['path', 'claims_checked', 'issues'],
  properties: { path: { type: 'string' }, claims_checked: { type: 'integer' }, issues: { type: 'array', items: ISSUE } },
}
const CROSS = {
  type: 'object',
  required: ['issues'],
  properties: {
    issues: {
      type: 'array',
      items: {
        type: 'object',
        required: ['docs', 'problem', 'fix', 'severity'],
        properties: {
          docs: { type: 'array', items: { type: 'string' } },
          problem: { type: 'string' },
          fix: { type: 'string' },
          severity: { type: 'string', enum: ['error', 'misleading', 'nit'] },
        },
      },
    },
  },
}

function writePrompt(d) {
  const lines = [
    `문서 \`${d.path}\`를 ${d.mode === 'create' ? '새로 작성' : '갱신'}하라.`,
    '.claude/skills/ct-hackathon-docs/SKILL.md, references/doc-catalog.md의 이 문서 절, references/style-guide.md를 먼저 읽어라.',
    `숫자의 1차 근거: ${FACTS}의 facts. 실제 모델 호출·비용·시간은 eval/results/real*/run.log.`,
    `작성 지시: ${d.brief || '문서 목록 명세를 따른다'}`,
    '이번 실행의 문서 세트(서로 링크하고 숫자·용어를 맞춰라):',
    SET,
  ]
  if (CHANGES) lines.push(`코드 수정의 문서 영향: ${CHANGES}의 "문서 영향" 항목을 반영하라.`)
  if (Array.isArray(d.findings) && d.findings.length) {
    lines.push('이 문서와 관련해 확정된 검토 지적(반드시 해소하라):')
    lines.push(JSON.stringify(d.findings.map(f => ({ id: f.id, title: f.title, evidence: f.evidence, fix: f.fix })), null, 1))
  }
  lines.push('파일을 직접 쓰고, 결과를 스키마로 보고하라. 코드 파일은 고치지 마라.')
  return lines.join('\n')
}

function checkPrompt(d, w) {
  return [
    `문서 사실 검증 모드. \`${d.path}\`의 검증 가능한 주장(숫자·명령·경로·기능·지표 해석·용어)을 모두 뽑아 대조하라.`,
    '.claude/skills/ct-hackathon-docs/SKILL.md의 「사실 검증」과 references/style-guide.md 용어집을 따르라.',
    `1차 근거: ${FACTS}의 facts, 그다음 eval/results/, 그다음 코드. mock 명령만 실행해 확인하고 실제 LLM은 호출하지 마라.`,
    '작성자가 밝힌 출처(참고용, 그대로 믿지 마라):',
    JSON.stringify({ sources_used: w.sources_used, open_questions: w.open_questions }, null, 1),
  ].join('\n')
}

function revisePrompt(d, issues) {
  return [
    `\`${d.path}\`의 사실 검증 문제를 고쳐라. 지적된 위치만 고치고 나머지는 그대로 둬라.`,
    '올바른 값을 근거에서 다시 확인한 뒤 고쳐라. 근거로 확정할 수 없으면 해당 주장을 빼거나 "목표"·"확인 필요"로 표시하고 open_questions에 남겨라.',
    'summary에 고친 위치를 나열하라.',
    JSON.stringify(issues, null, 1),
  ].join('\n')
}

function crossPrompt(done) {
  return [
    '교차 검토 모드. 아래 문서들이 같은 사실을 같은 숫자·용어로 말하는지, 서로의 링크가 깨지지 않았는지 확인하라.',
    'README.md 6절과 facts를 숫자 기준으로 삼아라. 이번에 쓰지 않은 기존 문서(README.md, docs/*.md)도 함께 열어 모순을 찾아라.',
    `facts: ${FACTS}. .claude/skills/ct-hackathon-docs/references/style-guide.md의 용어집을 따르라.`,
    '이번 실행에서 쓴 문서:',
    done.map(x => `- ${x.doc} (${x.write ? x.write.status : 'failed'})`).join('\n'),
  ].join('\n')
}

phase('작성')
const results = await pipeline(
  DOCS,
  d => call('ct-doc-writer', writePrompt(d), { label: `작성:${d.path}`, phase: '작성', schema: WRITE_REPORT }),
  (w, d) => {
    if (!w || w.status === 'failed') return { doc: d.path, write: w, check: null, revision: null }
    return call('ct-verifier', checkPrompt(d, w), { label: `검증:${d.path}`, phase: '사실 검증', schema: FACTCHECK })
      .then(c => ({ doc: d.path, write: w, check: c, revision: null }))
  },
  (x, d) => {
    if (!x || !x.check) return x
    const issues = (x.check.issues || []).filter(i => i.severity !== 'nit')
    if (!issues.length) return x
    return call('ct-doc-writer', revisePrompt(d, issues), { label: `보완:${d.path}`, phase: '보완', schema: WRITE_REPORT })
      .then(r => Object.assign({}, x, { revision: r }))
  },
)

const done = results.filter(Boolean)
const failed = DOCS.filter(d => !done.find(x => x.doc === d.path && x.write && x.write.status !== 'failed')).map(d => d.path)
if (failed.length) log(`작성하지 못한 문서 ${failed.length}개: ${failed.join(', ')}`)
const unchecked = done.filter(x => x.write && x.write.status !== 'failed' && !x.check).map(x => x.doc)
if (unchecked.length) log(`사실 검증을 받지 못한 문서 ${unchecked.length}개: ${unchecked.join(', ')}`)

phase('교차 검토')
const written = done.filter(x => x.write && x.write.status !== 'failed')
const cross = written.length
  ? await call('ct-verifier', crossPrompt(done), { label: '교차 검토', phase: '교차 검토', schema: CROSS })
  : null
if (written.length && !cross) log('교차 검토 결과를 받지 못했다.')

return {
  docs: done.map(x => ({
    path: x.doc,
    status: x.write ? x.write.status : 'failed',
    sections: x.write ? x.write.sections : [],
    claims_checked: x.check ? x.check.claims_checked : null,
    issues_found: x.check ? x.check.issues : null,
    revised: !!x.revision,
    revision_summary: x.revision ? x.revision.summary : null,
    open_questions: [].concat((x.write && x.write.open_questions) || [], (x.revision && x.revision.open_questions) || []),
  })),
  failed,
  unchecked,
  cross_issues: cross ? cross.issues : null,
}
