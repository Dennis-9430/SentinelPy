import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SeverityBadge } from './SeverityBadge'

describe('SeverityBadge', () => {
  it('renders severity text', () => {
    render(<SeverityBadge severity="critical" />)
    expect(screen.getByText('critical')).toBeInTheDocument()
  })

  it('renders info as fallback for unknown severity', () => {
    render(<SeverityBadge severity="unknown" />)
    expect(screen.getByText('unknown')).toBeInTheDocument()
  })
})
