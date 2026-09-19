import { useId, useMemo, useState, type ReactNode } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { Pause, Play, RotateCcw } from 'lucide-react'
import type { ArchEdge, ArchNode, NodeGroup, TraceStep } from '../types'
import { repoFile } from '../config'
import { useTicker } from '../lib/hooks'
import Reveal from './Reveal'

export const GROUP_LABEL: Record<NodeGroup, string> = {
  client: 'Sources and data',
  service: 'Orchestration',
  core: 'Evaluation core',
  ops: 'Model access',
  ship: 'Reporting',
}

interface Props {
  nodes: ArchNode[]
  edges: ArchEdge[]
  view: { x: number; y: number; w: number; h: number }
  groups: NodeGroup[]
  defaultNode: string
  ariaLabel: string
  idleCaption: string
  trace?: TraceStep[]
  traceLabel?: string
  /** optional per-group label overrides, e.g. the language seam calls its groups something else */
  groupLabels?: Partial<Record<NodeGroup, string>>
  after?: ReactNode
}

// the packet rides on the node's top-right corner so it never covers the label
const corner = (n: ArchNode): { x: number; y: number } => ({ x: n.x + n.w - 16, y: n.y + 16 })

function Detail({ node, groupLabel }: { node: ArchNode; groupLabel: string }) {
  return (
    <div className="arch-detail" aria-live="polite">
      <div className="ad-head">
        <h3>{node.title}</h3>
        <span className="tag">{groupLabel}</span>
      </div>
      <p className="body">{node.role}</p>
      <h4>Decisions inside it</h4>
      <ul className="bullets">{node.decisions.map((d) => <li key={d}>{d}</li>)}</ul>
      {node.limitation && <p className="limit"><b>Known limitation.</b> {node.limitation}</p>}
      {node.proof && <p className="proof"><b>Evidence.</b> {node.proof}</p>}
      <div className="files">
        {node.files.map((f) => {
          const href = repoFile(f)
          return href
            ? <a key={f} href={href} target="_blank" rel="noopener noreferrer"><code>{f}</code></a>
            : <code key={f}>{f}</code>
        })}
      </div>
    </div>
  )
}

/** A clickable system map. Selecting a box explains it; the optional trace walks one request through the map. */
export default function NodeMap({
  nodes, edges, view, groups, defaultNode, ariaLabel, idleCaption, trace, traceLabel = 'Trace an attempt', groupLabels, after,
}: Props) {
  const reduce = useReducedMotion()
  const uid = useId().replace(/:/g, '')
  const markerId = `ah-${uid}`
  const label = (g: NodeGroup): string => groupLabels?.[g] ?? GROUP_LABEL[g]
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes])
  const [selected, setSelected] = useState(defaultNode)
  const [hover, setHover] = useState<string | null>(null)
  const [step, setStep] = useState<number | null>(null)
  const [playing, setPlaying] = useState(false)

  const steps = trace ?? []
  const traceNode = step != null ? steps[step]?.node : undefined
  const focusId = hover ?? traceNode ?? selected
  const node = byId.get(traceNode ?? selected) ?? nodes[0]!

  useTicker(() => setStep((s) => {
    const n = (s ?? -1) + 1
    if (n >= steps.length) { setPlaying(false); return s }
    return n
  }), 2600, playing)

  const traceEdges = useMemo(() => {
    const set = new Set<string>()
    if (step != null && step > 0) {
      const a = steps[step - 1]?.node
      const b = steps[step]?.node
      edges.forEach((e) => { if ((e.from === a && e.to === b) || (e.from === b && e.to === a)) set.add(e.id) })
    }
    return set
  }, [step, steps, edges])

  const isHot = (e: ArchEdge): boolean => traceEdges.has(e.id) || e.from === focusId || e.to === focusId
  const dot = traceNode ? corner(byId.get(traceNode) ?? nodes[0]!) : null

  const start = () => { setStep(0); setPlaying(true) }
  const reset = () => { setPlaying(false); setStep(null) }

  return (
    <>
      <Reveal>
        <div className="arch">
          <div className="arch-bar">
            <div className="arch-legend" aria-label="Legend">
              {groups.map((g) => <span key={g} className={`lg lg-${g}`}><i />{label(g)}</span>)}
            </div>
            {steps.length > 0 && (
              <div className="row gap-2">
                {step == null ? (
                  <button className="btn primary" onClick={start}><Play size={14} />{traceLabel}</button>
                ) : (
                  <>
                    <button className="btn" onClick={() => setPlaying((p) => !p)}>{playing ? <Pause size={14} /> : <Play size={14} />}{playing ? 'Pause' : 'Resume'}</button>
                    <button className="btn" onClick={() => { setPlaying(false); setStep((s) => Math.min(steps.length - 1, (s ?? -1) + 1)) }}>Next</button>
                    <button className="btn" onClick={reset}><RotateCcw size={14} />Reset</button>
                  </>
                )}
              </div>
            )}
          </div>

          <div className="hscroll" tabIndex={0} role="group" aria-label={`${ariaLabel}, scrollable`}>
            <svg className="arch-svg" viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`} role="group" aria-label={ariaLabel}>
              <defs>
                <marker id={markerId} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
                </marker>
              </defs>
              {edges.map((e) => (
                <g key={e.id} className={`edge e-${e.kind} ${isHot(e) ? 'hot' : ''}`}>
                  <path d={e.d} fill="none" markerEnd={`url(#${markerId})`} />
                  {e.label && <text x={e.lx} y={e.ly} textAnchor={e.anchor ?? 'start'}>{e.label}</text>}
                </g>
              ))}
              {nodes.map((n) => {
                const on = n.id === focusId
                return (
                  <g
                    key={n.id} className={`node g-${n.group} ${on ? 'on' : ''}`} tabIndex={0} role="button"
                    aria-pressed={n.id === selected} aria-label={`${n.title}: ${n.sub}`}
                    onClick={() => { setSelected(n.id); reset() }}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(n.id); reset() } }}
                    onPointerEnter={() => setHover(n.id)} onPointerLeave={() => setHover(null)}
                    onFocus={() => setHover(n.id)} onBlur={() => setHover(null)}
                  >
                    <rect x={n.x} y={n.y} width={n.w} height={n.h} rx="6" />
                    <text className="nt" x={n.x + 16} y={n.y + 36}>{n.title}</text>
                    <text className="ns" x={n.x + 16} y={n.y + 60}>{n.sub}</text>
                  </g>
                )
              })}
              {dot && (
                <motion.circle
                  r="8" className="packet" initial={false}
                  animate={{ cx: dot.x, cy: dot.y }}
                  transition={reduce ? { duration: 0 } : { type: 'spring', stiffness: 90, damping: 18 }}
                />
              )}
            </svg>
          </div>

          <p className="trace-cap" aria-live="polite">
            {step != null
              ? <><b className="num">{step + 1} / {steps.length}.</b> {steps[step]?.caption}</>
              : idleCaption}
          </p>
        </div>
      </Reveal>

      <Reveal delay={0.05}><Detail node={node} groupLabel={label(node.group)} /></Reveal>
      {after}
    </>
  )
}
