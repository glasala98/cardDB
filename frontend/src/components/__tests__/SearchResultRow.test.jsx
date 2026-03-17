import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import SearchResultRow from '../SearchResultRow'

const baseSale = {
  id: 1,
  title: 'Connor McDavid 2015-16 UD Young Guns #201',
  price_val: 150.00,
  sold_date: '2024-03-15',
  source: 'ebay',
  grade: null,
  serial_number: null,
  print_run: null,
  lot_url: null,
  image_url: null,
  hammer_price: null,
  buyer_premium_pct: null,
  player_name: 'Connor McDavid',
  year: '2015-16',
  set_name: 'Upper Deck',
  is_rookie: false,
}

describe('SearchResultRow', () => {
  it('renders the sale title', () => {
    render(<SearchResultRow sale={baseSale} />)
    expect(screen.getByText(/Connor McDavid.*Young Guns/)).toBeInTheDocument()
  })

  it('renders the formatted price', () => {
    render(<SearchResultRow sale={baseSale} />)
    expect(screen.getByText('$150')).toBeInTheDocument()
  })

  it('renders source badge', () => {
    render(<SearchResultRow sale={baseSale} />)
    expect(screen.getByText('eBay')).toBeInTheDocument()
  })

  it('renders formatted sold date', () => {
    render(<SearchResultRow sale={baseSale} />)
    // Date formatting is locale-dependent in jsdom; just check year is present
    expect(screen.getByText(/2024/)).toBeInTheDocument()
  })

  it('renders grade badge when grade is present', () => {
    render(<SearchResultRow sale={{ ...baseSale, grade: 'PSA 10' }} />)
    expect(screen.getByText('PSA 10')).toBeInTheDocument()
  })

  it('does not render grade badge when grade is null', () => {
    render(<SearchResultRow sale={baseSale} />)
    expect(screen.queryByText(/PSA|BGS|SGC/)).toBeNull()
  })

  it('renders serial/print run when present', () => {
    render(<SearchResultRow sale={{ ...baseSale, serial_number: 7, print_run: 25 }} />)
    expect(screen.getByText('#7/25')).toBeInTheDocument()
  })

  it('does not render serial when absent', () => {
    render(<SearchResultRow sale={baseSale} />)
    expect(screen.queryByText(/#\d+\/\d+/)).toBeNull()
  })

  it('renders hammer price when present', () => {
    render(<SearchResultRow sale={{
      ...baseSale,
      hammer_price: 125.0,
      buyer_premium_pct: 20,
    }} />)
    expect(screen.getByText(/hammer/i)).toBeInTheDocument()
    expect(screen.getByText(/\$125/)).toBeInTheDocument()
  })

  it('renders thumbnail when image_url is provided', () => {
    const { container } = render(<SearchResultRow sale={{ ...baseSale, image_url: 'https://img.example.com/1.jpg' }} />)
    const img = container.querySelector('img')
    expect(img).not.toBeNull()
    expect(img.src).toContain('img.example.com')
  })

  it('does not render img element when image_url is null', () => {
    render(<SearchResultRow sale={baseSale} />)
    expect(screen.queryByRole('img')).toBeNull()
  })

  it('calls onClick when clicked', () => {
    const handler = vi.fn()
    render(<SearchResultRow sale={baseSale} onClick={handler} />)
    fireEvent.click(screen.getByText(/Connor McDavid/))
    expect(handler).toHaveBeenCalledOnce()
  })

  it('applies pointer cursor when onClick is provided', () => {
    const { container } = render(<SearchResultRow sale={baseSale} onClick={() => {}} />)
    const row = container.firstChild
    expect(row.style.cursor).toBe('pointer')
  })

  it('renders dash for null price', () => {
    render(<SearchResultRow sale={{ ...baseSale, price_val: null }} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
