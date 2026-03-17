import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import SaleDetailModal from '../SaleDetailModal'

// Mock the API client
vi.mock('../../api/client', () => ({
  default: {
    get: vi.fn().mockResolvedValue([]),
  },
}))

const baseSale = {
  id: 1,
  card_catalog_id: 42,
  title: 'Connor McDavid 2015-16 UD Young Guns #201',
  price_val: 150.00,
  sold_date: '2024-03-15',
  source: 'ebay',
  grade: null,
  grade_company: null,
  serial_number: null,
  print_run: null,
  lot_url: 'https://ebay.com/item/1',
  image_url: null,
  hammer_price: null,
  buyer_premium_pct: null,
  player_name: 'Connor McDavid',
  year: '2015-16',
  set_name: 'Upper Deck',
  variant: 'Young Guns',
  sport: 'NHL',
  is_rookie: false,
}

describe('SaleDetailModal', () => {
  it('renders nothing when sale is null', () => {
    const { container } = render(<SaleDetailModal sale={null} onClose={() => {}} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders player name', () => {
    render(<SaleDetailModal sale={baseSale} onClose={() => {}} />)
    expect(screen.getByText('Connor McDavid')).toBeInTheDocument()
  })

  it('renders sale price', () => {
    render(<SaleDetailModal sale={baseSale} onClose={() => {}} />)
    expect(screen.getByText('$150')).toBeInTheDocument()
  })

  it('renders source badge', () => {
    render(<SaleDetailModal sale={baseSale} onClose={() => {}} />)
    expect(screen.getByText('eBay')).toBeInTheDocument()
  })

  it('renders card meta (year + set)', () => {
    render(<SaleDetailModal sale={baseSale} onClose={() => {}} />)
    expect(screen.getByText(/2015-16 Upper Deck/)).toBeInTheDocument()
  })

  it('renders listing title in quotes', () => {
    render(<SaleDetailModal sale={baseSale} onClose={() => {}} />)
    expect(screen.getByText(/"Connor McDavid 2015-16 UD Young Guns #201"/)).toBeInTheDocument()
  })

  it('renders view original listing link', () => {
    render(<SaleDetailModal sale={baseSale} onClose={() => {}} />)
    const link = screen.getByText(/View original listing/)
    expect(link).toBeInTheDocument()
    expect(link.href).toContain('ebay.com')
  })

  it('calls onClose when × button is clicked', () => {
    const onClose = vi.fn()
    render(<SaleDetailModal sale={baseSale} onClose={onClose} />)
    fireEvent.click(screen.getByText('×'))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('calls onClose on Escape key', () => {
    const onClose = vi.fn()
    render(<SaleDetailModal sale={baseSale} onClose={onClose} />)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('renders grade badge when grade present', () => {
    render(<SaleDetailModal sale={{ ...baseSale, grade: 'PSA 10' }} onClose={() => {}} />)
    expect(screen.getByText('PSA 10')).toBeInTheDocument()
  })

  it('renders RC badge when is_rookie is true', () => {
    render(<SaleDetailModal sale={{ ...baseSale, is_rookie: true }} onClose={() => {}} />)
    expect(screen.getByText('RC')).toBeInTheDocument()
  })

  it('renders serial/print run when present', () => {
    render(<SaleDetailModal sale={{ ...baseSale, serial_number: 7, print_run: 25 }} onClose={() => {}} />)
    expect(screen.getByText('#7/25')).toBeInTheDocument()
  })

  it('renders hammer price section when present', () => {
    render(<SaleDetailModal sale={{
      ...baseSale,
      hammer_price: 125.0,
      buyer_premium_pct: 20,
    }} onClose={() => {}} />)
    expect(screen.getByText('$125')).toBeInTheDocument()
    expect(screen.getByText(/\+20%/)).toBeInTheDocument()
  })

  it('renders history loading state initially', async () => {
    render(<SaleDetailModal sale={baseSale} onClose={() => {}} />)
    // "…" spinner should appear while history loads
    expect(screen.getByText(/…/)).toBeInTheDocument()
  })

  it('renders no-history message when history is empty', async () => {
    render(<SaleDetailModal sale={baseSale} onClose={() => {}} />)
    await waitFor(() => {
      expect(screen.getByText(/Not enough history/)).toBeInTheDocument()
    })
  })

  it('does not crash when lot_url is null', () => {
    render(<SaleDetailModal sale={{ ...baseSale, lot_url: null }} onClose={() => {}} />)
    expect(screen.queryByText(/View original listing/)).toBeNull()
  })
})
