import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AlertGroupRow } from './AlertGroup'
import type { AlertGroupItem } from '@/lib/types'

const mockGroup: AlertGroupItem = {
  group_key: 'test-rule:192.168.1.1',
  group_name: 'Brute Force from 192.168.1.1',
  alert_count: 3,
  max_severity: 'high',
  risk_score: 0.75,
  alerts: [
    {
      id: 'alert-1',
      title: 'Failed login attempt',
      severity: 'high',
      status: 'open',
      event_count: 5,
      created_at: '2026-07-10T12:00:00Z',
    },
    {
      id: 'alert-2',
      title: 'Failed login attempt',
      severity: 'medium',
      status: 'open',
      event_count: 3,
      created_at: '2026-07-10T12:01:00Z',
    },
  ],
}

describe('AlertGroupRow', () => {
  it('renders group name and alert count', () => {
    render(<AlertGroupRow group={mockGroup} />)
    expect(screen.getByText('Brute Force from 192.168.1.1')).toBeInTheDocument()
    expect(screen.getByText('3 alertas')).toBeInTheDocument()
  })

  it('shows child alerts when expanded', () => {
    render(<AlertGroupRow group={mockGroup} />)

    // Child alerts should NOT be visible initially
    expect(screen.queryByText('Failed login attempt')).not.toBeInTheDocument()

    // Click to expand
    fireEvent.click(screen.getByText('Brute Force from 192.168.1.1'))

    // Now child alerts should be visible
    expect(screen.getAllByText('Failed login attempt').length).toBeGreaterThan(0)
  })

  it('hides child alerts when collapsed', () => {
    render(<AlertGroupRow group={mockGroup} />)

    // Expand
    fireEvent.click(screen.getByText('Brute Force from 192.168.1.1'))
    expect(screen.getAllByText('Failed login attempt').length).toBeGreaterThan(0)

    // Collapse
    fireEvent.click(screen.getByText('Brute Force from 192.168.1.1'))
    expect(screen.queryByText('Failed login attempt')).not.toBeInTheDocument()
  })

  it('displays risk badge', () => {
    render(<AlertGroupRow group={mockGroup} />)
    expect(screen.getByText('75%')).toBeInTheDocument()
  })

  it('displays severity badge', () => {
    render(<AlertGroupRow group={mockGroup} />)
    expect(screen.getByText('high')).toBeInTheDocument()
  })
})
