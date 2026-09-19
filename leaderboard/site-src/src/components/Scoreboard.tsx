import { motion } from 'motion/react'
import Reveal, { EASE_OUT } from './Reveal'
import Section from './Section'
import { data } from '../data'
import { excludedTotal, top } from '../lib/derived'
import { money, pct } from '../lib/format'
import type { Model } from '../types'

const AXIS_MAX = 0.6
const COLOR: Record<string, string> = {
  'claude-haiku': 'var(--s-haiku)',
  'qwen2.5-coder': 'var(--s-qwen25)',
  codestral: 'var(--s-codestral)',
  'qwen3:14b': 'var(--s-qwen3)',
}
const colorOf = (m: Model): string => Object.entries(COLOR).find(([k]) => m.id.includes(k))?.[1] ?? 'var(--muted)'

function Range({ m }: { m: Model }) {
  if (m.attempts === 0 || m.ci_low == null || m.ci_high == null || m.rate == null) return <span className="small">Never run</span>
  const left = (m.ci_low / AXIS_MAX) * 100
  const width = Math.max(((m.ci_high - m.ci_low) / AXIS_MAX) * 100, 0.8)
  const dot = (m.rate / AXIS_MAX) * 100
  return (
    <div className="rng" aria-label={`95% range ${pct(m.ci_low)} to ${pct(m.ci_high)}`}>
      <div className="rng-track">
        <motion.i
          className="rng-band" style={{ left: `${left}%`, width: `${width}%` }}
          initial={{ scaleX: 0 }} whileInView={{ scaleX: 1 }} viewport={{ once: true }} transition={{ duration: 0.9, ease: EASE_OUT }}
        />
        <motion.b
          className="rng-dot" style={{ left: `${dot}%` }}
          initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: true }} transition={{ duration: 0.4, delay: 0.5 }}
        />
      </div>
      <span className="small num">{pct(m.ci_low)} to {pct(m.ci_high)}</span>
    </div>
  )
}

function StatusTag({ m }: { m: Model }) {
  if (m.status === 'not_run') return <span className="tag">Not run</span>
  if (m.status === 'partial') return <span className="tag warn-tag">Stopped early</span>
  return <span className="tag">Complete</span>
}

export default function Scoreboard() {
  const order = [...data.models].sort((a, b) => Number(a.status === 'not_run') - Number(b.status === 'not_run') || b.resolved - a.resolved || b.attempts - a.attempts)
  return (
    <Section
      id="results"
      title="Who fixed what"
      intro={<>Models with zero fixes are tied, so they are not ranked. The bar is the range the true fix rate probably sits in, given how few attempts there are: a wide bar means low confidence.</>}
    >
      <Reveal>
        <div className="chart">
          <div className="chart-top">
            <div>
              <div className="chart-title">Bugs fixed by each model</div>
              <div className="chart-sub">Fix rate is fixed attempts over counted attempts. Bar scale is 0 to 60%. Our own infrastructure failures are excluded from the count; timeouts and patches that would not apply are not.</div>
            </div>
            <span className="tag measured">Measured</span>
          </div>
          <div className="tscroll">
            <table className="data score">
              <thead>
                <tr>
                  <th scope="col">Model</th>
                  <th scope="col" className="r">Fixed</th>
                  <th scope="col">Likely range (95%)</th>
                  <th scope="col" className="r">Cost</th>
                  <th scope="col" className="r">Tasks covered</th>
                  <th scope="col">Run</th>
                </tr>
              </thead>
              <tbody>
                {order.map((m) => (
                  <tr key={m.id} className={`${m.id === top.id ? 'hero-row' : ''} ${m.status === 'not_run' ? 'off-row' : ''}`}>
                    <th scope="row">
                      <span className="mname"><i className="dot" style={{ background: colorOf(m) }} />{m.name}</span>
                      <span className="small block">{m.maker}, {m.tier === 'paid' ? 'paid API' : 'local, free'}</span>
                    </th>
                    <td className="r num big">{m.attempts ? <><b>{m.resolved}</b> of {m.attempts}</> : 'No data'}</td>
                    <td><Range m={m} /></td>
                    <td className="r num">{m.attempts ? (m.cost_usd ? money(m.cost_usd) : 'Free') : 'None'}</td>
                    <td className="r num">{m.attempts ? `${m.instances_covered} of ${m.instances_total}` : 'None'}</td>
                    <td><StatusTag m={m} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="note">
            Paid spend was {money(top.cost_usd)} of a $10 budget, about {money(top.cost_per_attempt ?? 0)} per attempt. A further{' '}
            {data.smoke_test.attempts} attempts by {data.smoke_test.model} ({money(data.smoke_test.cost_usd)}) were early smoke tests, fixed{' '}
            {data.smoke_test.resolved}, and are too few to rank. {excludedTotal === 0 ? 'None of the attempts shown were excluded.' : `${excludedTotal} attempts were excluded.`}
          </p>
        </div>
      </Reveal>
    </Section>
  )
}
