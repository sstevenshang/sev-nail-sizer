import { Hono } from 'hono'
import { eq, desc, gte, lte, and, count, avg, sql } from 'drizzle-orm'
import bcrypt from 'bcrypt'
import { db } from '../db/index.js'
import {
  admins,
  nailSizes,
  sizeRules,
  sizeRulesConfig,
  sizeSets,
  measurements,
  recommendations,
} from '../db/schema.js'
import {
  requireAdmin,
  signAccessToken,
  signRefreshToken,
  verifyRefreshToken,
} from '../middleware/auth.js'

// ─── Root router ──────────────────────────────────────────────────────────────
const admin = new Hono()

// ─── Auth sub-router (no auth required) ──────────────────────────────────────

const auth = new Hono()

/** POST /v1/admin/auth/login */
auth.post('/login', async (c) => {
  let body: { email?: string; password?: string }
  try {
    body = await c.req.json()
  } catch {
    return c.json({ error: 'validation_error', message: 'Request body must be JSON' }, 400)
  }

  if (!body.email || !body.password) {
    return c.json({ error: 'validation_error', message: 'email and password are required' }, 400)
  }

  const [admin_] = await db.select().from(admins).where(eq(admins.email, body.email))
  if (!admin_) {
    return c.json({ error: 'unauthorized', message: 'Invalid credentials' }, 401)
  }

  const valid = await bcrypt.compare(body.password, admin_.passwordHash)
  if (!valid) {
    return c.json({ error: 'unauthorized', message: 'Invalid credentials' }, 401)
  }

  await db.update(admins).set({ lastLoginAt: new Date() }).where(eq(admins.id, admin_.id))

  const payload = { id: admin_.id, email: admin_.email }
  return c.json({
    access_token: signAccessToken(payload),
    refresh_token: signRefreshToken(payload),
    expires_in: 86400,
  })
})

/** POST /v1/admin/auth/refresh */
auth.post('/refresh', async (c) => {
  let body: { refresh_token?: string }
  try {
    body = await c.req.json()
  } catch {
    return c.json({ error: 'validation_error', message: 'Request body must be JSON' }, 400)
  }

  if (!body.refresh_token) {
    return c.json({ error: 'validation_error', message: 'refresh_token is required' }, 400)
  }

  try {
    const payload = verifyRefreshToken(body.refresh_token)
    const newPayload = { id: payload.id, email: payload.email }
    return c.json({
      access_token: signAccessToken(newPayload),
      refresh_token: signRefreshToken(newPayload),
      expires_in: 86400,
    })
  } catch {
    return c.json({ error: 'unauthorized', message: 'Invalid or expired refresh token' }, 401)
  }
})

admin.route('/auth', auth)

// ─── Protected sub-router ─────────────────────────────────────────────────────
const protect = new Hono()
protect.use('/*', requireAdmin())

// ══ Sizes ══════════════════════════════════════════════════════════════════════

/** GET /v1/admin/sizes */
protect.get('/sizes', async (c) => {
  const chartId = c.req.query('chart_id') ?? 'default'
  const rows = await db
    .select()
    .from(nailSizes)
    .where(eq(nailSizes.chartId, chartId))
    .orderBy(nailSizes.sizeNumber)

  return c.json({ sizes: rows, chart_id: chartId })
})

/** POST /v1/admin/sizes */
protect.post('/sizes', async (c) => {
  let body: { size_number?: number; width_mm?: number; length_mm?: number; label?: string; chart_id?: string }
  try {
    body = await c.req.json()
  } catch {
    return c.json({ error: 'validation_error', message: 'Request body must be JSON' }, 400)
  }

  if (body.size_number == null || body.width_mm == null) {
    return c.json({ error: 'validation_error', message: 'size_number and width_mm are required' }, 400)
  }

  const [row] = await db
    .insert(nailSizes)
    .values({
      chartId: body.chart_id ?? 'default',
      sizeNumber: body.size_number,
      widthMm: body.width_mm,
      lengthMm: body.length_mm ?? null,
      label: body.label ?? null,
    })
    .returning()

  return c.json(row, 201)
})

