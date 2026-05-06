import { useState } from 'react'
import Header from './components/Header'
import ChatWindow from './components/ChatWindow'
import PhaseIndicator from './components/PhaseIndicator'

const SESSION_KEY = 'mortgage_session_id'

function generateId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    try { return crypto.randomUUID() } catch (_) { /* non-secure context */ }
  }
  return 'xxxx-xxxx-xxxx'.replace(/x/g, () => Math.floor(Math.random() * 16).toString(16))
}

function getOrCreateSessionId() {
  const stored = localStorage.getItem(SESSION_KEY)
  if (stored) return stored
  const id = generateId()
  localStorage.setItem(SESSION_KEY, id)
  return id
}

function App() {
  const [sessionId] = useState(getOrCreateSessionId)
  const [phase, setPhase] = useState('GREETING')

  return (
    <div className="h-screen flex flex-col bg-bank-light">
      <Header />
      <PhaseIndicator phase={phase} />
      <main className="flex-1 overflow-hidden">
        <ChatWindow sessionId={sessionId} onPhaseChange={setPhase} />
      </main>
    </div>
  )
}

export default App
