# Phase 1: Image → Nail Sizes Backend

Feature-complete CV pipeline that takes a photo of a hand on a credit card and returns per-finger nail measurements.

## Architecture

```
Client → POST /measure (multipart image) → Hono API (CF Workers) → upload to R2
                                          → call Modal CV endpoint
                                          → return measurements + store in DB
```

### Tech Stack
- **API Gateway:** Hono on Cloudflare Workers
- **CV Pipeline:** Python FastAPI on Modal (serverless GPU)
- **Storage:** Cloudflare R2 (images), Turso/SQLite (measurements)
- **CV Libraries:** OpenCV, MediaPipe Hands, SAM 2 (via `segment-anything-2`)

## API Design

### `POST /api/v1/measure`

**Request:** `multipart/form-data`
- `image`: JPEG/PNG, max 10MB
- `hand`: `"left"` | `"right"` (optional, auto-detect)

**Response:**
```json
{
  "id": "msr_abc123",
  "hand": "right",
  "scale_px_per_mm": 12.4,
  "card_detected": true,
  "fingers": {
    "thumb":  { "width_mm": 16.2, "length_mm": 12.1, "curve_adj_width_mm": 17.8 },
    "index":  { "width_mm": 14.1, "length_mm": 11.3, "curve_adj_width_mm": 15.2 },
    "middle": { "width_mm": 14.8, "length_mm": 12.0, "curve_adj_width_mm": 16.0 },
    "ring":   { "width_mm": 13.2, "length_mm": 10.5, "curve_adj_width_mm": 14.2 },
    "pinky":  { "width_mm": 11.0, "length_mm":  8.8, "curve_adj_width_mm": 11.8 }
  },
  "debug_image_url": "https://r2.../debug/msr_abc123.jpg",
  "confidence": 0.92,
  "warnings": []
}
```

**Error responses:**
- `400` — no card detected, hand not visible, image too blurry
- `422` — invalid image format
- `500` — pipeline failure

### `GET /api/v1/measure/:id`

Retrieve a previous measurement by ID.

### `POST /api/v1/validate`

Quick pre-check (no full measurement):
- Card visible? Hand visible? Image quality OK?
- Returns pass/fail + guidance ("move hand closer", "reduce glare")

## CV Pipeline Detail

### 1. Image Preprocessing
```python
def preprocess(image: np.ndarray) -> np.ndarray:
    # Resize to max 2048px on longest side (preserve aspect)
    # Auto-orient from EXIF
    # Assess blur (Laplacian variance > 100 threshold)
    # Assess brightness (reject if mean < 40 or > 240)
```

### 2. Card Detection & Calibration
```python
def detect_card(image: np.ndarray) -> CardResult:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)
    contours = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Filter: area > 5% of image, approxPolyDP → 4 corners
    # Validate aspect ratio ≈ 1.586 (85.6 / 53.98) ± 0.1
    # Perspective transform → rectified card
    # px_per_mm = rectified_width_px / 85.6

    return CardResult(corners, px_per_mm, rectified)
```

**Fallback:** If classical detection fails, try adaptive thresholding + morphological closing. If still fails, return error with guidance.

### 3. Hand & Nail Detection
```python
def detect_nails(image: np.ndarray, px_per_mm: float) -> dict:
    # MediaPipe Hands → 21 landmarks
    hands = mp_hands.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

    # For each fingertip landmark (4, 8, 12, 16, 20):
    #   - Define ROI around fingertip
    #   - SAM 2 point prompt at fingertip → nail mask
    #   - Extract nail contour from mask

    # Per nail contour:
    #   - Width: distance between leftmost/rightmost at widest point near cuticle
    #   - Length: distance from cuticle line to free edge along nail center axis
    #   - Convert px → mm using px_per_mm
```

### 4. Curve Adjustment
```python
def adjust_curve(width_mm: float, finger_width_mm: float) -> float:
    ratio = width_mm / finger_width_mm
    if ratio < 0.70:
        factor = 1.05
    elif ratio < 0.85:
        factor = 1.12
    else:
        factor = 1.18
    return width_mm * factor
```

