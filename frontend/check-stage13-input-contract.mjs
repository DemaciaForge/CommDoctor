import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const sourcePath = fileURLToPath(new URL('./src/Stage13LmsApp.tsx', import.meta.url))
const source = readFileSync(sourcePath, 'utf8')
const input = source.match(/id="s13-mu"[^>]+/u)?.[0]
const defaultValue = source.match(/const \[mu, setMu\] = useState\('([^']+)'\)/u)?.[1]

assert.ok(input, 'Stage13 learning-rate input must exist')
assert.equal(defaultValue, '0.01', 'Stage13 default learning rate must remain 0.01')

const readAttribute = (name) => input.match(new RegExp(`${name}="([^"]+)"`, 'u'))?.[1]
const min = Number(readAttribute('min'))
const max = Number(readAttribute('max'))
const step = Number(readAttribute('step'))
const value = Number(defaultValue)

assert.ok(Number.isFinite(min) && Number.isFinite(max) && Number.isFinite(step))
assert.ok(value >= min && value <= max, 'default learning rate must be within min/max')
assert.ok(Math.abs((value - min) / step - Math.round((value - min) / step)) < 1e-9,
  'default learning rate must satisfy the native min/step grid')

console.log(`Stage13 learning-rate input contract OK: default=${defaultValue}, min=${min}, max=${max}, step=${step}`)
