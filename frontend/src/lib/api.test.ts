import { describe, it, expect } from 'vitest'

describe('api client', () => {
  it('exporta apiFetch como función', async () => {
    const mod = await import('./api')
    expect(mod.apiFetch).toBeDefined()
    expect(typeof mod.apiFetch).toBe('function')
  })

  it('exporta ApiError como clase', async () => {
    const mod = await import('./api')
    expect(mod.ApiError).toBeDefined()
    expect(mod.ApiError.prototype).toBeInstanceOf(Error)
  })
})
