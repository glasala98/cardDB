import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import { CurrencyProvider } from './context/CurrencyContext'
import ProtectedRoute from './components/ProtectedRoute'
import Navbar from './components/Navbar'
import Login from './pages/Login'
import CardLedger from './pages/CardLedger'
import CardInspect from './pages/CardInspect'
import Portfolio from './pages/Portfolio'
import MasterDB from './pages/MasterDB'
import NHLStats from './pages/NHLStats'
import Archive from './pages/Archive'
import Charts from './pages/Charts'
import Admin from './pages/Admin'
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
          <Route path="/archive"         element={<ProtectedRoute><Archive /></ProtectedRoute>} />
          <Route path="/charts"          element={<ProtectedRoute><Charts /></ProtectedRoute>} />
          <Route path="/admin"           element={<ProtectedRoute><Admin /></ProtectedRoute>} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <CurrencyProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/*"     element={<AppShell />} />
          </Routes>
        </CurrencyProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}
