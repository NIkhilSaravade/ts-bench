import {
  BookOpen, FlaskConical, Gauge, GitBranch, Layers, Network, Plug, Route, Scale, Server, ShieldCheck, Table2, Terminal, Wrench,
  type LucideIcon,
} from 'lucide-react'

export interface NavItem {
  id: string
  label: string
  icon: LucideIcon
}
export interface NavGroup {
  title: string
  items: NavItem[]
}

export const NAV: NavGroup[] = [
  {
    title: 'The result',
    items: [
      { id: 'overview', label: 'Overview', icon: BookOpen },
      { id: 'results', label: 'Scoreboard', icon: Gauge },
      { id: 'tasks', label: 'Task by task', icon: Table2 },
    ],
  },
  {
    title: 'How it is built',
    items: [
      { id: 'architecture', label: 'System design', icon: Network },
      { id: 'pipeline', label: 'Proving a task', icon: GitBranch },
      { id: 'scoring', label: 'Scoring an attempt', icon: FlaskConical },
      { id: 'seam', label: 'Language seam', icon: Plug },
      { id: 'scale', label: 'At scale', icon: Server },
      { id: 'journey', label: 'Build order', icon: Route },
      { id: 'stack', label: 'Tech stack', icon: Layers },
    ],
  },
  {
    title: 'Proof',
    items: [{ id: 'verification', label: 'Verification', icon: ShieldCheck }],
  },
  {
    title: 'Honesty',
    items: [
      { id: 'problems', label: 'Problems fixed', icon: Wrench },
      { id: 'limitations', label: 'Limitations', icon: Scale },
      { id: 'reproduce', label: 'Reproduce', icon: Terminal },
    ],
  },
]

export const SECTION_IDS: readonly string[] = NAV.flatMap((g) => g.items.map((i) => i.id))
