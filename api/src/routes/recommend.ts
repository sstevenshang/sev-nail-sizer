import { Hono } from 'hono'
import { eq, desc } from 'drizzle-orm'
import { db } from '../db/index.js'
import {
  measurements,
  nailSizes,
  sizeRules,
  sizeRulesConfig,
  sizeSets,
  recommendations,
  type SizeRule,
  type SizeRulesConfig,
} from '../db/schema.js'

const recommend = new Hono()

// ─── Size-mapping engine ───────────────────────────────────────────────────────

type FingerName = 'thumb' | 'index' | 'middle' | 'ring' | 'pinky'
type FitLabel = 'snug' | 'standard' | 'loose'

interface FingerResult {
  size: number
  size_label: string
  width_mm: number
  fit: FitLabel
}

function applyRulesToFinger(
  widthMm: number,
  fingerName: FingerName,
  rules: SizeRule[],
  config: SizeRulesConfig
): { size: number; fit: FitLabel } {
  // Filter to rules relevant for this finger
  const relevant = rules.filter((r) => r.finger === 'all' || r.finger === fingerName)

  // Sort: higher priority first; finger-specific beats 'all' at equal priority
  relevant.sort((a, b) => {
    if (b.priority !== a.priority) return b.priority - a.priority
    if (a.finger === fingerName && b.finger === 'all') return -1
    if (a.finger === 'all' && b.finger === fingerName) return 1
    return 0
  })

  // Exact range match
  for (const rule of relevant) {
    if (widthMm >= rule.minWidthMm && widthMm <= rule.maxWidthMm) {
      const range = rule.maxWidthMm - rule.minWidthMm
      const position = range > 0 ? (widthMm - rule.minWidthMm) / range : 0.5
      const fit: FitLabel = position < 0.33 ? 'snug' : position > 0.67 ? 'loose' : 'standard'
      return { size: rule.mappedSize, fit }
    }
  }

  // No exact match — find nearest boundary within tolerance
  let nearestRule: SizeRule | null = null
  let nearestDiff = Infinity

  for (const rule of relevant) {
    const diff = Math.min(
      Math.abs(widthMm - rule.minWidthMm),
      Math.abs(widthMm - rule.maxWidthMm)
    )
    if (diff <= config.toleranceMm && diff < nearestDiff) {
      nearestDiff = diff
      nearestRule = rule
    }
  }

  if (nearestRule) {
    const fit: FitLabel = config.betweenSizes === 'size_down' ? 'snug' : 'loose'
    return { size: nearestRule.mappedSize, fit }
  }

  // Last resort: find the closest rule regardless of tolerance
  let closestRule = relevant[0]
  let closestDiff = Infinity
  for (const rule of relevant) {
    const diff = Math.min(
      Math.abs(widthMm - rule.minWidthMm),
      Math.abs(widthMm - rule.maxWidthMm)
    )
    if (diff < closestDiff) {
      closestDiff = diff
      closestRule = rule
    }
  }

  return { size: closestRule.mappedSize, fit: 'standard' }
}

// ─── POST /v1/recommend ────────────────────────────────────────────────────────

/**
 * POST /v1/recommend
 * Given a measurement_id, applies size rules and returns per-finger recommendations
 * plus matching pre-packaged sets.
 */
recommend.post('/', async (c) => {
  let body: { measurement_id?: string }
  try {
    body = await c.req.json()
  } catch {
    return c.json({ error: 'validation_error', message: 'Request body must be JSON' }, 400)
  }

  if (!body.measurement_id) {
    return c.json({ error: 'validation_error', message: 'measurement_id is required' }, 400)
  }

  // 1. Fetch measurement
  const [measurement] = await db
    .select()
    .from(measurements)
    .where(eq(measurements.id, body.measurement_id))

  if (!measurement) {
    return c.json({ error: 'not_found', message: 'Measurement not found' }, 404)
  }

  // 2. Check rules exist
  const rules = await db
    .select()
    .from(sizeRules)
    .where(eq(sizeRules.chartId, 'default'))
    .orderBy(desc(sizeRules.priority))

  if (rules.length === 0) {
    return c.json(
      { error: 'no_rules', message: 'Size mapping rules have not been configured. Contact admin.' },
      400
    )
  }

  // 3. Fetch config (use defaults if not found)
  const [config] = await db
    .select()
    .from(sizeRulesConfig)
    .where(eq(sizeRulesConfig.chartId, 'default'))

  const effectiveConfig: SizeRulesConfig = config ?? {
    id: 0,
    chartId: 'default',
    betweenSizes: 'size_down',
    toleranceMm: 0.3,
    updatedAt: new Date(),
  }

  // 4. Fetch nail size labels
  const sizeRows = await db
    .select()
    .from(nailSizes)
    .where(eq(nailSizes.chartId, 'default'))

  const sizeLabel = (sizeNumber: number): string =>
    sizeRows.find((s) => s.sizeNumber === sizeNumber)?.label ?? String(sizeNumber)

  // 5. Apply rules to each finger
  const fingers = measurement.fingers as Record<
    FingerName,
    { width_mm: number; length_mm: number; curve_adj_width_mm: number; confidence: number }
  >

  const fingerNames: FingerName[] = ['thumb', 'index', 'middle', 'ring', 'pinky']
  const perFinger: Record<FingerName, FingerResult> = {} as Record<FingerName, FingerResult>

  for (const name of fingerNames) {
    const finger = fingers[name]
    if (!finger) {
      return c.json(
        { error: 'validation_error', message: `Measurement missing data for finger: ${name}` },
        400
      )
    }

    const { size, fit } = applyRulesToFinger(
      finger.curve_adj_width_mm,
      name,
      rules,
      effectiveConfig
    )

    perFinger[name] = {
      size,
      size_label: sizeLabel(size),
      width_mm: finger.curve_adj_width_mm,
      fit,
    }
  }

  // 6. Build size profile string: "thumb-index-middle-ring-pinky"
  const sizeProfile = fingerNames.map((n) => perFinger[n].size).join('-')

  // 7. Find matching sets (include sets with ≤ 2 finger differences)
  const sets = await db
    .select()
    .from(sizeSets)
    .where(eq(sizeSets.chartId, 'default'))

  const matchingSets = sets
    .map((set) => {
      const setMap: Record<FingerName, number> = {
        thumb: set.thumbSize,
        index: set.indexSize,
        middle: set.middleSize,
        ring: set.ringSize,
        pinky: set.pinkySize,
      }
      const diff = fingerNames.filter((n) => perFinger[n].size !== setMap[n]).length
      return { set_name: set.name, set_id: `set_${set.id}`, exact_match: diff === 0, diff, _id: set.id }
    })
    .filter((s) => s.diff <= 2)
    .sort((a, b) => a.diff - b.diff)

  const bestMatchSetId = matchingSets[0]?._id ?? null

  // 8. Store recommendation
  const sizesJson = Object.fromEntries(
    fingerNames.map((n) => [n, { size: perFinger[n].size, label: perFinger[n].size_label, fit: perFinger[n].fit }])
  )

  await db.insert(recommendations).values({
    measurementId: body.measurement_id,
    chartId: 'default',
    sizeProfile,
    sizes: sizesJson,
    matchingSetId: bestMatchSetId,
  })

  // 9. Return
  return c.json({
    measurement_id: body.measurement_id,
    size_profile: sizeProfile,
    per_finger: perFinger,
    matching_sets: matchingSets.map(({ _id, ...s }) => s),
  })
})

export default recommend
