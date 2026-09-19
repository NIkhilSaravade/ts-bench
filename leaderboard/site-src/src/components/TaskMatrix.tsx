import { Fragment, useState } from 'react'
import Reveal from './Reveal'
import Section from './Section'
import { attempts, instances, models } from '../lib/derived'
import { LANG_LABEL, month, taskNumber } from '../lib/format'

const shown = models
  .map((m, i) => ({ m, i }))
  .filter(({ m }) => m.attempts > 0)
  .sort((a, b) => b.m.resolved - a.m.resolved || b.m.attempts - a.m.attempts)

const counts = new Map<string, [number, number]>()
for (const [mi, ii, , code] of attempts) {
  const k = `${mi}:${ii}`
  const rec = counts.get(k) ?? [0, 0]
  rec[1] += 1
  if (code === 1) rec[0] += 1
  counts.set(k, rec)
}

export default function TaskMatrix() {
  const [col, setCol] = useState<number | null>(null)
  let current = ''
  return (
    <Section
      id="tasks"
      title="Every task, model by model"
      intro={<>Each cell is fixes over attempts. The date is when the real fix was merged into the project: the older it is, the more likely a model saw it during training. Hover a column to isolate a model.</>}
    >
      <Reveal>
        <div className="tscroll">
          <table className="data compact matrix">
            <thead>
              <tr>
                <th scope="col">Task</th>
                <th scope="col">Real fix merged</th>
                {shown.map(({ m }, c) => (
                  <th key={m.id} scope="col" className={`m ${col === c ? 'col-on' : ''}`} onMouseEnter={() => setCol(c)} onMouseLeave={() => setCol(null)}>{m.name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {instances.map((inst, ii) => {
                const head = inst.repo !== current
                current = inst.repo
                const n = instances.filter((i) => i.repo === inst.repo).length
                return (
                  <Fragment key={inst.id}>
                    {head && (
                      <tr className="grp"><th scope="colgroup" colSpan={2 + shown.length}>{inst.repo}<span className="small"> {LANG_LABEL[inst.language] ?? inst.language}, {n} tasks</span></th></tr>
                    )}
                    <tr>
                      <th scope="row">{taskNumber(inst.id)}</th>
                      <td className="small nowrap">{month(inst.merge_date)}</td>
                      {shown.map(({ i }, c) => {
                        const rec = counts.get(`${i}:${ii}`)
                        const cls = !rec ? 'none' : rec[0] > 0 ? 'hit' : ''
                        return (
                          <td key={i} className={`m ${col === c ? 'col-on' : ''}`} onMouseEnter={() => setCol(c)} onMouseLeave={() => setCol(null)}>
                            <span className={`mc ${cls}`}>{rec ? `${rec[0]}/${rec[1]}` : 'not run'}</span>
                          </td>
                        )
                      })}
                    </tr>
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      </Reveal>
    </Section>
  )
}
