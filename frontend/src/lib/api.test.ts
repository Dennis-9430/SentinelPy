import { describe, it, expect } from 'vitest'

describe('api client', () => {
  it('exports apiFetch as a function', async () => {
    const mod = await import('./api')
    expect(mod.apiFetch).toBeDefined()
    expect(typeof mod.apiFetch).toBe('function')
  })

  it('exports ApiError as a class', async () => {
    const mod = await import('./api')
    expect(mod.ApiError).toBeDefined()
    expect(mod.ApiError.prototype).toBeInstanceOf(Error)
  })
})
