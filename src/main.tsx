import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import { registerSW } from 'virtual:pwa-register'
import './index.css'
import App from './App'
import { AppStateProvider } from './state/AppState'
import { WorkoutProvider } from './state/WorkoutState'

// Service Worker: neue Version im Hintergrund laden und beim nächsten Start aktivieren.
registerSW({ immediate: true })

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <HashRouter>
      <AppStateProvider>
        <WorkoutProvider>
          <App />
        </WorkoutProvider>
      </AppStateProvider>
    </HashRouter>
  </StrictMode>,
)
