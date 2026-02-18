# Database Schema

**Engine:** PostgreSQL on Railway
**ORM:** Drizzle (TypeScript API) / SQLAlchemy (Python CV service)

---

## ER Diagram

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ measurements │     │  nail_sizes  │     │  size_rules  │
│──────────────│     │──────────────│     │──────────────│
│ id (PK)      │     │ id (PK)      │     │ id (PK)      │
│ image_key    │     │ chart_id     │←────│ chart_id     │
│ hand         │     │ size_number  │     │ finger       │
│ fingers (J)  │     │ width_mm     │     │ min_width_mm │
│ confidence   │     │ length_mm    │     │ max_width_mm │
│ ...          │     │ label        │     │ mapped_size  │
└──────┬───────┘     └──────────────┘     └──────────────┘
       │
       │ 1:1
       ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ recommen-    │     │  size_sets   │     │   admins     │
│  dations     │     │──────────────│     │──────────────│
│──────────────│     │ id (PK)      │     │ id (PK)      │
│ id (PK)      │     │ name         │     │ email        │
│ measurement_ │     │ thumb_size   │     │ password_hash│
│   id (FK)    │     │ index_size   │     │ created_at   │
│ size_profile │     │ ...          │     └──────────────┘
│ shopify_cust │     │ shopify_var  │
│ ...          │     └──────────────┘
└──────────────┘
```

---

## Tables

### `measurements`
Stores every measurement result from the CV pipeline.

```sql
CREATE TABLE measurements (
  id            TEXT PRIMARY KEY,               -- "msr_" + nanoid(12)
  image_key     TEXT NOT NULL,                  -- R2/S3 object key for original photo
  debug_image_key TEXT,                         -- annotated debug image key
  hand          TEXT NOT NULL CHECK (hand IN ('left', 'right')),
  scale_px_per_mm REAL,

  -- Per-finger measurements stored as JSONB for flexibility
  -- (avoids 15 separate columns, easy to add fields later)
  fingers       JSONB NOT NULL,
  /*
    {
      "thumb":  { "width_mm": 16.2, "length_mm": 12.1, "curve_adj_width_mm": 17.8, "confidence": 0.94 },
      "index":  { ... },
      "middle": { ... },
      "ring":   { ... },
      "pinky":  { ... }
    }
  */

  overall_confidence REAL,
  warnings      JSONB DEFAULT '[]',            -- ["partial_occlusion", ...]
  metadata      JSONB DEFAULT '{}',            -- extensible (device info, etc.)

  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- Indexes
  CONSTRAINT valid_confidence CHECK (overall_confidence BETWEEN 0 AND 1)
);

CREATE INDEX idx_measurements_created ON measurements (created_at DESC);
CREATE INDEX idx_measurements_confidence ON measurements (overall_confidence);
```

### `nail_sizes`
Product nail dimensions per size number. Grouped by `chart_id` to support multiple size charts in the future (different nail shapes).

```sql
CREATE TABLE nail_sizes (
  id            SERIAL PRIMARY KEY,
  chart_id      TEXT NOT NULL DEFAULT 'default',  -- future: "coffin", "almond", etc.
  size_number   INTEGER NOT NULL,                 -- 0-9
  width_mm      REAL NOT NULL,
  length_mm     REAL,
  curvature_mm  REAL,                             -- optional, for future curve matching
  label         TEXT,                              -- "Extra Large", "Small", etc.

  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

  UNIQUE (chart_id, size_number)
);
```

### `size_rules`
Maps curve-adjusted width ranges to nail sizes. Evaluated in priority order.

```sql
CREATE TABLE size_rules (
  id            SERIAL PRIMARY KEY,
  chart_id      TEXT NOT NULL DEFAULT 'default',
  finger        TEXT NOT NULL DEFAULT 'all',       -- "all" or specific finger name
  min_width_mm  REAL NOT NULL,
  max_width_mm  REAL NOT NULL,
  mapped_size   INTEGER NOT NULL,                  -- references nail_sizes.size_number
  priority      INTEGER NOT NULL DEFAULT 0,        -- higher = evaluated first

  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

  CHECK (min_width_mm < max_width_mm),
  CHECK (finger IN ('all', 'thumb', 'index', 'middle', 'ring', 'pinky'))
);

