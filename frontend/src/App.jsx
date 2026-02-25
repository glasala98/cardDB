import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import Navbar from './components/Navbar'
import Login from './pages/Login'
import CardLedger from './pages/CardLedger'
import CardInspect from './pages/CardInspect'
import Portfolio from './pages/Portfolio'
import MasterDB from './pages/MasterDB'
import NHLStats from './pages/NHLStats'
import styles from './App.module.css'

function AppShell() {
  return (
    <div className={styles.layout}>
      <Navbar />
      <main className={styles.main}>
        <Routes>
          <Route path="/" element={<Navigate to="/ledger" replace />} />
          <Route path="/ledger"          element={<ProtectedRoute><CardLedger /></ProtectedRoute>} />
          <Route path="/ledger/:cardName" element={<ProtectedRoute><CardInspect /></ProtectedRoute>} />
          <Route path="/portfolio"       element={<ProtectedRoute><Portfolio /></ProtectedRoute>} />
          <Route path="/master-db"       element={<ProtectedRoute><MasterDB /></ProtectedRoute>} />
          <Route path="/nhl-stats"       element={<ProtectedRoute><NHLStats /></ProtectedRoute>} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/*"     element={<AppShell />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
