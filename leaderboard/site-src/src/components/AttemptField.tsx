import { useEffect, useMemo, useState } from 'react'
import { useInView, useReducedMotion } from 'motion/react'
import { models, instances, attempts } from '../lib/derived'
import { taskName } from '../lib/format'
import { useWidth } from '../lib/hooks'

type Mode = 'model' | 'repo' | 'result'

const OUTCOME = ['Did not fix the bug', 'Fixed the bug', 'Tests ran out of time', 'Patch would not apply'] as const
const RESULT_LANES: [number, string][] = [[1, 'Fixed'], [0, 'Not fixed'], [2, 'Timed out'], [3, 'Patch did not apply']]

interface Lane { label: string; idxs: number[] }

function lanesFor(mode: Mode): Lane[] {
  const order = (a: number, b: number): number => {
    const x = attempts[a]!
    const y = attempts[b]!
    return x[0] - y[0] || x[1] - y[1] || x[2] - y[2]
  }
  const all = attempts.map((_, i) => i)
  let lanes: Lane[]
  if (mode === 'model') {
    lanes = models.map((m, mi) => ({ label: m.name, idxs: all.filter((i) => attempts[i]![0] === mi) }))
  } else if (mode === 'repo') {
    const repos = [...new Set(instances.map((i) => i.repo))].sort()
    lanes = repos.map((r) => ({ label: r, idxs: all.filter((i) => instances[attempts[i]![1]]!.repo === r) }))
  } else {
    lanes = RESULT_LANES.map(([code, label]) => ({ label, idxs: all.filter((i) => attempts[i]![3] === code) }))
  }
  return lanes.filter((l) => l.idxs.length > 0).map((l) => ({ ...l, idxs: [...l.idxs].sort(order) }))
}

interface Placed { x: number; y: number; order: number }
interface Layout { cells: Placed[]; labels: { y: number; label: string; meta: string }[]; height: number }

function layoutFor(mode: Mode, width: number, size: number, gap: number): Layout {
  const step = size + gap
  const cols = Math.max(1, Math.floor((width + gap) / step))
  const cells: Placed[] = new Array(attempts.length)
  const labels: Layout['labels'] = []
  let y = 0
  let order = 0
  for (const lane of lanesFor(mode)) {
    const fixed = lane.idxs.filter((i) => attempts[i]![3] === 1).length
    labels.push({ y, label: lane.label, meta: `${fixed} of ${lane.idxs.length} fixed` })
    y += 28
    lane.idxs.forEach((idx, k) => {
      cells[idx] = { x: (k % cols) * step, y: y + Math.floor(k / cols) * step, order: order++ }
    })
    y += Math.ceil(lane.idxs.length / cols) * step + 26
  }
  return { cells, labels, height: Math.max(120, y - 10) }
}

/** One square per real attempt. Regroup by model, repository or result and the squares glide to their new lanes. */
export default function AttemptField({ initialMode = 'model' }: { initialMode?: Mode }) {
  const [ref, width] = useWidth<HTMLDivElement>(900)
  const inView = useInView(ref, { once: true, margin: '0px 0px -12% 0px' })
  const [mode, setMode] = useState<Mode>(initialMode)
  const [phase, setPhase] = useState<'hidden' | 'reveal' | 'done'>('hidden')
  const [tip, setTip] = useState<{ x: number; y: number; i: number } | null>(null)

  const reduce = useReducedMotion()

  useEffect(() => {
    // Reduced motion: show everything at once. Otherwise reveal when scrolled into view, with a
    // fallback timer so the squares can never stay hidden if the visibility signal never arrives.
    if (reduce) { setPhase('done'); return }
    if (!inView) {
      const fallback = window.setTimeout(() => setPhase((p) => (p === 'hidden' ? 'done' : p)), 5000)
      return () => window.clearTimeout(fallback)
    }
    setPhase('reveal')
    const t = window.setTimeout(() => setPhase('done'), 2200)
    return () => window.clearTimeout(t)
  }, [inView, reduce])

  const small = width < 560
  const size = small ? 9 : 12
  const gap = small ? 2 : 3
  const layout = useMemo(() => layoutFor(mode, width, size, gap), [mode, width, size, gap])

  const onMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const el = (e.target as HTMLElement).closest<HTMLElement>('.cell')
    if (el?.dataset.i) setTip({ x: e.clientX, y: e.clientY, i: Number(el.dataset.i) })
    else setTip(null)
  }
  const tipAttempt = tip ? attempts[tip.i] : undefined

  return (
    <div>
      <div className="row between wrap-row mb-3">
        <div className="seg" role="group" aria-label="Group attempts by">
          {(['model', 'repo', 'result'] as const).map((m) => (
            <button key={m} aria-pressed={mode === m} onClick={() => setMode(m)}>
              {m === 'model' ? 'Model' : m === 'repo' ? 'Repository' : 'Result'}
            </button>
          ))}
        </div>
        <ul className="legend field-legend" aria-label="Legend">
          <li><i className="cell c1 static" />Fixed</li>
          <li><i className="cell c0 static" />Not fixed</li>
          <li><i className="cell c2 static" />Timed out</li>
          <li><i className="cell c3 static" />Patch did not apply</li>
        </ul>
      </div>
      <div
        ref={ref} className="stage" style={{ height: layout.height }}
        role="img" aria-label={`${attempts.length} squares, one per attempt. The same figures are in the scoreboard below.`}
        onPointerMove={onMove} onPointerLeave={() => setTip(null)}
      >
        {layout.labels.map((l) => (
          <p key={l.label} className="lane-label" style={{ top: l.y, opacity: phase === 'hidden' ? 0 : 1 }}>
            <b>{l.label}</b><span>{l.meta}</span>
          </p>
        ))}
        {attempts.map(([, , , code], i) => {
          const c = layout.cells[i]!
          const revealDelay = phase === 'reveal' ? Math.min(c.order * 1.2, 900) : 0
          const moveDelay = phase === 'done' ? Math.min(c.order * 0.6, 420) : 0
          return (
            <i
              key={i} data-i={i} className={`cell c${code}`}
              style={{
                width: size, height: size,
                transform: `translate(${c.x}px, ${c.y}px)`,
                opacity: phase === 'hidden' ? 0 : 1,
                transition: `transform 0.7s var(--ease-out) ${moveDelay}ms, opacity 0.5s ease ${revealDelay}ms`,
              }}
            />
          )
        })}
      </div>
      {tip && tipAttempt && (
        <div className="tip" style={{ left: Math.min(tip.x + 14, window.innerWidth - 240), top: tip.y + 18 }} role="tooltip">
          <b>{models[tipAttempt[0]]!.name}</b>
          <span className="block">{taskName(tipAttempt[1])}</span>
          <span className="block">Attempt {tipAttempt[2] + 1}</span>
          <em>{OUTCOME[tipAttempt[3]]}</em>
        </div>
      )}
    </div>
  )
}