### 5. Debug Image Generation
Annotated image with:
- Card outline (green)
- Hand landmarks (blue dots)
- Nail masks (semi-transparent overlay)
- Measurement lines with mm labels

Stored to R2 at `debug/{measurement_id}.jpg`.

## Database Schema

```sql
CREATE TABLE measurements (
  id TEXT PRIMARY KEY,          -- msr_xxx
  image_key TEXT NOT NULL,      -- R2 object key
  debug_image_key TEXT,
  hand TEXT NOT NULL,           -- left/right
  scale_px_per_mm REAL,
  confidence REAL,
  thumb_w REAL, thumb_l REAL, thumb_cw REAL,
  index_w REAL, index_l REAL, index_cw REAL,
  middle_w REAL, middle_l REAL, middle_cw REAL,
  ring_w REAL, ring_l REAL, ring_cw REAL,
  pinky_w REAL, pinky_l REAL, pinky_cw REAL,
  warnings TEXT,                -- JSON array
  created_at TEXT DEFAULT (datetime('now')),
  metadata TEXT                 -- JSON blob for extensibility
);
```

## Directory Structure

```
sev-nail-sizer/
├── api/                        # Hono on CF Workers
│   ├── src/
│   │   ├── index.ts            # Router
│   │   ├── routes/measure.ts   # /measure, /measure/:id
│   │   ├── routes/validate.ts  # /validate
│   │   ├── lib/modal.ts        # Modal API client
│   │   ├── lib/r2.ts           # R2 upload/download
│   │   └── lib/db.ts           # Turso client
│   ├── wrangler.toml
│   └── package.json
├── cv/                         # Python CV pipeline on Modal
│   ├── app.py                  # Modal app + FastAPI endpoints
│   ├── pipeline/
│   │   ├── preprocess.py
│   │   ├── card_detect.py
│   │   ├── nail_detect.py
│   │   ├── measure.py
│   │   └── debug_viz.py
│   ├── models/                 # SAM 2 weights (downloaded at build)
│   └── requirements.txt
└── shared/                     # Shared types/schemas
    └── types.ts
```

## Testing Strategy

### Unit Tests
- Card detection on synthetic images (rotated, glare, partial occlusion)
- Measurement extraction on known-size test images
- Curve adjustment lookup table verification

### Integration Tests
- End-to-end: upload image → get measurements
- Known reference images with measured ground truth (print card + ruler photo)

### Accuracy Benchmarks
- Target: ±0.5mm on width, ±1mm on length
- Test set: 20+ hands photographed with caliper-measured nails
- Track regression across pipeline changes

## Error Handling

| Condition | Response |
|-----------|----------|
| No card detected | 400 + "Place card fully visible in frame" |
| Card too small (<10% of image) | 400 + "Move closer to the card" |
| No hand detected | 400 + "Place hand flat on card" |
| Fewer than 5 nails detected | Partial result + warning |
| Image blurry | 400 + "Hold camera steady, ensure good lighting" |
| Low confidence (<0.7) | Return result + warning flag |

## Task Breakdown

| # | Task | Effort |
|---|------|--------|
| 1 | Set up Modal project + FastAPI skeleton | 2h |
| 2 | Card detection (classical CV) | 4h |
| 3 | MediaPipe hand landmark detection | 2h |
| 4 | SAM 2 nail segmentation | 4h |
| 5 | Measurement extraction (width, length) | 4h |
| 6 | Curve adjustment (lookup table) | 1h |
| 7 | Debug image generation | 2h |
| 8 | Hono API gateway (CF Workers) | 3h |
| 9 | R2 upload/download integration | 2h |
| 10 | Database setup (Turso) + schema | 2h |
| 11 | Validation endpoint | 2h |
| 12 | Error handling + edge cases | 3h |
| 13 | Test suite + reference images | 4h |
| 14 | End-to-end integration testing | 3h |
| **Total** | | **~38h (~1 week)** |

## Open Questions
1. Should we support both hands in one photo, or require separate uploads?
   - *Rec: separate uploads for MVP, simplifies detection*
2. Minimum supported image resolution?
   - *Rec: 1080p minimum, reject below*
3. Do we need to handle acrylic/gel nails already on? (Different shape than natural)
   - *Rec: MVP assumes natural nails, add note in UX*
