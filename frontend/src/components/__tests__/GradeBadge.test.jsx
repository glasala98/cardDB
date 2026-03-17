import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import GradeBadge from '../GradeBadge'

describe('GradeBadge', () => {
  it('renders nothing when grade is null', () => {
    const { container } = render(<GradeBadge grade={null} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing when grade is undefined', () => {
    const { container } = render(<GradeBadge />)
    expect(container.firstChild).toBeNull()
  })

  it('renders the grade text', () => {
    render(<GradeBadge grade="PSA 10" />)
    expect(screen.getByText('PSA 10')).toBeInTheDocument()
  })

  it('renders BGS grades', () => {
    render(<GradeBadge grade="BGS 9.5" />)
    expect(screen.getByText('BGS 9.5')).toBeInTheDocument()
  })

  it('renders SGC grades', () => {
    render(<GradeBadge grade="SGC 10" />)
    expect(screen.getByText('SGC 10')).toBeInTheDocument()
  })

  it('renders unknown grade with fallback grey color', () => {
    render(<GradeBadge grade="HGA 8" />)
    const el = screen.getByText('HGA 8')
    expect(el).toBeInTheDocument()
    // fallback bg is #555
    expect(el.style.backgroundColor).toBe('rgb(85, 85, 85)')
  })

  it('applies PSA 10 red background', () => {
    render(<GradeBadge grade="PSA 10" />)
    const el = screen.getByText('PSA 10')
    // PSA 10: #c8102e
    expect(el.style.backgroundColor).toBe('rgb(200, 16, 46)')
  })

  it('applies BGS 10 blue background', () => {
    render(<GradeBadge grade="BGS 10" />)
    const el = screen.getByText('BGS 10')
    // BGS 10: #003087
    expect(el.style.backgroundColor).toBe('rgb(0, 48, 135)')
  })

  it('applies white text color', () => {
    render(<GradeBadge grade="PSA 10" />)
    const el = screen.getByText('PSA 10')
    expect(el.style.color).toBe('rgb(255, 255, 255)')
  })

  it('renders as a span element', () => {
    render(<GradeBadge grade="PSA 9" />)
    const el = screen.getByText('PSA 9')
    expect(el.tagName).toBe('SPAN')
  })
})
