import 'dotenv/config'
import { drizzle } from 'drizzle-orm/node-postgres'
import { migrate } from 'drizzle-orm/node-postgres/migrator'
import { Pool } from 'pg'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const __dirname = dirname(fileURLToPath(import.meta.url))

const pool = new Pool({ connectionString: process.env.DATABASE_URL })
const db = drizzle(pool)

console.log('Running migrations…')
await migrate(db, { migrationsFolder: join(__dirname, '../../drizzle') })
console.log('Migrations complete.')

await pool.end()
