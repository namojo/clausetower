export const meta = {
  name: 'ct-review',
  description: 'ClauseTower 시스템 구성과 문서를 관점별로 검토하고 지적마다 반박 검증한다',
  whenToUse: 'clausetower-hackathon 오케스트레이터 2단계. args: {dimensions, factsPath, priorFindingsPath, focus, thorough, roleFromFile}',
  phases: [
    { title: '검토', detail: '관점(runtime·security·engine·docs)마다 ct-config-reviewer가 근거 붙은 지적을 수집한다' },
    { title: '검증', detail: 'ct-verifier가 지적을 재현·반증 입장에서 판정한다(철저 모드는 렌즈 3개 다수결)' },
  ],
}

const A = args || {}
const ALL_DIMENSIONS = ['runtime', 'security', 'engine', 'docs']
const DIMENSIONS = (Array.isArray(A.dimensions) && A.dimensions.length ? A.dimensions : ALL_DIMENSIONS)
  .filter(d => ALL_DIMENSIONS.includes(d))
const FACTS = A.factsPath || '_workspace/01_qa_gates.json'
const THOROUGH = A.thorough === true
const LENSES = THOROUGH ? ['reproduce', 'counter-evidence', 'impact'] : ['batch']
const MAJORITY = Math.floor(LENSES.length / 2) + 1
const SEV_ORDER = { blocker: 0, high: 1, medium: 2, low: 3 }
const SEVERITIES = ['blocker', 'high', 'medium', 'low']

// 사용자 정의 에이전트가 아직 등록되지 않은 세션(하네스를 만든 세션 등)에서는 roleFromFile: true로
// 기본 워크플로 에이전트가 .claude/agents/{type}.md를 읽어 역할을 불러온다.
const ROLE_FROM_FILE = A.roleFromFile === true
const ROLE_MODEL = { 'ct-qa': 'sonnet' }
function call(type, prompt, opts) {
  if (!ROLE_FROM_FILE) return agent(prompt, Object.assign({ agentType: type }, opts))
  const p = `먼저 .claude/agents/${type}.md를 읽고 그 역할·작업 원칙·입출력 규칙을 그대로 따르라. ` +
    '이 세션에는 사용자 정의 에이전트 유형이 아직 등록되지 않아 정의 파일로 역할을 불러온다. ' +
    '정의 파일의 tools에 Edit·Write가 없으면 어떤 파일도 고치지 마라.\n\n' + prompt
  return agent(p, Object.assign(ROLE_MODEL[type] ? { model: ROLE_MODEL[type] } : {}, opts))
}

const FINDINGS = {
  type: 'object',
  required: ['findings', 'checked'],
  properties: {
    checked: { type: 'array', items: { type: 'string' } },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['title', 'severity', 'kind', 'files', 'evidence', 'impact', 'fix', 'fix_owner', 'effort'],
        properties: {
          title: { type: 'string' },
          severity: { type: 'string', enum: SEVERITIES },
          kind: { type: 'string', enum: ['defect', 'env', 'risk', 'doc-error', 'doc-gap'] },
          files: { type: 'array', items: { type: 'string' } },
          evidence: { type: 'string' },
          repro: { type: 'string' },
          impact: { type: 'string' },
          fix: { type: 'string' },
          fix_owner: { type: 'string', enum: ['code', 'docs', 'user'] },
          effort: { type: 'string', enum: ['S', 'M', 'L'] },
        },
      },
    },
  },
}

const VERDICT_ITEM = {
  type: 'object',
  required: ['id', 'status', 'reason'],
  properties: {
    id: { type: 'string' },
    status: { type: 'string', enum: ['confirmed', 'refuted', 'uncertain'] },
    reason: { type: 'string' },
    evidence: { type: 'string' },
    severity: { type: 'string', enum: SEVERITIES },
  },
}
const VERDICTS = { type: 'object', required: ['verdicts'], properties: { verdicts: { type: 'array', items: VERDICT_ITEM } } }

function reviewPrompt(dim) {
  const lines = [
    `관점 \`${dim}\`에서 ClauseTower 저장소(현재 작업 디렉터리)를 검토하라.`,
    `1. .claude/skills/ct-config-review/SKILL.md를 읽고 references/dimensions.md의 \`${dim}\` 절 점검 목록을 빠짐없이 확인하라.`,
    `2. 게이트 결과 JSON ${FACTS}의 summary·env·facts를 먼저 읽어라. 측정으로 드러난 문제부터 원인을 잡아라.`,
    '3. 지적마다 재현 명령(repro) 또는 파일:줄 인용을 evidence로 붙이고 해커톤 영향으로 심각도를 매겨라.',
    '4. 점검한 항목은 문제가 없어도 checked에 "항목: 결과 한 줄"로 남겨라.',
    '추적 중인 파일을 바꾸는 명령, 실제 LLM을 호출하는 명령은 실행하지 마라. 쓰기가 필요하면 _workspace/ 아래로 출력하라.',
  ]
  if (A.priorFindingsPath) lines.push(`이전 실행의 지적 목록: ${A.priorFindingsPath}. 이미 해소된 지적은 다시 보고하지 말고, 해소되지 않았거나 수정이 만든 새 문제만 보고하라.`)
  if (A.focus) lines.push(`사용자가 특히 살펴 달라고 한 점: ${A.focus}`)
  return lines.join('\n')
}

