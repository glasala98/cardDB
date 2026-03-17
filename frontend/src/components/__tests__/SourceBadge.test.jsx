import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import SourceBadge from '../SourceBadge'

describe('SourceBadge', () => {
  it('renders eBay label for ebay source', () => {
    render(<SourceBadge source="ebay" />)
    expect(screen.getByText('eBay')).toBeInTheDocument()
  })

  it('renders Goldin label for goldin source', () => {
    render(<SourceBadge source="goldin" />)
    expect(screen.getByText('Goldin')).toBeInTheDocument()
  })

  it('renders Heritage label', () => {
    render(<SourceBadge source="heritage" />)
    expect(screen.getByText('Heritage')).toBeInTheDocument()
  })

  it('renders PWCC label', () => {
    render(<SourceBadge source="pwcc" />)
    expect(screen.getByText('PWCC')).toBeInTheDocument()
  })

  it('renders Fanatics label', () => {
    render(<SourceBadge source="fanatics" />)
    expect(screen.getByText('Fanatics')).toBeInTheDocument()
  })

  it('renders Pristine label', () => {
    render(<SourceBadge source="pristine" />)
    expect(screen.getByText('Pristine')).toBeInTheDocument()
  })

  it('renders MySlabs label', () => {
    render(<SourceBadge source="myslabs" />)
    expect(screen.getByText('MySlabs')).toBeInTheDocument()
  })

  it('is case-insensitive for source key', () => {
    render(<SourceBadge source="EBAY" />)
    expect(screen.getByText('eBay')).toBeInTheDocument()
  })

  it('renders unknown source as-is', () => {
    render(<SourceBadge source="newsite" />)
    expect(screen.getByText('newsite')).toBeInTheDocument()
  })

  it('renders ? when source is undefined', () => {
    render(<SourceBadge />)
    expect(screen.getByText('?')).toBeInTheDocument()
  })

  it('applies sm size class by default', () => {
    const { container } = render(<SourceBadge source="ebay" />)
    const span = container.querySelector('span')
    // className should contain 'sm'
    expect(span.className).toMatch(/sm/)
  })

  it('applies md size class when size=md', () => {
    const { container } = render(<SourceBadge source="ebay" size="md" />)
    const span = container.querySelector('span')
    expect(span.className).toMatch(/md/)
  })

  it('applies lg size class when size=lg', () => {
    const { container } = render(<SourceBadge source="ebay" size="lg" />)
    const span = container.querySelector('span')
    expect(span.className).toMatch(/lg/)
  })

  it('renders as a span element', () => {
    render(<SourceBadge source="goldin" />)
    const el = screen.getByText('Goldin')
    expect(el.tagName).toBe('SPAN')
  })
})
