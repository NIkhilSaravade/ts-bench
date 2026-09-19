import NodeMap from './NodeMap'
import Replay from './Replay'
import Stepper from './Stepper'
import Section, { Sub } from './Section'
import { ARCH_VIEW, EDGES, GROUPS, NODES, TRACE } from '../content/architecture'
import { SEAM_EDGES, SEAM_NODES, SEAM_VIEW } from '../content/seam'
import {
  SCALE_EDGES, SCALE_NODES, SCALE_SCENARIOS, SCALE_VIEW, SCORING_STEPS, TASK_EDGES, TASK_NODES, TASK_SCENARIOS, TASK_VIEW,
} from '../content/flows'

export function SystemDesign() {
  return (
    <Section
      id="architecture"
      title="How it is built"
      intro="Twelve components in five groups. Click any of them, or trace one attempt from a merged pull request all the way to the number on this page."
    >
      <NodeMap
        nodes={NODES} edges={EDGES} view={ARCH_VIEW} groups={[...GROUPS]} defaultNode="eval"
        trace={TRACE} traceLabel="Trace an attempt" ariaLabel="System map of the benchmark"
        idleCaption="Solid lines carry the main path, dashed lines carry control traffic. Selecting a component explains what it decides."
      />
    </Section>
  )
}

export function Pipeline() {
  return (
    <Section
      id="pipeline"
      title="Proving a task is fair"
      intro="The hard part of a benchmark is trusting the tasks. Every candidate passes this gate before it is admitted, and most of the ways it can fail are logged, not hidden."
    >
      <Sub title="The life of a candidate">
        A task is admitted only if its tests fail before the human fix and pass after it. Pick a path and replay it.
      </Sub>
      <Replay view={TASK_VIEW} nodes={TASK_NODES} edges={TASK_EDGES} scenarios={TASK_SCENARIOS} ariaLabel="State machine for validating a task" />
    </Section>
  )
}

export function Scoring() {
  return (
    <Section
      id="scoring"
      title="Scoring one attempt"
      intro="The agent works in one place and is scored in another. Scoring starts from a clean rebuild the agent never touched, and the order of the steps is what stops it from cheating."
    >
      <Stepper steps={SCORING_STEPS} label="Scoring step" />
      <p className="small hint">
        Each attempt ends as one of four statuses: ok, patch_apply_failed, timeout or infra_error. Only ok can be fixed, and infra_error is
        our own failure, so it is left out of the score instead of being held against a model.
      </p>
    </Section>
  )
}

export function Seam() {
  return (
    <Section
      id="seam"
      title="One interface, three languages"
      intro="Only four things depend on the language: how to detect the environment, install, run the tests and read the results. Everything else is shared, and that boundary was tested by adding two more languages."
    >
      <NodeMap
        nodes={SEAM_NODES} edges={SEAM_EDGES} view={SEAM_VIEW} groups={['service', 'ops', 'core', 'client']} defaultNode="ts"
        ariaLabel="The language adapter interface and its three implementations"
        groupLabels={{ service: 'Language-agnostic core', ops: 'Factory', core: 'Interface', client: 'Language adapters' }}
        idleCaption="Select an adapter to see what it does differently, and what it learned the hard way."
      />
    </Section>
  )
}

export function Scale() {
  return (
    <Section
      id="scale"
      title="Running it at scale"
      intro="Model by task by repeat quickly becomes hundreds of runs. A queue turns that into parallel workers, provided a replayed or half-finished job can never create a duplicate result."
    >
      <Replay view={SCALE_VIEW} nodes={SCALE_NODES} edges={SCALE_EDGES} scenarios={SCALE_SCENARIOS} ariaLabel="Job queue with three workers" stepMs={1000} />
      <p className="small hint">
        Verified on a real single-broker Kafka and a local Kubernetes cluster, in two runs of 15 and 30 jobs. The demo image baked in only the Python tasks to
        stay small, so it proves the queue mechanism and not the full task set.
      </p>
    </Section>
  )
}
