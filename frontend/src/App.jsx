import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import { CurrencyProvider } from './context/CurrencyContext'
import { PublicModeProvider } from './context/PublicModeContext'
import ProtectedRoute from './components/ProtectedRoute'
import AdminRoute from './components/AdminRoute'
import Navbar from './components/Navbar'
import Login from './pages/Login'
import Signup from './pages/Signup'
import CardLedger from './pages/CardLedger'
import CardInspect from './pages/CardInspect'
import Portfolio from './pages/Portfolio'
import MasterDB from './pages/MasterDB'
import NHLStats from './pages/NHLStats'
import Archive from './pages/Archive'
import Charts from './pages/Charts'
import Admin from './pages/Admin'
import Catalog from './pages/Catalog'
import Collection from './pages/Collection'
import Settings from './pages/Settings'
import Releases from './pages/Releases'
import Search from './pages/Search'
import CardSalesPage from './pages/CardSalesPage'
import SetBrowser from './pages/SetBrowser'
import SetDetail from './pages/SetDetail'
import Trending from './pages/Trending'
import ScanPage from './pages/ScanPage'
import { PreferencesProvider } from './context/PreferencesContext'
import styles from './App.module.css'

// Preserves :cardName param when redirecting /ledger/:cardName → /my-cards/:cardName
function RedirectLedgerDetail() {
  const { cardName } = useParams()
  return <Navigate to={`/my-cards/${cardName}`} replace />
}

function AppShell() {
  return (
    <div className={styles.layout}>
      <Navbar />
      <main className={styles.main}>
        <Routes>
          {/* Default: public catalog homepage */}
          <Route path="/" element={<Navigate to="/catalog" replace />} />

          {/* Public pages */}
          <Route path="/search"         element={<Search />} />
          <Route path="/catalog"        element={<Catalog />} />
          <Route path="/catalog/:id"    element={<CardSalesPage />} />
          <Route path="/releases"       element={<Releases />} />
          <Route path="/sets"           element={<SetBrowser />} />
          <Route path="/sets/detail"    element={<SetDetail />} />
          <Route path="/trending"       element={<Trending />} />

          {/* My Cards (previously: Ledger + Collection) */}
          <Route path="/my-cards"            element={<ProtectedRoute><CardLedger /></ProtectedRoute>} />
          <Route path="/my-cards/archive"    element={<ProtectedRoute><Archive /></ProtectedRoute>} />
          <Route path="/my-cards/collection" element={<ProtectedRoute><Collection /></ProtectedRoute>} />
          <Route path="/my-cards/:cardName"  element={<ProtectedRoute><CardInspect /></ProtectedRoute>} />

          {/* Young Guns (previously: Master DB) */}
          <Route path="/young-guns"     element={<ProtectedRoute><MasterDB /></ProtectedRoute>} />
          <Route path="/nhl-stats"      element={<ProtectedRoute><NHLStats /></ProtectedRoute>} />

          {/* Scan */}
          <Route path="/scan"           element={<ProtectedRoute><ScanPage /></ProtectedRoute>} />

          {/* Portfolio */}
          <Route path="/portfolio"      element={<ProtectedRoute><Portfolio /></ProtectedRoute>} />
          <Route path="/charts"         element={<ProtectedRoute><Charts /></ProtectedRoute>} />

          {/* Admin + Settings */}
          <Route path="/settings"       element={<ProtectedRoute><Settings /></ProtectedRoute>} />
          <Route path="/admin"          element={<AdminRoute><Admin /></AdminRoute>} />

          {/* Legacy redirects — keep old URLs alive */}
          <Route path="/ledger"          element={<Navigate to="/my-cards" replace />} />
          <Route path="/ledger/:cardName" element={<RedirectLedgerDetail />} />
          <Route path="/archive"         element={<Navigate to="/my-cards/archive" replace />} />
          <Route path="/collection"      element={<Navigate to="/my-cards/collection" replace />} />
          <Route path="/master-db"       element={<Navigate to="/young-guns" replace />} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <PreferencesProvider>
        <CurrencyProvider>
          <PublicModeProvider>
            <Routes>
              <Route path="/login"  element={<Login />} />
              <Route path="/signup" element={<Signup />} />
              <Route path="/*"      element={<AppShell />} />
            </Routes>
          </PublicModeProvider>
        </CurrencyProvider>
        </PreferencesProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}
