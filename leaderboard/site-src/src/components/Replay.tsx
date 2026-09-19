import { useId, useState } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { Play } from 'lucide-react'
import { useTicker } from '../lib/hooks'
import Reveal from './Reveal'

export interface RNode {
  id: string
  x: number
  y: number
  w: number
  h?: number
  label: string
  sub: string
  group?: 'core' | 'service' | 'client' | 'ops' | 'ship' | 'bad'
}
export interface REdge {
  d: string
  label?: string
  lx?: number
  ly?: number
  kind?: 'request' | 'control'
}
export interface Scenario {
  id: string
  label: string
  path: string[]
  caption: string
}

interface Props {
  view: string
  nodes: RNode[]
  edges: REdge[]
  scenarios: Scenario[]
  ariaLabel: string
  /** ms between moves of the marker */
  stepMs?: number
}

/** A state machine you can replay: pick a scenario and a marker walks its path, with a caption for what happened. */
export default function Replay({ view, nodes, edges, scenarios, ariaLabel, stepMs = 1100 }: Props) {
  const reduce = useReducedMotion()
  const uid = useId().replace(/:/g, '')
  const marker = `rp-${uid}`
  const [sid, setSid] = useState(scenarios[0]!.id)
  const [pos, setPos] = useState(0)
  const [playing, setPlaying] = useState(false)
  const sc = scenarios.find((s) => s.id === sid) ?? scenarios[0]!
  const here = sc.path[Math.min(pos, sc.path.length - 1)] ?? sc.path[0]!
  const node = nodes.find((n) => n.id === here) ?? nodes[0]!
  const at = { x: node.x + node.w - 16, y: node.y + 16 }

  useTicker(() => setPos((p) => { if (p + 1 >= sc.path.length) { setPlaying(false); return p } return p + 1 }), stepMs, playing)
  const run = (id: string) => { setSid(id); setPos(0); setPlaying(true) }

  return (
    <Reveal>
      <div className="arch">
        <div className="arch-bar">
          <div className="seg" role="group" aria-label="Scenario">
            {scenarios.map((s) => <button key={s.id} aria-pressed={sid === s.id} onClick={() => run(s.id)}>{s.label}</button>)}
          </div>
          <button className="btn primary" onClick={() => run(sid)}><Play size={14} />Replay</button>
        </div>
        <div className="hscroll" tabIndex={0} role="group" aria-label={`${ariaLabel}, scrollable`}>
          <svg className="life-svg" viewBox={view} role="group" aria-label={ariaLabel}>
            <defs>
              <marker id={marker} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
              </marker>
            </defs>
            {edges.map((e, i) => (
              <g key={i} className={`edge ${e.kind === 'control' ? 'e-control' : 'e-request'}`}>
                <path d={e.d} fill="none" markerEnd={`url(#${marker})`} />
                {e.label && <text x={e.lx} y={e.ly}>{e.label}</text>}
              </g>
            ))}
            {nodes.map((n) => (
              <g key={n.id} className={`node g-${n.group ?? 'core'} ${here === n.id ? 'on' : ''}`}>
                <rect x={n.x} y={n.y} width={n.w} height={n.h ?? 64} rx="6" />
                <text className="nt" x={n.x + 14} y={n.y + 27}>{n.label}</text>
                <text className="ns" x={n.x + 14} y={n.y + 48}>{n.sub}</text>
              </g>
            ))}
            <motion.circle
              r="8" className="packet" initial={false} animate={{ cx: at.x, cy: at.y }}
              transition={reduce ? { duration: 0 } : { type: 'spring', stiffness: 140, damping: 20 }}
            />
          </svg>
        </div>
        <p className="trace-cap" aria-live="polite">{sc.caption}</p>
      </div>
    </Reveal>
  )
}