function batchVerifyPrompt(dim, findings) {
  return [
    `지적 검증 모드. 관점 \`${dim}\`의 지적 ${findings.length}건을 반박하는 입장에서 하나씩 검증하라.`,
    `.claude/skills/ct-config-review/SKILL.md의 「검증 절차」를 따르라. 게이트 결과 JSON: ${FACTS}`,
    '지적마다 repro를 직접 실행하거나 evidence의 파일:줄을 직접 열어 확인하고, 반대 증거(이미 막는 코드·시험·문서)를 찾아라.',
    '모든 id에 verdicts 항목을 하나씩 돌려줘라. 심각도가 해커톤 영향에 비해 과장되거나 과소하면 severity에 조정값을 넣고 reason에 이유를 적어라.',
    '지적 목록(JSON):',
    JSON.stringify(findings, null, 1),
  ].join('\n')
}

function lensPrompt(f, lens) {
  return [
    `지적 검증 모드, 렌즈 \`${lens}\`. 아래 지적 한 건을 반박하는 입장에서 이 렌즈에만 집중해 판정하라.`,
    `.claude/skills/ct-config-review/SKILL.md의 「검증 절차」 렌즈 표를 따르라. 게이트 결과 JSON: ${FACTS}`,
    `verdicts 배열에 id \`${f.id}\` 항목 하나만 돌려줘라.`,
    JSON.stringify(f, null, 1),
  ].join('\n')
}

function withIds(dim, review) {
  const list = review && Array.isArray(review.findings) ? review.findings : []
  return list.map((f, i) => Object.assign({ id: `${dim}-${i + 1}`, dimension: dim }, f))
}

function decide(f, verdicts) {
  const vs = verdicts.filter(Boolean)
  const nConfirmed = vs.filter(v => v.status === 'confirmed').length
  const nRefuted = vs.filter(v => v.status === 'refuted').length
  let status = 'uncertain'
  if (nConfirmed >= MAJORITY) status = 'confirmed'
  else if (nRefuted >= MAJORITY) status = 'refuted'
  const impact = vs.find(v => v.lens === 'impact' && v.severity) || vs.find(v => v.severity)
  return Object.assign({}, f, {
    original_severity: f.severity,
    severity: impact ? impact.severity : f.severity,
    status,
    votes: { confirmed: nConfirmed, refuted: nRefuted, total: LENSES.length, received: vs.length },
    verdicts: vs.map(v => ({ lens: v.lens, status: v.status, reason: v.reason, evidence: v.evidence || '' })),
  })
}

function verifyStandard(dim, findings) {
  return call('ct-verifier', batchVerifyPrompt(dim, findings), {
    label: `검증:${dim}`, phase: '검증', schema: VERDICTS,
  }).then(r => {
    const byId = {}
    for (const v of (r && r.verdicts) || []) byId[v.id] = Object.assign({ lens: 'batch' }, v)
    return findings.map(f => decide(f, byId[f.id] ? [byId[f.id]] : []))
  })
}

function verifyThorough(dim, findings) {
  return parallel(findings.map(f => () =>
    parallel(LENSES.map(lens => () =>
      call('ct-verifier', lensPrompt(f, lens), {
        label: `검증:${f.id}:${lens}`, phase: '검증', schema: VERDICTS,
      }).then(r => {
        const v = r && Array.isArray(r.verdicts) ? r.verdicts[0] : null
        return v ? Object.assign({ lens }, v) : null
      })))
      .then(vs => decide(f, vs))))
    .then(list => list.filter(Boolean))
}

phase('검토')
const perDim = await pipeline(
  DIMENSIONS,
  dim => call('ct-config-reviewer', reviewPrompt(dim), {
    label: `검토:${dim}`, phase: '검토', schema: FINDINGS,
  }),
  (review, dim) => {
    if (!review) return { dim, failed: true, findings: [], checked: [] }
    const findings = withIds(dim, review)
    const checked = Array.isArray(review.checked) ? review.checked : []
    if (!findings.length) return { dim, failed: false, findings: [], checked }
    const run = THOROUGH ? verifyThorough(dim, findings) : verifyStandard(dim, findings)
    return run.then(decided => ({ dim, failed: false, findings: decided, checked }))
  },
)

const done = perDim.filter(Boolean)
const failedDims = DIMENSIONS.filter(d => !done.find(x => x.dim === d && !x.failed))
if (failedDims.length) log(`검토를 마치지 못한 관점 ${failedDims.length}개: ${failedDims.join(', ')}`)

const all = done.flatMap(x => x.findings)
const bySeverity = (a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9)
const confirmed = all.filter(f => f.status === 'confirmed').sort(bySeverity)
const uncertain = all.filter(f => f.status === 'uncertain').sort(bySeverity)
const refuted = all.filter(f => f.status === 'refuted')
const noVerdict = all.filter(f => f.votes.received === 0).length
if (noVerdict) log(`검증 판정을 받지 못한 지적 ${noVerdict}건은 uncertain으로 두었다.`)
log(`지적 ${all.length}건 중 확정 ${confirmed.length}건, 보류 ${uncertain.length}건, 기각 ${refuted.length}건`)

const checked = {}
for (const x of done) checked[x.dim] = x.checked

return {
  mode: THOROUGH ? 'thorough' : 'standard',
  dimensions: DIMENSIONS,
  failed_dimensions: failedDims,
  stats: {
    total: all.length,
    confirmed: confirmed.length,
    uncertain: uncertain.length,
    refuted: refuted.length,
    by_severity: SEVERITIES.reduce((o, s) => { o[s] = confirmed.filter(f => f.severity === s).length; return o }, {}),
    by_owner: ['code', 'docs', 'user'].reduce((o, k) => { o[k] = confirmed.filter(f => f.fix_owner === k).length; return o }, {}),
  },
  confirmed,
  uncertain,
  refuted,
  checked,
}
