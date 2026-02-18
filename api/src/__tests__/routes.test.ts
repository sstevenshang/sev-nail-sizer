/**
 * Comprehensive API route tests.
 *
 * Strategy: mock the DB layer and CV client at the module level so we can
 * test route logic (validation, error handling, response shape) in isolation.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { Hono } from 'hono'

// ─── Shared mock state ─────────────────────────────────────────────────────────

const mockDb = {
  select: vi.fn(),
  insert: vi.fn(),
  update: vi.fn(),
  delete: vi.fn(),
}

// Helper to make chainable query builder mocks
function chainable(finalValue: unknown) {
  const chain: Record<string, any> = {}
  const handler = {
    get(_target: any, prop: string) {
      if (prop === 'then') {
        // Make it thenable — resolve to finalValue
        return (resolve: (v: any) => void) => resolve(finalValue)
      }
      return (..._args: any[]) => new Proxy({}, handler)
    },
  }
  return new Proxy({}, handler)
}

// ─── Mock modules ──────────────────────────────────────────────────────────────

vi.mock('../db/index.js', () => ({
  db: new Proxy(
    {},
    {
      get(_target, prop) {
        if (prop === 'select' || prop === 'insert' || prop === 'update' || prop === 'delete') {
          return (...args: any[]) => {
            const fn = (mockDb as any)[prop]
            if (fn && fn.mockImplementation) {
              return fn(...args)
            }
            return chainable([])
          }
        }
        return undefined
      },
    }
  ),
  pool: { end: vi.fn() },
}))

vi.mock('../lib/cv-client.js', async (importOriginal) => {
  const original = (await importOriginal()) as any
  return {
    ...original,
    cvMeasure: vi.fn(),
    cvValidate: vi.fn(),
  }
})

vi.mock('../middleware/rate-limit.js', () => ({
  createRateLimiter: () => async (_c: any, next: any) => next(),
}))

vi.mock('bcrypt', () => ({
  default: {
    compare: vi.fn(),
    hash: vi.fn(),
  },
}))

// ─── Imports (after mocks) ─────────────────────────────────────────────────────

import { cvMeasure, cvValidate, CVServiceError } from '../lib/cv-client.js'
import bcrypt from 'bcrypt'

// ═══════════════════════════════════════════════════════════════════════════════
// VALIDATE ROUTE
// ═══════════════════════════════════════════════════════════════════════════════

describe('POST /v1/validate', () => {
  let app: Hono

  beforeEach(async () => {
    vi.clearAllMocks()
    const mod = await import('../routes/validate.js')
    app = new Hono()
    app.route('/v1/validate', mod.default)
  })

  it('returns 400 for missing image field', async () => {
    const form = new FormData()
    const res = await app.request('/v1/validate', { method: 'POST', body: form })
    expect(res.status).toBe(400)
    const json = await res.json()
    expect(json.error).toBe('validation_error')
  })

  it('returns 400 for oversized image', async () => {
    const form = new FormData()
    const bigBlob = new Blob([new Uint8Array(11 * 1024 * 1024)], { type: 'image/jpeg' })
    form.append('image', bigBlob, 'big.jpg')
    const res = await app.request('/v1/validate', { method: 'POST', body: form })
    expect(res.status).toBe(400)
    expect((await res.json()).message).toMatch(/10MB/)
  })

  it('returns 400 for invalid content type', async () => {
    const form = new FormData()
    form.append('image', new Blob(['hello'], { type: 'text/plain' }), 'test.txt')
    const res = await app.request('/v1/validate', { method: 'POST', body: form })
    expect(res.status).toBe(400)
    expect((await res.json()).message).toMatch(/JPEG or PNG/)
  })

  it('proxies successful CV result', async () => {
    const mockResult = {
      valid: true,
      checks: {
        card_detected: true,
        hand_detected: true,
        image_quality: 'good',
        blur_score: 500,
        brightness: 'normal',
      },
      guidance: null,
    }
    vi.mocked(cvValidate).mockResolvedValue(mockResult)

    const form = new FormData()
    form.append('image', new Blob([new Uint8Array(100)], { type: 'image/jpeg' }), 'test.jpg')
    const res = await app.request('/v1/validate', { method: 'POST', body: form })
    expect(res.status).toBe(200)
    expect(await res.json()).toEqual(mockResult)
  })

  it('returns CV service error status', async () => {
    vi.mocked(cvValidate).mockRejectedValue(
      new CVServiceError(503, 'cv_unavailable', 'CV service is unavailable')
    )

    const form = new FormData()
    form.append('image', new Blob([new Uint8Array(100)], { type: 'image/jpeg' }), 'test.jpg')
    const res = await app.request('/v1/validate', { method: 'POST', body: form })
    expect(res.status).toBe(503)
    expect((await res.json()).error).toBe('cv_unavailable')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// MEASURE ROUTE
// ═══════════════════════════════════════════════════════════════════════════════

describe('POST /v1/measure', () => {
  let app: Hono

  beforeEach(async () => {
    vi.clearAllMocks()
    const mod = await import('../routes/measure.js')
    app = new Hono()
    app.route('/v1/measure', mod.default)
  })

  it('returns 400 for missing image', async () => {
    const form = new FormData()
    const res = await app.request('/v1/measure', { method: 'POST', body: form })
    expect(res.status).toBe(400)
  })

  it('returns 400 for invalid hand value', async () => {
    const form = new FormData()
    form.append('image', new Blob([new Uint8Array(100)], { type: 'image/jpeg' }), 'test.jpg')
    form.append('hand', 'both')
    const res = await app.request('/v1/measure', { method: 'POST', body: form })
    expect(res.status).toBe(400)
    expect((await res.json()).message).toMatch(/left.*right/)
  })

  it('returns 400 for non-image content type', async () => {
    const form = new FormData()
    form.append('image', new Blob(['hello'], { type: 'application/pdf' }), 'test.pdf')
    const res = await app.request('/v1/measure', { method: 'POST', body: form })
    expect(res.status).toBe(400)
  })

  it('forwards CV errors properly', async () => {
    vi.mocked(cvMeasure).mockRejectedValue(
      new CVServiceError(400, 'card_not_detected', 'No card found')
    )

    const form = new FormData()
    form.append('image', new Blob([new Uint8Array(100)], { type: 'image/jpeg' }), 'test.jpg')
    const res = await app.request('/v1/measure', { method: 'POST', body: form })
    expect(res.status).toBe(400)
    expect((await res.json()).error).toBe('card_not_detected')
  })

  it('returns measurement result on success', async () => {
    const cvResult = {
      hand: 'right' as const,
      scale_px_per_mm: 6.3,
      fingers: {
        thumb: { width_mm: 12, length_mm: 14, curve_adj_width_mm: 13.2, confidence: 0.9 },
        index: { width_mm: 11, length_mm: 13, curve_adj_width_mm: 12.1, confidence: 0.88 },
        middle: { width_mm: 11.5, length_mm: 13.5, curve_adj_width_mm: 12.6, confidence: 0.91 },
        ring: { width_mm: 10.5, length_mm: 12, curve_adj_width_mm: 11.6, confidence: 0.85 },
        pinky: { width_mm: 9, length_mm: 10, curve_adj_width_mm: 9.9, confidence: 0.82 },
      },
      overall_confidence: 0.87,
      warnings: [],
    }
    vi.mocked(cvMeasure).mockResolvedValue(cvResult)

    // Mock db.insert to return chainable
    mockDb.insert.mockReturnValue(chainable([]))

    const form = new FormData()
    form.append('image', new Blob([new Uint8Array(100)], { type: 'image/jpeg' }), 'test.jpg')
    const res = await app.request('/v1/measure', { method: 'POST', body: form })
    expect(res.status).toBe(200)

    const json = await res.json()
    expect(json.id).toMatch(/^msr_/)
    expect(json.hand).toBe('right')
    expect(json.fingers).toBeDefined()
    expect(json.overall_confidence).toBe(0.87)
  })
})

describe('GET /v1/measure/:id', () => {
  let app: Hono

  beforeEach(async () => {
    vi.clearAllMocks()
    const mod = await import('../routes/measure.js')
    app = new Hono()
    app.route('/v1/measure', mod.default)
  })

  it('returns 404 for non-existent measurement', async () => {
    mockDb.select.mockReturnValue(chainable([]))
    const res = await app.request('/v1/measure/msr_nonexistent', { method: 'GET' })
    expect(res.status).toBe(404)
  })
})

describe('GET /v1/measure/history', () => {
  let app: Hono

  beforeEach(async () => {
    vi.clearAllMocks()
    const mod = await import('../routes/measure.js')
    app = new Hono()
    app.route('/v1/measure', mod.default)
  })

  it('returns 400 without customer_id', async () => {
    const res = await app.request('/v1/measure/history', { method: 'GET' })
    expect(res.status).toBe(400)
  })

  it('returns empty measurements for unknown customer', async () => {
    mockDb.select.mockReturnValue(chainable([]))
    const res = await app.request('/v1/measure/history?customer_id=cust_123', { method: 'GET' })
    expect(res.status).toBe(200)
    const json = await res.json()
    expect(json.measurements).toEqual([])
    expect(json.active_id).toBeNull()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// RECOMMEND ROUTE
// ═══════════════════════════════════════════════════════════════════════════════

describe('POST /v1/recommend', () => {
  let app: Hono

  beforeEach(async () => {
    vi.clearAllMocks()
    const mod = await import('../routes/recommend.js')
    app = new Hono()
    app.route('/v1/recommend', mod.default)
  })

  it('returns 400 for missing body', async () => {
    const res = await app.request('/v1/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    expect(res.status).toBe(400)
  })

  it('returns 400 for non-JSON body', async () => {
    const res = await app.request('/v1/recommend', {
      method: 'POST',
      body: 'not json',
    })
    expect(res.status).toBe(400)
  })

  it('returns 404 when measurement not found', async () => {
    mockDb.select.mockReturnValue(chainable([]))
    const res = await app.request('/v1/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ measurement_id: 'msr_nonexistent' }),
    })
    expect(res.status).toBe(404)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// ADMIN AUTH ROUTES
// ═══════════════════════════════════════════════════════════════════════════════

describe('POST /v1/admin/auth/login', () => {
  let app: Hono

  beforeEach(async () => {
    vi.clearAllMocks()
    const mod = await import('../routes/admin.js')
    app = new Hono()
    app.route('/v1/admin', mod.default)
  })

  it('returns 400 for missing credentials', async () => {
    const res = await app.request('/v1/admin/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    expect(res.status).toBe(400)
  })

  it('returns 401 for unknown email', async () => {
    mockDb.select.mockReturnValue(chainable([]))
    const res = await app.request('/v1/admin/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'bad@test.com', password: 'wrong' }),
    })
    expect(res.status).toBe(401)
  })

  it('returns 401 for wrong password', async () => {
    mockDb.select.mockReturnValue(
      chainable([{ id: 1, email: 'admin@test.com', passwordHash: '$2b$10$fakehash' }])
    )
    vi.mocked(bcrypt.compare).mockResolvedValue(false as never)

    const res = await app.request('/v1/admin/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'admin@test.com', password: 'wrong' }),
    })
    expect(res.status).toBe(401)
  })

  it('returns tokens on successful login', async () => {
    mockDb.select.mockReturnValue(
      chainable([{ id: 1, email: 'admin@test.com', passwordHash: '$2b$10$fakehash' }])
    )
    vi.mocked(bcrypt.compare).mockResolvedValue(true as never)
    mockDb.update.mockReturnValue(chainable([]))

    const res = await app.request('/v1/admin/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'admin@test.com', password: 'correct' }),
    })
    expect(res.status).toBe(200)
    const json = await res.json()
    expect(json.access_token).toBeDefined()
    expect(json.refresh_token).toBeDefined()
    expect(json.expires_in).toBe(86400)
  })
})

describe('POST /v1/admin/auth/refresh', () => {
  let app: Hono

  beforeEach(async () => {
    vi.clearAllMocks()
    const mod = await import('../routes/admin.js')
    app = new Hono()
    app.route('/v1/admin', mod.default)
  })

  it('returns 400 for missing refresh_token', async () => {
    const res = await app.request('/v1/admin/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    expect(res.status).toBe(400)
  })

  it('returns 401 for invalid refresh token', async () => {
    const res = await app.request('/v1/admin/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: 'invalid.token.here' }),
    })
    expect(res.status).toBe(401)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// ADMIN PROTECTED ROUTES (auth required)
// ═══════════════════════════════════════════════════════════════════════════════

describe('Admin protected routes', () => {
  let app: Hono
  let token: string

  beforeEach(async () => {
    vi.clearAllMocks()

    // Generate a valid admin JWT
    const { signAccessToken } = await import('../middleware/auth.js')
    token = signAccessToken({ id: 1, email: 'admin@test.com' })

    const mod = await import('../routes/admin.js')
    app = new Hono()
    app.route('/v1/admin', mod.default)
  })

  it('returns 401 without Authorization header', async () => {
    const res = await app.request('/v1/admin/sizes', { method: 'GET' })
    expect(res.status).toBe(401)
  })

  it('returns 401 with invalid token', async () => {
    const res = await app.request('/v1/admin/sizes', {
      method: 'GET',
      headers: { Authorization: 'Bearer invalid.token' },
    })
    expect(res.status).toBe(401)
  })

  // ── Sizes ──────────────────────────────────────────────────────────────────

  describe('GET /v1/admin/sizes', () => {
    it('returns sizes list', async () => {
      mockDb.select.mockReturnValue(chainable([]))
      const res = await app.request('/v1/admin/sizes', {
        method: 'GET',
        headers: { Authorization: `Bearer ${token}` },
      })
      expect(res.status).toBe(200)
      const json = await res.json()
      expect(json.sizes).toEqual([])
      expect(json.chart_id).toBe('default')
    })
  })

  describe('POST /v1/admin/sizes', () => {
    it('returns 400 for missing required fields', async () => {
      const res = await app.request('/v1/admin/sizes', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ label: 'test' }),
      })
      expect(res.status).toBe(400)
    })

    it('creates a size on valid input', async () => {
      const mockRow = { id: 1, chartId: 'default', sizeNumber: 5, widthMm: 14.5 }
      mockDb.insert.mockReturnValue(chainable([mockRow]))

      const res = await app.request('/v1/admin/sizes', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ size_number: 5, width_mm: 14.5 }),
      })
      expect(res.status).toBe(201)
    })
  })

  // ── Rules ──────────────────────────────────────────────────────────────────

  describe('GET /v1/admin/rules', () => {
    it('returns rules and config', async () => {
      mockDb.select.mockReturnValue(chainable([]))
      const res = await app.request('/v1/admin/rules', {
        method: 'GET',
        headers: { Authorization: `Bearer ${token}` },
      })
      expect(res.status).toBe(200)
      const json = await res.json()
      expect(json.rules).toBeDefined()
      expect(json.config).toBeDefined()
    })
  })

  describe('POST /v1/admin/rules', () => {
    it('returns 400 for missing required fields', async () => {
      const res = await app.request('/v1/admin/rules', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ min_width_mm: 10 }),
      })
      expect(res.status).toBe(400)
    })

    it('returns 400 when min >= max', async () => {
      const res = await app.request('/v1/admin/rules', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ min_width_mm: 15, max_width_mm: 10, mapped_size: 5 }),
      })
      expect(res.status).toBe(400)
    })

    it('returns 400 for invalid finger name', async () => {
      const res = await app.request('/v1/admin/rules', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ min_width_mm: 10, max_width_mm: 15, mapped_size: 5, finger: 'toe' }),
      })
      expect(res.status).toBe(400)
    })
  })

  describe('PUT /v1/admin/rules/config', () => {
    it('returns 400 for invalid between_sizes', async () => {
      const res = await app.request('/v1/admin/rules/config', {
        method: 'PUT',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ between_sizes: 'invalid' }),
      })
      expect(res.status).toBe(400)
    })
  })

  // ── Sets ───────────────────────────────────────────────────────────────────

  describe('POST /v1/admin/sets', () => {
    it('returns 400 for missing fields', async () => {
      const res = await app.request('/v1/admin/sets', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ name: 'Test Set' }),
      })
      expect(res.status).toBe(400)
    })
  })

  // ── Rules preview ──────────────────────────────────────────────────────────

  describe('POST /v1/admin/rules/preview', () => {
    it('returns 400 for missing finger measurements', async () => {
      const res = await app.request('/v1/admin/rules/preview', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ measurements: { thumb: 12 } }),
      })
      expect(res.status).toBe(400)
      expect((await res.json()).message).toMatch(/Missing measurements/)
    })
  })

  // ── CSV import/export ──────────────────────────────────────────────────────

  describe('POST /v1/admin/sizes/import', () => {
    it('returns 400 for wrong content type', async () => {
      const res = await app.request('/v1/admin/sizes/import', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: '{}',
      })
      expect(res.status).toBe(400)
      expect((await res.json()).message).toMatch(/text\/csv/)
    })
  })

  // ── Measurements admin ────────────────────────────────────────────────────

  describe('GET /v1/admin/measurements/stats', () => {
    it('returns stats object', async () => {
      mockDb.select.mockReturnValue(chainable([{ count: 0, avg: null }]))
      const res = await app.request('/v1/admin/measurements/stats', {
        method: 'GET',
        headers: { Authorization: `Bearer ${token}` },
      })
      expect(res.status).toBe(200)
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// INDEX APP (health, 404, error handler)
// ═══════════════════════════════════════════════════════════════════════════════

describe('App-level routes', () => {
  let app: Hono

  beforeEach(async () => {
    // Import the app (it exports default)
    const mod = await import('../index.js')
    app = mod.default
  })

  it('GET /health returns ok', async () => {
    const res = await app.request('/health')
    expect(res.status).toBe(200)
    const json = await res.json()
    expect(json.status).toBe('ok')
  })

  it('GET /nonexistent returns 404', async () => {
    const res = await app.request('/nonexistent')
    expect(res.status).toBe(404)
    const json = await res.json()
    expect(json.error).toBe('not_found')
  })
})
