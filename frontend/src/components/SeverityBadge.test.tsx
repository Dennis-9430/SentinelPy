import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SeverityBadge } from './SeverityBadge'

describe('SeverityBadge', () => {
  it('renderiza el texto de severidad', () => {
    render(<SeverityBadge severity="critical" />)
    expect(screen.getByText('critical')).toBeInTheDocument()
  })

  it('renderiza info como fallback para severidad desconocida', () => {
    render(<SeverityBadge severity="unknown" />)
    expect(screen.getByText('unknown')).toBeInTheDocument()
  })
})
