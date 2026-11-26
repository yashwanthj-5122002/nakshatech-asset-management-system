import assert from 'node:assert/strict'
import fs from 'node:fs'
import ts from 'typescript'

const source = fs.readFileSync(new URL('../src/lib/date.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
}).outputText
const { indiaDateInput } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

// Midnight in India is 18:30 UTC on the previous calendar day.
for (const [instant, expected] of [
  ['2026-11-03T18:29:59Z', '2026-11-03'],
  ['2026-11-03T18:30:00Z', '2026-11-04'],
  ['2026-10-31T20:00:00Z', '2026-11-01'],
  ['2026-12-31T20:00:00Z', '2027-01-01'],
  ['2028-02-28T20:00:00Z', '2028-02-29'],
  ['2026-11-04T12:00:00+05:30', '2026-11-04'],
]) {
  assert.equal(indiaDateInput(new Date(instant)), expected, instant)
}
console.log('India date inputs: all 6 calendar-boundary checks passed')