CREATE INDEX idx_rules_chart ON size_rules (chart_id);
```

### `size_rules_config`
Global configuration for the size mapping engine.

```sql
CREATE TABLE size_rules_config (
  id            SERIAL PRIMARY KEY,
  chart_id      TEXT NOT NULL DEFAULT 'default' UNIQUE,
  between_sizes TEXT NOT NULL DEFAULT 'size_down'  -- "size_up" | "size_down"
    CHECK (between_sizes IN ('size_up', 'size_down')),
  tolerance_mm  REAL NOT NULL DEFAULT 0.3,

  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `size_sets`
Pre-packaged size combinations linked to Shopify variants.

```sql
CREATE TABLE size_sets (
  id            SERIAL PRIMARY KEY,
  chart_id      TEXT NOT NULL DEFAULT 'default',
  name          TEXT NOT NULL,                     -- "Small Set", "Medium Set"
  thumb_size    INTEGER NOT NULL,
  index_size    INTEGER NOT NULL,
  middle_size   INTEGER NOT NULL,
  ring_size     INTEGER NOT NULL,
  pinky_size    INTEGER NOT NULL,
  shopify_variant_id TEXT,                         -- linked Shopify variant (Phase 3)

  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `recommendations`
Stores size recommendations — links a measurement to a size profile and optionally a Shopify customer.

```sql
CREATE TABLE recommendations (
  id              SERIAL PRIMARY KEY,
  measurement_id  TEXT NOT NULL REFERENCES measurements(id),
  chart_id        TEXT NOT NULL DEFAULT 'default',
  size_profile    TEXT NOT NULL,                   -- "3-5-4-6-8"

  -- Per-finger size assignments
  sizes           JSONB NOT NULL,
  /*
    {
      "thumb":  { "size": 3, "label": "Medium-Large", "fit": "snug" },
      "index":  { "size": 5, "label": "Medium", "fit": "standard" },
      ...
    }
  */

  matching_set_id INTEGER REFERENCES size_sets(id),

  -- Shopify link (Phase 3)
  shopify_customer_id TEXT,                       -- "gid://shopify/Customer/12345"
  metafields_written  BOOLEAN DEFAULT false,

  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_rec_measurement ON recommendations (measurement_id);
CREATE INDEX idx_rec_shopify ON recommendations (shopify_customer_id);
```

### `admins`
Simple admin auth for the dashboard.

```sql
CREATE TABLE admins (
  id            SERIAL PRIMARY KEY,
  email         TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,                     -- bcrypt
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_login_at TIMESTAMPTZ
);
```

---

## Design Decisions

### Why JSONB for fingers?
Each finger has 3-4 measurements now, but we'll likely add more (nail shape classification, curvature estimate, etc.). JSONB lets us extend without migrations. The top-level structure (5 fingers) is stable — it's the per-finger fields that'll evolve.

### Why `chart_id` on sizes/rules/sets?
Steven wants single chart now but flexible for multiple shapes later. `chart_id = 'default'` everywhere for MVP. When Sev adds coffin vs almond shapes, we add rows with different `chart_id` values — no schema changes needed.

### Why a separate `recommendations` table?
Decouples measurement (CV output) from sizing (business logic). Same measurement can be re-recommended if size rules change. Also cleanly links to Shopify customer.

### Image storage
Original photos and debug images stored in Railway's volume or S3-compatible storage. DB stores only the object key. Signed URLs generated on access.

---

## Migrations

Using Drizzle Kit for migrations. Schema defined in TypeScript, SQL generated automatically.

```
sev-nail-sizer/
├── api/
│   └── src/
│       └── db/
│           ├── schema.ts        -- Drizzle schema definitions
│           ├── migrate.ts       -- Migration runner
│           └── seed.ts          -- Seed admin user + sample sizes
```

### Seed Data
- 1 admin user (email + hashed password)
- Default size chart (sizes 0-9 with placeholder dimensions — Steven fills in real values)
- Default size rules (even width ranges as starting point)

---

## Design Decisions Log

1. **JSONB for per-finger data** — extensible without migrations as we add fields
2. **`chart_id` for future multi-shape support** — different dimensions per shape, may extend to other attributes later
3. **Separate `recommendations` table** — decouples CV output from business logic; supports auto-update when rules change
4. **Measurement history kept forever** — customer profile uses latest, but all past measurements preserved
5. **Auto-update on rule change** — background job re-evaluates all active profiles against new rules
6. **Per-finger rules deferred** — schema supports it (`finger` column), decision on whether to use TBD
