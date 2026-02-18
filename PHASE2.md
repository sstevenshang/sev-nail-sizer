# Phase 2: Admin Panel — Product Config & Size Mapping

Web dashboard for managing nail product dimensions, size mappings, and viewing measurement analytics.

## Architecture

```
Admin → Next.js app (Vercel) → API routes → Turso DB
                              → R2 (product images)
```

### Tech Stack
- **Frontend:** Next.js 15 (App Router) + Tailwind + shadcn/ui
- **Auth:** NextAuth.js with email/password (single admin for MVP)
- **Database:** Same Turso instance as Phase 1
- **Hosting:** Vercel

## Features

### 1. Size Chart Management
- CRUD for nail sizes (typically 0-9)
- Per size: width_mm, length_mm, curvature_mm, label
- Bulk import/export (CSV)
- Visual size chart preview

### 2. Size Mapping Rules
- Configure how curve-adjusted measurements map to sizes
- Per-finger tolerance settings (e.g., ±0.3mm → size up)
- Round-up vs round-down preference
- Preview: "14.2mm width → Size 6"

### 3. Product Management
- Link sizes to Shopify products (by SKU or product ID)
- Pre-packaged sets: define size combos (e.g., "Medium set = 3-5-4-6-8")
- Custom sets: let size mapping auto-generate per customer

### 4. Measurement Dashboard
- Browse all measurements (with debug images)
- Filter by date, confidence, warnings
- Accuracy stats (if ground truth provided)

## Database Schema

```sql
-- Nail sizes for a product line
CREATE TABLE nail_sizes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  size_number INTEGER NOT NULL,       -- 0-9
  width_mm REAL NOT NULL,
  length_mm REAL,
  curvature_mm REAL,
  label TEXT,                          -- "Extra Small", "Small", etc.
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);

-- Size mapping rules
CREATE TABLE size_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  finger TEXT NOT NULL,               -- thumb/index/middle/ring/pinky or "all"
  min_width_mm REAL NOT NULL,
  max_width_mm REAL NOT NULL,
  mapped_size INTEGER NOT NULL,       -- references nail_sizes.size_number
  priority INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now'))
);

-- Pre-packaged size sets
CREATE TABLE size_sets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,                  -- "Small Set", "Medium Set"
  thumb_size INTEGER,
  index_size INTEGER,
  middle_size INTEGER,
  ring_size INTEGER,
  pinky_size INTEGER,
  shopify_variant_id TEXT,            -- linked Shopify variant
  created_at TEXT DEFAULT (datetime('now'))
);

-- Admin users
CREATE TABLE admins (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now'))
);
```

## API Routes

### Size Chart
```
GET    /api/sizes              → list all sizes
POST   /api/sizes              → create size { size_number, width_mm, ... }
PUT    /api/sizes/:id          → update size
DELETE /api/sizes/:id          → delete size
POST   /api/sizes/import       → bulk CSV import
GET    /api/sizes/export       → CSV export
```

### Size Mapping
```
GET    /api/rules              → list mapping rules
POST   /api/rules              → create rule
PUT    /api/rules/:id          → update rule
DELETE /api/rules/:id          → delete rule
POST   /api/rules/preview      → { measurements } → { recommended_sizes }
```

### Size Sets
```
GET    /api/sets               → list pre-packaged sets
POST   /api/sets               → create set
PUT    /api/sets/:id           → update set
DELETE /api/sets/:id           → delete set
```

### Measurements (read-only in admin)
```
GET    /api/measurements       → list (paginated, filterable)
GET    /api/measurements/:id   → detail with debug image
GET    /api/measurements/stats → accuracy/volume stats
```

## UI Pages

```
/admin
├── /login
├── /dashboard               → stats overview
├── /sizes                   → size chart CRUD
│   ├── (table view with inline edit)
│   └── /import              → CSV upload
├── /rules                   → size mapping config
│   ├── (visual range editor)
│   └── /preview             → test with sample measurements
├── /sets                    → pre-packaged sets
└── /measurements            → browse measurements
    └── /:id                 → detail view with debug image
```

## Key UI Components

### Size Chart Editor
```
┌─────────────────────────────────────────────┐
│ Size Chart                          [+ Add] │
├──────┬──────────┬──────────┬────────────────┤
│ Size │ Width mm │ Length mm│ Label          │
├──────┼──────────┼──────────┼────────────────┤
│  0   │  17.5    │  14.0   │ Extra Large    │
│  1   │  16.5    │  13.5   │ Large          │
│  2   │  15.8    │  13.0   │ Medium-Large   │
│  ...                                        │
│  9   │  10.0    │   8.0   │ Extra Small    │
└─────────────────────────────────────────────┘
        [Import CSV]  [Export CSV]
```

### Size Rule Editor
Visual range slider per finger showing width ranges → size mappings. Click to adjust boundaries. Preview panel on the right shows "if customer measures X, they get size Y."

### Measurement Browser
Card grid with thumbnail of debug image, date, confidence badge, size profile summary. Click for full detail.

## Directory Structure

```
sev-nail-sizer/
├── admin/                          # Next.js admin panel
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── login/page.tsx
│   │   │   ├── dashboard/page.tsx
│   │   │   ├── sizes/page.tsx
│   │   │   ├── rules/page.tsx
│   │   │   ├── sets/page.tsx
│   │   │   └── measurements/
│   │   │       ├── page.tsx
│   │   │       └── [id]/page.tsx
│   │   ├── api/
│   │   │   ├── sizes/route.ts
│   │   │   ├── rules/route.ts
│   │   │   ├── sets/route.ts
│   │   │   └── measurements/route.ts
│   │   ├── components/
│   │   │   ├── size-chart-editor.tsx
│   │   │   ├── rule-range-editor.tsx
│   │   │   ├── measurement-card.tsx
│   │   │   └── csv-import.tsx
│   │   └── lib/
│   │       ├── db.ts
│   │       └── auth.ts
│   ├── next.config.ts
│   └── package.json
```

## Task Breakdown

| # | Task | Effort |
|---|------|--------|
| 1 | Next.js project setup + Tailwind + shadcn | 1h |
| 2 | Auth (NextAuth + admin seed) | 2h |
| 3 | DB schema migration (new tables) | 1h |
| 4 | Size chart CRUD (API + UI) | 4h |
| 5 | CSV import/export for sizes | 2h |
| 6 | Size mapping rules (API + UI) | 5h |
| 7 | Rule preview/test tool | 2h |
| 8 | Pre-packaged sets (API + UI) | 3h |
| 9 | Measurement browser (API + UI) | 4h |
| 10 | Dashboard stats page | 2h |
| 11 | Polish + responsive design | 2h |
| **Total** | | **~28h (~4 days)** |

## Open Questions
1. How many product lines will Sev have? (One size chart vs multiple)
   - *Rec: single size chart for MVP, add product line selector in v2*
2. Should admin be able to manually override a customer's measurements?
   - *Rec: yes, add override field in measurement detail view*
3. Multi-admin support needed?
   - *Rec: single admin for MVP, add roles later*