/** PUT /v1/admin/sizes/:id */
protect.put('/sizes/:id', async (c) => {
  const id = Number(c.req.param('id'))
  let body: { width_mm?: number; length_mm?: number; label?: string }
  try {
    body = await c.req.json()
  } catch {
    return c.json({ error: 'validation_error', message: 'Request body must be JSON' }, 400)
  }

  const updates: Partial<typeof nailSizes.$inferInsert> = {}
  if (body.width_mm != null) updates.widthMm = body.width_mm
  if (body.length_mm != null) updates.lengthMm = body.length_mm
  if (body.label != null) updates.label = body.label
  updates.updatedAt = new Date()

  const [row] = await db.update(nailSizes).set(updates).where(eq(nailSizes.id, id)).returning()

  if (!row) return c.json({ error: 'not_found', message: 'Size not found' }, 404)
  return c.json(row)
})

/** DELETE /v1/admin/sizes/:id */
protect.delete('/sizes/:id', async (c) => {
  const id = Number(c.req.param('id'))
  const [row] = await db.delete(nailSizes).where(eq(nailSizes.id, id)).returning()
  if (!row) return c.json({ error: 'not_found', message: 'Size not found' }, 404)
  return c.json({ deleted: true })
})

/** POST /v1/admin/sizes/import — CSV import */
protect.post('/sizes/import', async (c) => {
  const contentType = c.req.header('content-type') ?? ''
  if (!contentType.includes('text/csv')) {
    return c.json({ error: 'validation_error', message: 'Content-Type must be text/csv' }, 400)
  }

  const text = await c.req.text()
  const lines = text.trim().split('\n')
  const [header, ...rows] = lines

  const cols = header.split(',').map((h) => h.trim())
  const required = ['size_number', 'width_mm']
  const missing = required.filter((r) => !cols.includes(r))
  if (missing.length > 0) {
    return c.json({ error: 'validation_error', message: `Missing columns: ${missing.join(', ')}` }, 400)
  }

  const errors: string[] = []
  let imported = 0

  for (let i = 0; i < rows.length; i++) {
    const values = rows[i].split(',').map((v) => v.trim())
    const row: Record<string, string> = {}
    cols.forEach((col, idx) => { row[col] = values[idx] ?? '' })

    const sizeNumber = parseInt(row.size_number)
    const widthMm = parseFloat(row.width_mm)

    if (isNaN(sizeNumber) || isNaN(widthMm)) {
      errors.push(`Row ${i + 2}: invalid size_number or width_mm`)
      continue
    }

    try {
      await db
        .insert(nailSizes)
        .values({
          chartId: 'default',
          sizeNumber,
          widthMm,
          lengthMm: row.length_mm ? parseFloat(row.length_mm) : null,
          label: row.label || null,
        })
        .onConflictDoUpdate({
          target: [nailSizes.chartId, nailSizes.sizeNumber],
          set: { widthMm, lengthMm: row.length_mm ? parseFloat(row.length_mm) : null, label: row.label || null, updatedAt: new Date() },
        })
      imported++
    } catch (err) {
      errors.push(`Row ${i + 2}: ${String(err)}`)
    }
  }

  return c.json({ imported, errors })
})

/** GET /v1/admin/sizes/export — CSV download */
protect.get('/sizes/export', async (c) => {
  const rows = await db
    .select()
    .from(nailSizes)
    .where(eq(nailSizes.chartId, 'default'))
    .orderBy(nailSizes.sizeNumber)

  const csv = [
    'size_number,width_mm,length_mm,label',
    ...rows.map((r) => `${r.sizeNumber},${r.widthMm},${r.lengthMm ?? ''},${r.label ?? ''}`),
  ].join('\n')

  return new Response(csv, {
    headers: {
      'Content-Type': 'text/csv',
      'Content-Disposition': 'attachment; filename="nail-sizes.csv"',
    },
  })
})

// ══ Rules ══════════════════════════════════════════════════════════════════════

