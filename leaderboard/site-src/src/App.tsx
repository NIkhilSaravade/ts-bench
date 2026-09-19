import Sidebar from './components/Sidebar'
import Hero from './components/Hero'
import Scoreboard from './components/Scoreboard'
import TaskMatrix from './components/TaskMatrix'
import { Pipeline, Scale, Scoring, Seam, SystemDesign } from './components/Design'
import { Journey, Limitations, Reproduce, Stack, Verification } from './components/Story'
import Problems from './components/Problems'

export default function App() {
  return (
    <div className="shell">
      <Sidebar />
      <main id="main" className="content">
        <Hero />
        <Scoreboard />
        <TaskMatrix />
        <SystemDesign />
        <Pipeline />
        <Scoring />
        <Seam />
        <Scale />
        <Journey />
        <Stack />
        <Verification />
        <Problems />
        <Limitations />
        <Reproduce />
        <footer className="foot">
          ts-bench. A benchmark for AI coding agents built to make a score believable, and to say plainly when it is not yet.
        </footer>
      </main>
    </div>
  )
}
