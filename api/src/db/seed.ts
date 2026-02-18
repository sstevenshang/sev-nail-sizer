/**
 * Seed script: inserts default admin, nail sizes 0-9, size rules, and config.
 * Run once after migrations: npm run db:seed
 *
 * NOTE: Change the admin password immediately after first run.
 */
import 'dotenv/config'
import bcrypt from 'bcrypt'
import { drizzle } from 'drizzle-orm/node-postgres'
import { Pool } from 'pg'
import { admins, nailSizes, sizeRules, sizeRulesConfig } from './schema.js'
import { eq } from 'drizzle-orm'

const pool = new Pool({ connectionString: process.env.DATABASE_URL })
const db = drizzle(pool)

// ─── Admin ────────────────────────────────────────────────────────────────────
const email = process.env.ADMIN_DEFAULT_EMAIL ?? 'admin@sev.com'
const password = process.env.ADMIN_DEFAULT_PASSWORD ?? 'changeme123!'
const passwordHash = await bcrypt.hash(password, 12)

const existing = await db.select().from(admins).where(eq(admins.email, email))
if (existing.length === 0) {
  await db.insert(admins).values({ email, passwordHash })
  console.log(`Admin created: ${email}`)
} else {
  console.log(`Admin already exists: ${email}`)
}

// ─── Nail sizes 0–9 (default chart) ──────────────────────────────────────────
// Placeholder dimensions — Steven fills in actual product measurements.
const defaultSizes = [
  { sizeNumber: 0, widthMm: 17.5, lengthMm: 14.0, label: 'Extra Large' },
  { sizeNumber: 1, widthMm: 16.5, lengthMm: 13.5, label: 'Large' },
  { sizeNumber: 2, widthMm: 15.5, lengthMm: 13.0, label: 'Large-Medium' },
  { sizeNumber: 3, widthMm: 14.8, lengthMm: 12.5, label: 'Medium-Large' },
  { sizeNumber: 4, widthMm: 14.1, lengthMm: 12.0, label: 'Medium' },
  { sizeNumber: 5, widthMm: 13.4, lengthMm: 11.5, label: 'Medium' },
  { sizeNumber: 6, widthMm: 12.7, lengthMm: 11.0, label: 'Small-Medium' },
  { sizeNumber: 7, widthMm: 12.0, lengthMm: 10.5, label: 'Small' },
  { sizeNumber: 8, widthMm: 11.3, lengthMm: 10.0, label: 'Small' },
  { sizeNumber: 9, widthMm: 10.5, lengthMm: 9.5, label: 'Extra Small' },
]

for (const s of defaultSizes) {
  await db
    .insert(nailSizes)
    .values({ ...s, chartId: 'default' })
    .onConflictDoNothing()
}
console.log(`Seeded ${defaultSizes.length} nail sizes.`)

// ─── Default size rules ───────────────────────────────────────────────────────
// Even width ranges as a starting point — Sev calibrates these with real data.
const defaultRules = [
  { mappedSize: 0, minWidthMm: 17.0, maxWidthMm: 30.0 },
  { mappedSize: 1, minWidthMm: 15.5, maxWidthMm: 17.0 },
  { mappedSize: 2, minWidthMm: 14.5, maxWidthMm: 15.5 },
  { mappedSize: 3, minWidthMm: 13.8, maxWidthMm: 14.5 },
  { mappedSize: 4, minWidthMm: 13.1, maxWidthMm: 13.8 },
  { mappedSize: 5, minWidthMm: 12.4, maxWidthMm: 13.1 },
  { mappedSize: 6, minWidthMm: 11.7, maxWidthMm: 12.4 },
  { mappedSize: 7, minWidthMm: 11.0, maxWidthMm: 11.7 },
  { mappedSize: 8, minWidthMm: 10.3, maxWidthMm: 11.0 },
  { mappedSize: 9, minWidthMm: 5.0, maxWidthMm: 10.3 },
]

const existingRules = await db.select().from(sizeRules)
if (existingRules.length === 0) {
  await db.insert(sizeRules).values(
    defaultRules.map((r) => ({ ...r, chartId: 'default', finger: 'all', priority: 0 }))
  )
  console.log(`Seeded ${defaultRules.length} size rules.`)
} else {
  console.log(`Size rules already exist (${existingRules.length}), skipping.`)
}

// ─── Default size rules config ────────────────────────────────────────────────
await db
  .insert(sizeRulesConfig)
  .values({ chartId: 'default', betweenSizes: 'size_down', toleranceMm: 0.3 })
  .onConflictDoNothing()
console.log('Size rules config seeded.')

await pool.end()
console.log('Seed complete.')