/** GET /v1/admin/rules */
protect.get('/rules', async (c) => {
  const chartId = c.req.query('chart_id') ?? 'default'
  const rules = await db
    .select()
    .from(sizeRules)
    .where(eq(sizeRules.chartId, chartId))
    .orderBy(desc(sizeRules.priority), sizeRules.mappedSize)

  const [config] = await db
    .select()
    .from(sizeRulesConfig)
    .where(eq(sizeRulesConfig.chartId, chartId))

  return c.json({
    rules,
    config: config
      ? { between_sizes: config.betweenSizes, tolerance_mm: config.toleranceMm }
      : { between_sizes: 'size_down', tolerance_mm: 0.3 },
  })
})

/** POST /v1/admin/rules */
protect.post('/rules', async (c) => {
  let body: { finger?: string; min_width_mm?: number; max_width_mm?: number; mapped_size?: number; priority?: number; chart_id?: string }
  try {
    body = await c.req.json()
  } catch {
    return c.json({ error: 'validation_error', message: 'Request body must be JSON' }, 400)
  }

  if (body.min_width_mm == null || body.max_width_mm == null || body.mapped_size == null) {
    return c.json(
      { error: 'validation_error', message: 'min_width_mm, max_width_mm, and mapped_size are required' },
      400
    )
  }

  if (body.min_width_mm >= body.max_width_mm) {
    return c.json({ error: 'validation_error', message: 'min_width_mm must be less than max_width_mm' }, 400)
  }

  const validFingers = ['all', 'thumb', 'index', 'middle', 'ring', 'pinky']
  if (body.finger && !validFingers.includes(body.finger)) {
    return c.json({ error: 'validation_error', message: `finger must be one of: ${validFingers.join(', ')}` }, 400)
  }

  const [row] = await db
    .insert(sizeRules)
    .values({
      chartId: body.chart_id ?? 'default',
      finger: body.finger ?? 'all',
      minWidthMm: body.min_width_mm,
      maxWidthMm: body.max_width_mm,
      mappedSize: body.mapped_size,
      priority: body.priority ?? 0,
    })
    .returning()

  return c.json(row, 201)
})

/** PUT /v1/admin/rules/config — MUST be before /rules/:id to avoid shadowing */
protect.put('/rules/config', async (c) => {
  let body: { between_sizes?: string; tolerance_mm?: number }
  try {
    body = await c.req.json()
  } catch {
    return c.json({ error: 'validation_error', message: 'Request body must be JSON' }, 400)
  }

  if (body.between_sizes && !['size_up', 'size_down'].includes(body.between_sizes)) {
    return c.json({ error: 'validation_error', message: 'between_sizes must be "size_up" or "size_down"' }, 400)
  }

  const updates: Partial<typeof sizeRulesConfig.$inferInsert> = { updatedAt: new Date() }
  if (body.between_sizes) updates.betweenSizes = body.between_sizes
  if (body.tolerance_mm != null) updates.toleranceMm = body.tolerance_mm

  const [row] = await db
    .insert(sizeRulesConfig)
    .values({ chartId: 'default', ...updates })
    .onConflictDoUpdate({ target: sizeRulesConfig.chartId, set: updates })
    .returning()

  return c.json({ between_sizes: row.betweenSizes, tolerance_mm: row.toleranceMm })
})

/** PUT /v1/admin/rules/:id */
protect.put('/rules/:id', async (c) => {
  const id = Number(c.req.param('id'))
  let body: { finger?: string; min_width_mm?: number; max_width_mm?: number; mapped_size?: number; priority?: number }
  try {
    body = await c.req.json()
  } catch {
    return c.json({ error: 'validation_error', message: 'Request body must be JSON' }, 400)
  }

  const updates: Partial<typeof sizeRules.$inferInsert> = {}
  if (body.finger != null) updates.finger = body.finger
  if (body.min_width_mm != null) updates.minWidthMm = body.min_width_mm
  if (body.max_width_mm != null) updates.maxWidthMm = body.max_width_mm
  if (body.mapped_size != null) updates.mappedSize = body.mapped_size
  if (body.priority != null) updates.priority = body.priority

  const [row] = await db.update(sizeRules).set(updates).where(eq(sizeRules.id, id)).returning()
  if (!row) return c.json({ error: 'not_found', message: 'Rule not found' }, 404)
  return c.json(row)
})

