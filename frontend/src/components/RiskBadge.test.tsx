import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RiskBadge } from './RiskBadge'

describe('RiskBadge', () => {
  it('renders high risk for score >= 0.6', () => {
    render(<RiskBadge score={0.75} />)
    expect(screen.getByText('75%')).toBeInTheDocument()
  })

  it('renders medium risk for score 0.3-0.6', () => {
    render(<RiskBadge score={0.45} />)
    expect(screen.getByText('45%')).toBeInTheDocument()
  })

  it('renders low risk for score < 0.3', () => {
    render(<RiskBadge score={0.1} />)
    expect(screen.getByText('10%')).toBeInTheDocument()
  })

  it('renders dash for null score', () => {
    render(<RiskBadge score={null} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('renders 0% for zero score', () => {
    render(<RiskBadge score={0} />)
    expect(screen.getByText('0%')).toBeInTheDocument()
  })

  it('renders 100% for max score', () => {
    render(<RiskBadge score={1} />)
    expect(screen.getByText('100%')).toBeInTheDocument()
  })
})
