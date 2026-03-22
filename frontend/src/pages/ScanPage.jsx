import { useNavigate } from 'react-router-dom'
import ScanCardModal from '../components/ScanCardModal'

// Renders the scan modal as a full page (no backdrop click to dismiss)
export default function ScanPage() {
  const navigate = useNavigate()
  return (
    <ScanCardModal
      onClose={() => navigate('/my-cards')}
      onAdded={() => navigate('/my-cards')}
    />
  )
}
