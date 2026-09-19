import { useEffect, useState } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { ExternalLink, Menu, Moon, Sun, X } from 'lucide-react'
import { NAV, SECTION_IDS } from '../nav'
import { useScrollProgress, useScrollSpy } from '../lib/hooks'
import { config } from '../config'

type Theme = 'dark' | 'light'

function readTheme(): Theme {
  return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark'
}

function Mark() {
  return (
    <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="var(--accent)" />
      <path d="M8 16.5 L13.5 22 L24 10" fill="none" stroke="var(--accent-ink)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export default function Sidebar() {
  const active = useScrollSpy(SECTION_IDS)
  const progress = useScrollProgress()
  const reduce = useReducedMotion()
  const [theme, setTheme] = useState<Theme>(readTheme)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem('theme', theme) } catch { /* private mode */ }
  }, [theme])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => { window.removeEventListener('keydown', onKey); document.body.style.overflow = '' }
  }, [open])

  return (
    <>
      <header className="topbar">
        <a className="brand" href="#overview"><Mark />ts-bench</a>
        <button className="icon-btn" onClick={() => setOpen(true)} aria-label="Open navigation" aria-expanded={open} aria-controls="sidebar">
          <Menu size={18} />
        </button>
      </header>
      {open && <button className="scrim" aria-label="Close navigation" onClick={() => setOpen(false)} />}

      <aside id="sidebar" className={`sidebar ${open ? 'open' : ''}`} aria-label="Site navigation">
        <div className="sidebar-head">
          <a className="brand" href="#overview" onClick={() => setOpen(false)}>
            <Mark />
            <span>ts-bench<small>Benchmarking AI coding agents</small></span>
          </a>
          <button className="icon-btn close" onClick={() => setOpen(false)} aria-label="Close navigation"><X size={18} /></button>
        </div>

        <nav className="side-nav" aria-label="Sections">
          {NAV.map((g) => (
            <div key={g.title} className="side-group">
              <div className="side-title">{g.title}</div>
              <ul>
                {g.items.map((it) => {
                  const Icon = it.icon
                  const on = active === it.id
                  return (
                    <li key={it.id}>
                      <a href={`#${it.id}`} className={on ? 'on' : ''} aria-current={on ? 'true' : undefined} onClick={() => setOpen(false)}>
                        {on && (
                          <motion.span
                            layoutId="nav-active" className="pill" aria-hidden="true"
                            transition={reduce ? { duration: 0 } : { type: 'spring', stiffness: 520, damping: 40 }}
                          />
                        )}
                        <Icon size={16} strokeWidth={1.75} aria-hidden="true" />
                        <span>{it.label}</span>
                      </a>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </nav>

        <div className="side-foot">
          <div className="progress" aria-hidden="true"><i style={{ transform: `scaleX(${progress})` }} /></div>
          <div className="row between">
            <button className="btn-quiet" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
              {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
              <span>{theme === 'dark' ? 'Light' : 'Dark'} theme</span>
            </button>
            {config.repoUrl && (
              <a className="btn-quiet" href={config.repoUrl} target="_blank" rel="noopener noreferrer">
                <ExternalLink size={15} /><span>Source</span>
              </a>
            )}
          </div>
        </div>
      </aside>
    </>
  )
}
