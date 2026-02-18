import {
  pgTable,
  text,
  integer,
  real,
  boolean,
  serial,
  jsonb,
  timestamp,
  unique,
  index,
} from 'drizzle-orm/pg-core'
import { sql } from 'drizzle-orm'

// ─── measurements ─────────────────────────────────────────────────────────────
// Stores every result from the CV pipeline. Per-finger data is JSONB for
// extensibility — new fields can be added without migrations.

export const measurements = pgTable(
  'measurements',
  {
    id: text('id').primaryKey(), // "msr_" + nanoid(12)
    imageKey: text('image_key').notNull(), // R2/S3 object key
    debugImageKey: text('debug_image_key'), // annotated image key
    hand: text('hand').notNull(), // "left" | "right"
    scalePxPerMm: real('scale_px_per_mm'),
    // { thumb: { width_mm, length_mm, curve_adj_width_mm, confidence }, ... }
    fingers: jsonb('fingers').notNull(),
    overallConfidence: real('overall_confidence'),
    warnings: jsonb('warnings').default(sql`'[]'::jsonb`),
    metadata: jsonb('metadata').default(sql`'{}'::jsonb`),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [
    index('idx_measurements_created').on(t.createdAt),
    index('idx_measurements_confidence').on(t.overallConfidence),
  ]
)

// ─── nail_sizes ───────────────────────────────────────────────────────────────
// Product nail dimensions per size number. chart_id supports future shapes
// (coffin, almond, etc.) — MVP uses "default" everywhere.

export const nailSizes = pgTable(
  'nail_sizes',
  {
    id: serial('id').primaryKey(),
    chartId: text('chart_id').notNull().default('default'),
    sizeNumber: integer('size_number').notNull(), // 0-9
    widthMm: real('width_mm').notNull(),
    lengthMm: real('length_mm'),
    curvatureMm: real('curvature_mm'),
    label: text('label'), // "Extra Large", "Small", etc.
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp('updated_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [unique('uq_nail_sizes_chart_number').on(t.chartId, t.sizeNumber)]
)

// ─── size_rules ───────────────────────────────────────────────────────────────
// Maps curve-adjusted width ranges to nail sizes. Evaluated priority-first.
// finger = "all" applies to all fingers; can be finger-specific too.

export const sizeRules = pgTable(
  'size_rules',
  {
    id: serial('id').primaryKey(),
    chartId: text('chart_id').notNull().default('default'),
    finger: text('finger').notNull().default('all'), // "all" | "thumb" | "index" | ...
    minWidthMm: real('min_width_mm').notNull(),
    maxWidthMm: real('max_width_mm').notNull(),
    mappedSize: integer('mapped_size').notNull(), // references nail_sizes.size_number
    priority: integer('priority').notNull().default(0),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index('idx_rules_chart').on(t.chartId)]
)

// ─── size_rules_config ────────────────────────────────────────────────────────
// Global config for the size mapping engine (one row per chart_id).

export const sizeRulesConfig = pgTable('size_rules_config', {
  id: serial('id').primaryKey(),
  chartId: text('chart_id').notNull().unique().default('default'),
  betweenSizes: text('between_sizes').notNull().default('size_down'), // "size_up" | "size_down"
  toleranceMm: real('tolerance_mm').notNull().default(0.3),
  updatedAt: timestamp('updated_at', { withTimezone: true }).notNull().defaultNow(),
})

// ─── size_sets ────────────────────────────────────────────────────────────────
// Pre-packaged size combinations linked to Shopify variants (Phase 3).

export const sizeSets = pgTable('size_sets', {
  id: serial('id').primaryKey(),
  chartId: text('chart_id').notNull().default('default'),
  name: text('name').notNull(), // "Small Set", "Medium Set"
  thumbSize: integer('thumb_size').notNull(),
  indexSize: integer('index_size').notNull(),
  middleSize: integer('middle_size').notNull(),
  ringSize: integer('ring_size').notNull(),
  pinkySize: integer('pinky_size').notNull(),
  shopifyVariantId: text('shopify_variant_id'), // Phase 3
  createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp('updated_at', { withTimezone: true }).notNull().defaultNow(),
})

// ─── recommendations ──────────────────────────────────────────────────────────
// Links a measurement to a size profile. Decoupled from measurements so the
// same measurement can be re-recommended if rules change.

export const recommendations = pgTable(
  'recommendations',
  {
    id: serial('id').primaryKey(),
    measurementId: text('measurement_id')
      .notNull()
      .references(() => measurements.id),
    chartId: text('chart_id').notNull().default('default'),
    sizeProfile: text('size_profile').notNull(), // "3-5-4-6-8"
    // { thumb: { size, label, fit }, index: ..., ... }
    sizes: jsonb('sizes').notNull(),
    matchingSetId: integer('matching_set_id').references(() => sizeSets.id),
    shopifyCustomerId: text('shopify_customer_id'), // Phase 3
    metafieldsWritten: boolean('metafields_written').default(false),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [
    index('idx_rec_measurement').on(t.measurementId),
    index('idx_rec_shopify').on(t.shopifyCustomerId),
  ]
)

// ─── admins ───────────────────────────────────────────────────────────────────
export const admins = pgTable('admins', {
  id: serial('id').primaryKey(),
  email: text('email').unique().notNull(),
  passwordHash: text('password_hash').notNull(), // bcrypt
  createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  lastLoginAt: timestamp('last_login_at', { withTimezone: true }),
})

// ─── Inferred types ───────────────────────────────────────────────────────────
export type Measurement = typeof measurements.$inferSelect
export type NewMeasurement = typeof measurements.$inferInsert
export type NailSize = typeof nailSizes.$inferSelect
export type SizeRule = typeof sizeRules.$inferSelect
export type SizeRulesConfig = typeof sizeRulesConfig.$inferSelect
export type SizeSet = typeof sizeSets.$inferSelect
export type Recommendation = typeof recommendations.$inferSelect
export type Admin = typeof admins.$inferSelect
