import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AgentsPage from '../pages/AgentsPage'

// ── Mocks ──────────────────────────────────────────────────────────────

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(),
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.status = status
    }
  },
}))

vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: '1', username: 'admin', role: 'admin' as const },
    loading: false,
    error: null,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}))

// ── Fixtures ───────────────────────────────────────────────────────────

const mockAgents = [
  {
    id: 1,
    name: 'agent-01',
    hostname: 'server-01.example.com',
    last_seen: '2026-07-05T12:00:00Z',
    active: true,
    created_at: '2026-07-01T00:00:00Z',
  },
  {
    id: 2,
    name: 'agent-02',
    hostname: 'server-02.example.com',
    last_seen: null,
    active: false,
    created_at: '2026-07-02T00:00:00Z',
  },
]

const mockAgentsResponse = { agents: mockAgents, total: 2 }
const mockEmptyResponse = { agents: [], total: 0 }

// ── Helpers ────────────────────────────────────────────────────────────

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      {ui}
    </QueryClientProvider>,
  )
}

// ── Tests ──────────────────────────────────────────────────────────────

describe('AgentsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renderiza tabla con agents desde la API', async () => {
    const { apiFetch } = await import('@/lib/api')
    vi.mocked(apiFetch).mockResolvedValue(mockAgentsResponse)

    renderWithProviders(<AgentsPage />)

    await waitFor(() => {
      expect(screen.getByText('agent-01')).toBeInTheDocument()
    })
    expect(screen.getByText('agent-02')).toBeInTheDocument()
    expect(screen.getByText('server-01.example.com')).toBeInTheDocument()
    expect(screen.getByText('server-02.example.com')).toBeInTheDocument()
  })

  it('muestra estado vacío cuando no hay agents', async () => {
    const { apiFetch } = await import('@/lib/api')
    vi.mocked(apiFetch).mockResolvedValue(mockEmptyResponse)

    renderWithProviders(<AgentsPage />)

    await waitFor(() => {
      expect(screen.getByText(/no se encontraron/i)).toBeInTheDocument()
    })
  })

  it('abre el dialog de creación al hacer click en Crear Agente', async () => {
    const { apiFetch } = await import('@/lib/api')
    vi.mocked(apiFetch).mockResolvedValue(mockAgentsResponse)
    const user = userEvent.setup()

    renderWithProviders(<AgentsPage />)

    await waitFor(() => {
      expect(screen.getByText('agent-01')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /crear agente/i }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('renderiza skeleton loading mientras carga', async () => {
    const { apiFetch } = await import('@/lib/api')
    // Never resolve — keep loading
    vi.mocked(apiFetch).mockImplementation(() => new Promise(() => {}))

    renderWithProviders(<AgentsPage />)

    expect(screen.getByTestId('skeleton-loader')).toBeInTheDocument()
  })

  it('renderiza active/inactive badge según estado', async () => {
    const { apiFetch } = await import('@/lib/api')
    vi.mocked(apiFetch).mockResolvedValue(mockAgentsResponse)

    renderWithProviders(<AgentsPage />)

    await waitFor(() => {
      expect(screen.getByText('Activo')).toBeInTheDocument()
    })
    expect(screen.getByText('Inactivo')).toBeInTheDocument()
  })
})
