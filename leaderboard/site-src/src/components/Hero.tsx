import type { ReactNode } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import Reveal, { EASE_OUT } from './Reveal'
import AttemptField from './AttemptField'
import { problems } from '../content/problems'
import { dataset, leadFixes, leadRepoShort, localAttempts, localResolved, models, top, totals } from '../lib/derived'
import { pct } from '../lib/format'

/** The one authored moment: the headline rises out of a clip, line by line. */
function Line({ children, i }: { children: ReactNode; i: number }) {
  const reduce = useReducedMotion()
  return (
    <span className="clip">
      <motion.span
        initial={reduce ? false : { y: '108%' }}
        animate={{ y: 0 }}
        transition={{ duration: 1, delay: 0.1 + i * 0.12, ease: EASE_OUT }}
      >
        {children}
      </motion.span>
    </span>
  )
}

function Row({ k, children, warn }: { k: string; children: ReactNode; warn?: boolean }) {
  return (
    <div className={`brief-row ${warn ? 'warn-row' : ''}`}>
      <dt>{k}</dt>
      <dd>{children}</dd>
    </div>
  )
}

export default function Hero() {
  return (
    <section id="overview" className="hero" aria-labelledby="overview-h">
      <div className="hero-grid" aria-hidden="true" />
      <h1 id="overview-h">
        <Line i={0}>Benchmarking AI</Line>
        <Line i={1}>agents is an <em>integrity</em></Line>
        <Line i={2}>problem.</Line>
      </h1>

      <Reveal delay={0.55} className="hero-sub">
        <p className="lede">
          A benchmark for AI coding agents on real bugs from open-source projects, where most of the engineering is the machinery that
          makes a score believable.
        </p>
      </Reveal>

      <Reveal delay={0.7} className="brief">
        <h2 className="brief-title">The whole page in thirty seconds</h2>
        <dl>
          <Row k="What it is">
            An end-to-end evaluation system. It mines real fixes from open-source repositories, proves that each one is a fair task,
            runs models against them in isolated sandboxes, and scores every patch with the project's own tests. It covers{' '}
            <b>TypeScript, Python and Java</b> through one adapter interface.
          </Row>
          <Row k="What it found">
            <b className="num">{totals.resolved} fixes in {totals.attempts} attempts</b> across {totals.models_with_data} models.
            Only {top.name} fixed anything: <b className="num">{top.resolved} of {top.attempts}</b>, with a 95% range of{' '}
            {pct(top.ci_low ?? 0)} to {pct(top.ci_high ?? 0)}, and {leadFixes} of those in {leadRepoShort}. The free local models fixed{' '}
            <b className="num">{localResolved} of {localAttempts}</b>.
          </Row>
          <Row k="How it is proven">
            A task exists only if its tests fail before the human fix and pass after it, confirmed over three runs. Through the real
            runner, the human fix resolves all <b className="num">{dataset.instances}</b> tasks and an empty patch resolves none.
          </Row>
          <Row k="What went wrong">
            {problems.length} real problems, from a benchmark that silently scored a broken patch as our own fault to a global setting that
            broke every install. Each is written up with the wrong assumption behind it. <a href="#problems">Read the log</a>.
          </Row>
          <Row k="How far to trust it" warn>
            <b>Not far, yet.</b> The sample is small, the only model with fixes got one attempt per task, some planned models are missing,
            and older tasks may be in training data. <a href="#limitations">Read the limits</a> before quoting a number.
          </Row>
        </dl>
      </Reveal>

      <Reveal delay={0.1} y={22} className="hero-chart">
        <div className="chart">
          <div className="chart-top">
            <div>
              <div className="chart-title">Every attempt</div>
              <div className="chart-sub">
                One square per real attempt, {totals.attempts} in total. Hover or tap a square for the model, the task and the outcome.
              </div>
            </div>
            <span className="tag measured">Measured</span>
          </div>
          <AttemptField />
        </div>
        <p className="note">
          Nothing on this page is a projection. The {models.filter((m) => m.attempts > 0).length} models with data are shown as they ran, and a model that never ran
          is shown as not run, not as zero.
        </p>
      </Reveal>
    </section>
  )
}
