import { Route, Routes } from 'react-router-dom'
import { TabBar } from './components/TabBar'
import { Toasts } from './components/Toasts'
import { useApp } from './state/AppState'
import Today from './screens/Today'
import ActiveWorkout from './screens/ActiveWorkout'
import WorkoutSummary from './screens/WorkoutSummary'
import History from './screens/History'
import SessionDetail from './screens/SessionDetail'
import Stats from './screens/Stats'
import ExerciseLibrary from './screens/ExerciseLibrary'
import ExerciseDetail from './screens/ExerciseDetail'
import RoutineEditor from './screens/RoutineEditor'
import Routines from './screens/Routines'
import Programs from './screens/Programs'
import BodyMetrics from './screens/BodyMetrics'
import Achievements from './screens/Achievements'
import SettingsScreen from './screens/Settings'

export default function App() {
  const { ready } = useApp()

  if (!ready) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <div className="text-3xl font-bold tracking-tight">Lift</div>
          <div className="mt-2 text-sm text-mute">Daten werden geladen…</div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-full">
      <Routes>
        <Route path="/" element={<Today />} />
        <Route path="/workout" element={<ActiveWorkout />} />
        <Route path="/summary/:id" element={<WorkoutSummary />} />
        <Route path="/history" element={<History />} />
        <Route path="/history/:id" element={<SessionDetail />} />
        <Route path="/stats" element={<Stats />} />
        <Route path="/exercises" element={<ExerciseLibrary />} />
        <Route path="/exercises/:id" element={<ExerciseDetail />} />
        <Route path="/routines" element={<Routines />} />
        <Route path="/routines/:id" element={<RoutineEditor />} />
        <Route path="/programs" element={<Programs />} />
        <Route path="/body" element={<BodyMetrics />} />
        <Route path="/achievements" element={<Achievements />} />
        <Route path="/settings" element={<SettingsScreen />} />
        <Route path="*" element={<Today />} />
      </Routes>
      <TabBar />
      <Toasts />
    </div>
  )
}
