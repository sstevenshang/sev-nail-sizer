# Sev Nail Sizer

AI-powered nail measurement service for [Sev](https://sev.myshopify.com) — a press-on nail brand. Customers photograph their hand on a credit card, and the system returns per-finger nail measurements with size recommendations.

**Status: Phase 1 ✅ | Phase 2 ✅ | Phase 3 ⏳**

## How It Works

1. Customer places their hand flat on a credit card and takes **two photos** from ~12" above:
   - **Photo 1:** Index, middle, ring, and pinky fingers on the card
   - **Photo 2:** Thumb on the card (a standard credit card can't fit all 5 fingers at once)
2. Each photo is processed independently through the CV pipeline
3. The system detects the card for scale calibration (ISO 7810: 85.6 × 53.98mm)
4. Nail segmentation extracts each nail's width and length in millimeters
5. Curvature adjustment converts flat 2D measurements to estimated 3D nail width
6. Results from both photos are merged into a complete 5-finger size profile (e.g., `3-5-4-6-8`)
7. Size profile maps to Sev's product sizes for instant recommendations

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│ Phase 3: Shopify App (Remix)                                  │
│   App Proxy → Customer sizer UI (Next.js on Vercel)           │
│   Theme App Extension → Size banner on product pages          │
│   Customer metafields → sev_nails.size_profile                │
├───────────────────────────────────────────────────────────────┤
│ Phase 2: Admin Panel (Next.js + Tailwind + shadcn/ui)         │
│   Size chart CRUD · Size mapping rules · Measurement browser  │
│   Pre-packaged sets · CSV import/export · Rule preview        │
├───────────────────────────────────────────────────────────────┤
│ Phase 1: CV Pipeline (Python FastAPI)                         │
│   Card detection → Hand detection → Nail segmentation         │
│   → Measurement extraction → Curve adjustment → Debug viz     │
├───────────────────────────────────────────────────────────────┤
│ Infrastructure                                                │
│   Railway (hosting + Postgres) · Replicate (SAM 2 inference)  │
│   R2/S3 (image storage) · Vercel (admin + storefront)         │
└───────────────────────────────────────────────────────────────┘
```

## Project Structure

```
sev-nail-sizer/
├── cv/                          # Phase 1: Python CV pipeline
│   ├── app.py                   # FastAPI service (validate, measure, merge)
│   ├── pipeline/
│   │   ├── preprocess.py        # Resize, blur check, brightness check
│   │   ├── card_detect.py       # Credit card detection + scale calibration
│   │   ├── hand_detect.py       # MediaPipe hand landmark detection
│   │   ├── nail_segment.py      # Nail segmentation (OpenCV + SAM 2 fallback)
│   │   ├── measure.py           # Width/length extraction from masks
│   │   ├── curve_adjust.py      # 2D→3D curvature compensation
│   │   └── debug_viz.py         # Annotated debug image generation
│   ├── tests/
│   │   ├── test_preprocess.py
│   │   ├── test_card_detect.py
│   │   ├── test_measure.py
│   │   ├── test_curve_adjust.py
│   │   ├── test_api.py
│   │   ├── test_e2e.py
│   │   └── test_stress.py
│   ├── conftest.py
│   ├── requirements.txt
│   └── Dockerfile
├── admin/                       # Phase 2: Next.js admin dashboard
│   ├── src/
│   │   ├── app/
│   │   │   ├── dashboard/       # Stats overview
│   │   │   ├── sizes/           # Size chart CRUD
│   │   │   ├── rules/           # Size mapping rules
│   │   │   ├── sets/            # Pre-packaged size sets
│   │   │   ├── measurements/    # Measurement browser + detail
│   │   │   └── login/
│   │   ├── components/          # Shared UI components
│   │   ├── lib/                 # DB, auth, utilities
│   │   └── middleware.ts
│   └── package.json
├── DESIGN.md                    # Architecture & design overview
├── API-DESIGN.md                # Full API specification
├── DB-SCHEMA.md                 # Database schema (PostgreSQL)
├── CONFIGURATION.md             # Tunable parameters & calibration guide
├── PHASE1.md                    # Phase 1 spec & task breakdown
├── PHASE2.md                    # Phase 2 spec & task breakdown
├── PHASE3.md                    # Phase 3 spec & task breakdown
└── HUMAN-TODO.md                # Items requiring human input
```

---

## Phase 1: CV Pipeline ✅

**Status: Complete — 69 tests passing**

Python FastAPI service that processes hand-on-card photos and returns nail measurements.

### Pipeline Stages

1. **Preprocessing** — Resize to max 2048px, assess blur (Laplacian variance) and brightness
2. **Card Detection** — Multi-strategy approach:
   - Canny edge detection → contour filtering → aspect ratio validation (~1.586)
   - Multi-epsilon `approxPolyDP` (0.02 → 0.04 → 0.06 → 0.08)
   - `minAreaRect` box-point fallback for imperfect contours
   - Rectangularity filter (contour area / rect area > 0.7)
   - Fallback chain: Canny → adaptive threshold → Otsu → high binary threshold
   - Output: `px_per_mm` scale factor from `card_width_pixels / 85.6mm`
3. **Hand Detection** — MediaPipe Hands (21 landmarks, fingertip + DIP positions)
4. **Nail Segmentation** — HSV skin detection + saturation/value thresholding for nail candidates, connected component selection near fingertips. Mock mode available (`SEV_MOCK_SEGMENTATION=1`). SAM 2 via Replicate planned for production.
5. **Measurement** — Width (widest horizontal span) and length (top-to-bottom span) extracted from nail masks, converted to mm via `px_per_mm`
6. **Curve Adjustment** — Lookup table compensating for nail curvature:
   - Nail/finger ratio < 0.70 → ×1.05
   - 0.70–0.85 → ×1.12
   - ≥ 0.85 → ×1.18
7. **Debug Visualization** — Annotated image with card outline, hand landmarks, nail masks, and measurement labels

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/pipeline/validate` | Quick pre-check (~1s): card detected? hand detected? image quality? |
| `POST` | `/pipeline/measure` | Full pipeline (5-15s): returns per-finger measurements |
| `POST` | `/pipeline/merge` | Combine thumb + four-finger measurements into complete profile |
| `GET` | `/measurements` | List stored measurements |
| `GET` | `/measurements/:id` | Retrieve a specific measurement |
| `GET` | `/health` | Health check |

### Two-Photo Flow

A credit card can't fit all 5 fingers at once. The API accepts each photo separately:

```
POST /pipeline/measure  (photo_type=four_finger)  →  msr_abc123
POST /pipeline/measure  (photo_type=thumb)         →  msr_def456
POST /pipeline/merge    { thumb_id, four_finger_id } →  msr_merged_789
```

`photo_type` is auto-detected from landmark positions if not specified.

### Running Locally

```bash
cd cv
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

### Running Tests

```bash
cd cv
source .venv/bin/activate
python -m pytest --tb=short -q     # 69 tests
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SEV_MOCK_SEGMENTATION` | unset | `"1"` → synthetic ellipse masks (no real segmentation) |
| `SEV_USE_REPLICATE` | unset | `"1"` → use SAM 2 via Replicate API |
| `REPLICATE_API_TOKEN` | unset | Replicate API key (for SAM 2) |
| `SEV_DB_PATH` | `./sev_nails.db` | SQLite database path |
| `SEV_IMAGE_DIR` | `./debug_images/` | Debug image output directory |
| `SEV_PERSIST` | `"1"` | `"0"` → disable persistence (tests) |

---

## Phase 2: Admin Panel ✅

**Status: Complete**

Next.js 15 dashboard for managing nail sizes, mapping rules, and reviewing measurements.

### Features

- **Size Chart Management** — CRUD for sizes 0-9 with width/length/label. CSV import/export.
- **Size Mapping Rules** — Configure width ranges → size mappings. Per-finger or universal rules. Between-sizes preference (size up/down). Preview tool to test rules against sample measurements.
- **Pre-packaged Sets** — Define size combinations (e.g., "Medium Set = 3-5-4-6-8"). Link to Shopify variants.
- **Measurement Browser** — Browse all measurements with debug images, filter by date/confidence/warnings.
- **Dashboard** — Volume stats, accuracy metrics, common warnings.

### Pages

| Route | Description |
|-------|-------------|
| `/login` | Admin authentication |
| `/dashboard` | Stats overview |
| `/sizes` | Size chart editor with inline editing |
| `/rules` | Size mapping rule configuration + preview |
| `/sets` | Pre-packaged size set management |
| `/measurements` | Measurement list (paginated, filterable) |
| `/measurements/:id` | Detail view with debug image |

### Running Locally

```bash
cd admin
npm install
cp .env.local.example .env.local   # Configure DB connection
npm run dev                         # http://localhost:3000
```

---

## Phase 3: Shopify Integration ⏳

**Status: Not started (~45h estimated)**

Connect the measurement pipeline to Sev's Shopify store so customers can measure once and get size recommendations on every product page.

### Planned Architecture

- **Shopify Custom App** (Remix template) with App Bridge 4
- **App Proxy:** `sev.myshopify.com/apps/nail-sizer` → customer-facing sizer UI
- **Theme App Extension:** Size recommendation banner on product pages
- **Customer Metafields:** `sev_nails.size_profile`, `sev_nails.measurements`, `sev_nails.measured_at`
- **Auth:** Shopify Customer Account API (no separate login)

### Customer UX Flow

```
Step 1: "Find Your Nail Size" landing page
  ↓
Step 2: Photo 1 — Place index through pinky on credit card → capture → analyze
  ↓
Step 3: Photo 2 — Place thumb on credit card → capture → analyze
  ↓
Step 4: Results — Per-finger sizes displayed, profile string generated
  ↓
Step 5: Save to account → Metafields written → Product pages show "Your size: 3-5-4-6-8"
```

### Task Breakdown

| # | Task | Effort |
|---|------|--------|
| 1 | Shopify app scaffold (`shopify app init`) | 2h |
| 2 | App proxy setup + storefront routing | 3h |
| 3 | Customer auth via Shopify session | 3h |
| 4 | Guided camera/upload UI | 6h |
| 5 | Camera overlay (card + hand guide) | 4h |
| 6 | Real-time validation feedback | 3h |
| 7 | Results display page | 3h |
| 8 | Recommendation API (measurement → size → profile) | 4h |
| 9 | Customer metafield write/read | 2h |
| 10 | Theme app extension (size banner) | 3h |
| 11 | Auto-select variant on product page | 2h |
| 12 | Embedded admin view | 2h |
| 13 | Mobile responsiveness + camera polish | 4h |
| 14 | End-to-end testing | 4h |

---

## Database Schema

**Engine:** PostgreSQL (Railway) / SQLite (local dev)

### Tables

| Table | Description |
|-------|-------------|
| `measurements` | CV pipeline results — per-finger widths, lengths, confidence, debug image path |
| `nail_sizes` | Product nail dimensions per size number (0-9), grouped by `chart_id` |
| `size_rules` | Width range → size mappings, per-finger or universal |
| `size_rules_config` | Global config: between-sizes preference, tolerance |
| `size_sets` | Pre-packaged size combinations linked to Shopify variants |
| `recommendations` | Size profiles linking measurements to Shopify customers |
| `admins` | Admin auth (bcrypt passwords) |

Key design decisions:
- **JSONB for per-finger data** — extensible without migrations
- **`chart_id` on sizes/rules/sets** — future multi-shape support (coffin, almond, etc.)
- **Separate `recommendations` table** — decouples CV output from business logic; supports auto-update when rules change
- **All measurement history preserved** — customer profile uses latest

Full schema: [DB-SCHEMA.md](DB-SCHEMA.md)

---

## API Design

### Public Endpoints (rate-limited, no auth)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/validate` | Quick image pre-check |
| `POST` | `/v1/measure` | Full measurement pipeline |
| `POST` | `/v1/measure/merge` | Combine thumb + four-finger results |
| `GET` | `/v1/measure/:id` | Retrieve measurement |
| `POST` | `/v1/recommend` | Measurement → size recommendation |

### Admin Endpoints (JWT auth)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/admin/auth/login` | Login → access + refresh tokens |
| `GET/POST/PUT/DELETE` | `/v1/admin/sizes` | Size chart CRUD |
| `POST` | `/v1/admin/sizes/import` | CSV bulk import |
| `GET/POST/PUT/DELETE` | `/v1/admin/rules` | Size mapping rules |
| `POST` | `/v1/admin/rules/preview` | Test rules against measurements |
| `GET/POST/PUT/DELETE` | `/v1/admin/sets` | Pre-packaged sets |
| `GET` | `/v1/admin/measurements` | Browse measurements |
| `GET` | `/v1/admin/measurements/stats` | Volume/accuracy stats |

### Shopify Endpoints (Phase 3, session token auth)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/shopify/save-profile` | Write size profile to customer metafields |
| `GET` | `/v1/shopify/customer-profile` | Read current customer's profile |

Full API spec: [API-DESIGN.md](API-DESIGN.md)

---

## Configuration & Calibration

All tunable CV parameters are documented in [CONFIGURATION.md](CONFIGURATION.md), including:

- Image preprocessing thresholds (blur, brightness)
- Card detection parameters (Canny thresholds, aspect tolerance, fallback strategies)
- Hand detection confidence levels
- Nail segmentation HSV ranges (skin tone detection)
- Curvature adjustment factors
- Debug visualization settings

### Calibration Workflow

1. Capture 20+ test photos (varied skin tones, lighting, card angles)
2. Run pipeline, collect blur/brightness/detection data
3. Adjust thresholds based on pass/fail analysis
4. Compare measurements to caliper ground truth
5. Run test suite to prevent regressions

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Two-photo flow** | Standard credit card (85.6 × 53.98mm) can't fit all 5 fingers simultaneously |
| **Railway for hosting** | Simple Postgres + container hosting, no serverless complexity |
| **Replicate for SAM 2** | ~$0.02/call, no GPU infrastructure needed |
| **MediaPipe on CPU** | Hand detection doesn't need GPU, runs fast on CPU |
| **Hybrid customer auth** | localStorage for guests, Shopify metafields when logged in |
| **`chart_id` for future shapes** | Sev may add coffin/almond/stiletto with different dimensions |
| **Classical CV card detection** | No ML needed — edge detection + contour filtering works well with fallbacks |
| **Mock segmentation mode** | Enables full test coverage without SAM 2 dependency |

---

## Timeline

| Phase | Scope | Effort | Status |
|-------|-------|--------|--------|
| Phase 1 | CV Pipeline (Python) | ~1 week | ✅ Complete (69 tests) |
| Phase 2 | Admin Panel (Next.js) | ~4 days | ✅ Complete |
| Phase 3 | Shopify Integration + UX | ~1.5 weeks | ⏳ Not started |

---

## Blockers (Human TODO)

> Full list: [HUMAN-TODO.md](HUMAN-TODO.md)

### Blocking Accuracy Validation (Priority 1)

- [ ] **Test photos** — 2 photos per hand (4 fingers + thumb on credit card), from ~12" above, good lighting
- [ ] **Ground truth measurements** — Each nail's width + length measured with ruler/calipers (±0.5mm)

### Blocking Phase 2 Configuration

- [ ] **Sev product info** — Number of sizes, width per size in mm, sold as sets vs individual, size up/down preference, nail shapes offered
- [ ] **Shopify admin access** — Collaborator invite or admin credentials
- [ ] **Design preferences** — Brand colors/style or "just make it clean"

### Blocking Phase 3

- [ ] **Shopify Partner account** — Needed for custom app creation
- [ ] **Theme info** — Which Shopify theme is Sev using?
- [ ] **Customer accounts** — Are they enabled on the store?

---

## Development

### Prerequisites

- Python 3.11+ (CV pipeline)
- Node.js 18+ (admin panel)
- PostgreSQL (or SQLite for local dev)

### Quick Start

```bash
# CV Pipeline
cd cv
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest --tb=short -q          # Run tests
uvicorn app:app --reload --port 8000    # Start server

# Admin Panel
cd admin
npm install
npm run dev                              # http://localhost:3000
```

---

## Design Docs

| Document | Description |
|----------|-------------|
| [DESIGN.md](DESIGN.md) | Architecture overview, CV pipeline detail, tech stack |
| [API-DESIGN.md](API-DESIGN.md) | Full API specification with request/response examples |
| [DB-SCHEMA.md](DB-SCHEMA.md) | PostgreSQL schema, ER diagram, design rationale |
| [CONFIGURATION.md](CONFIGURATION.md) | All tunable parameters + calibration guide |
| [PHASE1.md](PHASE1.md) | Phase 1 spec, task breakdown, testing strategy |
| [PHASE2.md](PHASE2.md) | Phase 2 spec, UI pages, task breakdown |
| [PHASE3.md](PHASE3.md) | Phase 3 spec, Shopify integration, customer UX flow |
| [HUMAN-TODO.md](HUMAN-TODO.md) | Items requiring human input (photos, product info, access) |