/** DELETE /v1/admin/rules/:id */
protect.delete('/rules/:id', async (c) => {
  const id = Number(c.req.param('id'))
  const [row] = await db.delete(sizeRules).where(eq(sizeRules.id, id)).returning()
  if (!row) return c.json({ error: 'not_found', message: 'Rule not found' }, 404)
  return c.json({ deleted: true })
})

/** POST /v1/admin/rules/preview — test rules against sample measurements */
protect.post('/rules/preview', async (c) => {
  let body: { measurements?: Record<string, number> }
  try {
    body = await c.req.json()
  } catch {
    return c.json({ error: 'validation_error', message: 'Request body must be JSON' }, 400)
  }

  const required = ['thumb', 'index', 'middle', 'ring', 'pinky']
  const missing = required.filter((f) => body.measurements?.[f] == null)
  if (missing.length > 0) {
    return c.json(
      { error: 'validation_error', message: `Missing measurements for: ${missing.join(', ')}` },
      400
    )
  }

  const rules = await db
    .select()
    .from(sizeRules)
    .where(eq(sizeRules.chartId, 'default'))
    .orderBy(desc(sizeRules.priority))

  const [config] = await db.select().from(sizeRulesConfig).where(eq(sizeRulesConfig.chartId, 'default'))
  const sizeRows = await db.select().from(nailSizes).where(eq(nailSizes.chartId, 'default'))

  const effectiveConfig = config ?? {
    id: 0, chartId: 'default', betweenSizes: 'size_down', toleranceMm: 0.3, updatedAt: new Date(),
  }

  const fingerNames = ['thumb', 'index', 'middle', 'ring', 'pinky'] as const
  const recommended: Record<string, { size: number; label: string }> = {}

  for (const finger of fingerNames) {
    const widthMm = body.measurements![finger]
    const relevant = rules.filter((r) => r.finger === 'all' || r.finger === finger)
    relevant.sort((a, b) => {
      if (b.priority !== a.priority) return b.priority - a.priority
      if (a.finger === finger && b.finger === 'all') return -1
      return 0
    })

    let size = relevant[0]?.mappedSize ?? 5 // fallback
    for (const rule of relevant) {
      if (widthMm >= rule.minWidthMm && widthMm <= rule.maxWidthMm) {
        size = rule.mappedSize
        break
      }
    }

    const label = sizeRows.find((s) => s.sizeNumber === size)?.label ?? String(size)
    recommended[finger] = { size, label }
  }

  const sizeProfile = fingerNames.map((f) => recommended[f].size).join('-')
  return c.json({ recommended, size_profile: sizeProfile })
})

// ══ Sets ═══════════════════════════════════════════════════════════════════════

/** GET /v1/admin/sets */
protect.get('/sets', async (c) => {
  const rows = await db.select().from(sizeSets).where(eq(sizeSets.chartId, 'default'))
  return c.json({ sets: rows })
})

/** POST /v1/admin/sets */
protect.post('/sets', async (c) => {
  let body: {
    name?: string
    thumb_size?: number
    index_size?: number
    middle_size?: number
    ring_size?: number
    pinky_size?: number
    shopify_variant_id?: string
    chart_id?: string
  }
  try {
    body = await c.req.json()
  } catch {
    return c.json({ error: 'validation_error', message: 'Request body must be JSON' }, 400)
  }

  const required = ['name', 'thumb_size', 'index_size', 'middle_size', 'ring_size', 'pinky_size'] as const
  const missing = required.filter((k) => body[k] == null)
  if (missing.length > 0) {
    return c.json({ error: 'validation_error', message: `Missing fields: ${missing.join(', ')}` }, 400)
  }

  const [row] = await db
    .insert(sizeSets)
    .values({
      chartId: body.chart_id ?? 'default',
      name: body.name!,
      thumbSize: body.thumb_size!,
      indexSize: body.index_size!,
      middleSize: body.middle_size!,
      ringSize: body.ring_size!,
      pinkySize: body.pinky_size!,
      shopifyVariantId: body.shopify_variant_id ?? null,
    })
    .returning()

  return c.json(row, 201)
})

