import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Navbar from './components/Navbar'
import CardLedger from './pages/CardLedger'
import CardInspect from './pages/CardInspect'
import Portfolio from './pages/Portfolio'
import MasterDB from './pages/MasterDB'
import NHLStats from './pages/NHLStats'
import styles from './App.module.css'

export default function App() {
  return (
    <BrowserRouter>
      <div className={styles.layout}>
        <Navbar />
        <main className={styles.main}>
          <Routes>
            <Route path="/" element={<Navigate to="/ledger" replace />} />
            <Route path="/ledger" element={<CardLedger />} />
            <Route path="/ledger/:cardName" element={<CardInspect />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/master-db" element={<MasterDB />} />
            <Route path="/nhl-stats" element={<NHLStats />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
