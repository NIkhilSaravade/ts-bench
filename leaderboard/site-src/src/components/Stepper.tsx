import { useState } from 'react'
import Reveal from './Reveal'
import { useTicker } from '../lib/hooks'

export interface Step {
  name: string
  code: string
  text: string
}

/** A row of steps you can click through or auto-play, with the current step explained underneath. */
export default function Stepper({ steps, label }: { steps: readonly Step[]; label: string }) {
  const [it, setIt] = useState(0)
  const [play, setPlay] = useState(false)
  useTicker(() => setIt((i) => (i + 1) % steps.length), 2600, play)
  return (
    <Reveal>
      <div className="arch">
        <div className="arch-bar">
          <div className="seg wrap-seg" role="group" aria-label={label} style={{ marginBottom: 0 }}>
            {steps.map((s, i) => <button key={s.name} aria-pressed={it === i} onClick={() => { setPlay(false); setIt(i) }}>{s.name}</button>)}
          </div>
          <button className="btn" onClick={() => setPlay((p) => !p)}>{play ? 'Pause' : 'Auto-play'}</button>
        </div>
        <ol className="iter" aria-label={label}>
          {steps.map((s, i) => (
            <li key={s.name} className={i === it ? 'on' : i < it ? 'done' : ''}><code>{s.code}</code></li>
          ))}
        </ol>
        <p className="trace-cap" aria-live="polite"><b>{steps[it]?.name}.</b> {steps[it]?.text}</p>
      </div>
    </Reveal>
  )
}