/** PUT /v1/admin/sets/:id */
protect.put('/sets/:id', async (c) => {
  const id = Number(c.req.param('id'))
  let body: Partial<{
    name: string; thumb_size: number; index_size: number; middle_size: number
    ring_size: number; pinky_size: number; shopify_variant_id: string
  }>
  try {
    body = await c.req.json()
  } catch {
    return c.json({ error: 'validation_error', message: 'Request body must be JSON' }, 400)
  }

  const updates: Partial<typeof sizeSets.$inferInsert> = { updatedAt: new Date() }
  if (body.name != null) updates.name = body.name
  if (body.thumb_size != null) updates.thumbSize = body.thumb_size
  if (body.index_size != null) updates.indexSize = body.index_size
  if (body.middle_size != null) updates.middleSize = body.middle_size
  if (body.ring_size != null) updates.ringSize = body.ring_size
  if (body.pinky_size != null) updates.pinkySize = body.pinky_size
  if (body.shopify_variant_id !== undefined) updates.shopifyVariantId = body.shopify_variant_id

  const [row] = await db.update(sizeSets).set(updates).where(eq(sizeSets.id, id)).returning()
  if (!row) return c.json({ error: 'not_found', message: 'Set not found' }, 404)
  return c.json(row)
})

/** DELETE /v1/admin/sets/:id */
protect.delete('/sets/:id', async (c) => {
  const id = Number(c.req.param('id'))
  const [row] = await db.delete(sizeSets).where(eq(sizeSets.id, id)).returning()
  if (!row) return c.json({ error: 'not_found', message: 'Set not found' }, 404)
  return c.json({ deleted: true })
})

// ══ Measurements (read-only) ═══════════════════════════════════════════════════

/** GET /v1/admin/measurements/stats */
protect.get('/measurements/stats', async (c) => {
  const [total] = await db.select({ count: count() }).from(measurements)

  const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000)
  const [last7] = await db
    .select({ count: count() })
    .from(measurements)
    .where(gte(measurements.createdAt, sevenDaysAgo))

  const [avgConf] = await db
    .select({ avg: avg(measurements.overallConfidence) })
    .from(measurements)

  const [lowConf] = await db
    .select({ count: count() })
    .from(measurements)
    .where(lte(measurements.overallConfidence, 0.7))

  return c.json({
    total: total.count,
    last_7_days: last7.count,
    avg_confidence: avgConf.avg ? Number(Number(avgConf.avg).toFixed(4)) : null,
    low_confidence_count: lowConf.count,
  })
})

/** GET /v1/admin/measurements */
protect.get('/measurements', async (c) => {
  const page = Math.max(1, Number(c.req.query('page') ?? 1))
  const limit = Math.min(100, Math.max(1, Number(c.req.query('limit') ?? 20)))
  const offset = (page - 1) * limit

  const minConf = c.req.query('min_confidence')
  const fromDate = c.req.query('from_date')
  const toDate = c.req.query('to_date')

  const conditions = []
  if (minConf) conditions.push(gte(measurements.overallConfidence, parseFloat(minConf)))
  if (fromDate) conditions.push(gte(measurements.createdAt, new Date(fromDate)))
  if (toDate) conditions.push(lte(measurements.createdAt, new Date(toDate)))

  const where = conditions.length > 0 ? and(...conditions) : undefined

  const [{ total }] = await db.select({ total: count() }).from(measurements).where(where)

  const rows = await db
    .select()
    .from(measurements)
    .where(where)
    .orderBy(desc(measurements.createdAt))
    .limit(limit)
    .offset(offset)

  return c.json({
    measurements: rows,
    total,
    page,
    pages: Math.ceil(total / limit),
  })
})

/** GET /v1/admin/measurements/:id */
protect.get('/measurements/:id', async (c) => {
  const id = c.req.param('id')
  const [m] = await db.select().from(measurements).where(eq(measurements.id, id))
  if (!m) return c.json({ error: 'not_found', message: 'Measurement not found' }, 404)

  return c.json({
    ...m,
    debug_image_url: null, // TODO: signed URL when storage is configured
  })
})

admin.route('/', protect)

export default admin
