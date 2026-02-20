# Sev Nail Sizer — Architecture & Design

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                              │
│  Next.js app (embedded in Shopify via App Bridge)            │
│  + React Native (Expo) for P1 mobile app                     │
├─────────────────────────────────────────────────────────────┤
│                        Backend API                           │
│  Node.js (Hono on Cloudflare Workers)                        │
│  - /upload → presigned URL                                   │
│  - /measure → triggers CV pipeline                           │
│  - /sizes → returns size recommendations                     │
│  - /tryon → returns visualization                            │
├─────────────────────────────────────────────────────────────┤
│                     CV/ML Pipeline                            │
│  Python service (FastAPI on Modal or Replicate)              │
│  - Card detection → homography → scale calibration           │
│  - Nail segmentation → measurement extraction                │
│  - Curve adjustment model                                    │
├─────────────────────────────────────────────────────────────┤
│                       Storage                                │
│  - Cloudflare R2: raw photos + processed images              │
│  - Planetscale (MySQL): user profiles, measurements          │
│  - Shopify metafields: per-customer nail sizes               │
└─────────────────────────────────────────────────────────────┘
```

## CV/ML Pipeline

### Two-Photo Requirement

A standard credit card (85.6 × 53.98mm) is too small to fit all 5 fingers simultaneously. Users take **two photos**:

1. **Four-finger photo:** Index, middle, ring, pinky placed flat on the card
2. **Thumb photo:** Thumb placed flat on the card

Both photos use the same card for scale calibration. The pipeline processes each independently, then merges results into one complete measurement.

### Step 1: Card Detection & Scale Calibration

Classical CV — no ML needed:

1. Grayscale → Gaussian blur → Canny edge detection → find contours → filter rectangles with ~1.586 aspect ratio (85.6mm / 53.98mm)
2. Perspective transform (homography) to rectify the card
3. Compute **pixels-per-mm**: `card_width_pixels / 85.6mm`

Edge cases: card partially occluded (require corners visible via UI guidance), glare (adaptive thresholding), extreme angles (reject if reprojection error > threshold).

### Step 2: Hand & Nail Detection

1. **MediaPipe Hands** → 21 landmarks per hand, fingertip positions
2. **Nail segmentation:** SAM 2 with point prompts at fingertip landmarks (zero-shot — no training data needed for MVP). Fine-tune U-Net later with ~500 annotated images.
3. Per nail: extract width (widest horizontal at cuticle line) and length (cuticle to free edge along center axis)
4. **Photo type detection:** Auto-detect whether photo contains thumb-only or four-fingers based on detected landmark count and positions

### Step 3: Curve Adjustment

Nails are approximately cylindrical. MVP uses lookup table:

- Narrow nail (< 70% finger width) → ~5% width addition
- Medium (70-85%) → ~10-15% addition
- Wide (>85%) → ~15-20% addition

Math: Given flat width `w` and estimated C-curve radius `r`, arc length = `2r * arcsin(w / 2r)`

v2: Train regression model on 3D nail scan data predicting C-curve % from 2D features.

### Pipeline Output

Each `/measure` call returns partial results (thumb-only or four-finger). The `/measure/merge` endpoint combines two measurements into a complete profile:

```json
{
  "hand": "right",
  "photo_type": "four_finger",
  "scale_factor_px_per_mm": 12.4,
  "fingers": {
    "index":  { "width_mm": 14.1, "length_mm": 11.3, "curve_adjusted_width_mm": 15.2, "recommended_size": "5" },
    "middle": { "width_mm": 14.8, "length_mm": 12.0, "curve_adjusted_width_mm": 16.0, "recommended_size": "4" },
    "ring":   { "width_mm": 13.2, "length_mm": 10.5, "curve_adjusted_width_mm": 14.2, "recommended_size": "6" },
    "pinky":  { "width_mm": 11.0, "length_mm":  8.8, "curve_adjusted_width_mm": 11.8, "recommended_size": "8" }
  },
  "confidence": 0.92
}
```

After merging both photos:
```json
{
  "hand": "right",
  "complete": true,
  "fingers": {
    "thumb":  { "width_mm": 16.2, "length_mm": 12.1, "curve_adjusted_width_mm": 17.8, "recommended_size": "3", "source_measurement": "msr_abc123" },
    "index":  { "width_mm": 14.1, "length_mm": 11.3, "curve_adjusted_width_mm": 15.2, "recommended_size": "5", "source_measurement": "msr_def456" },
    "middle": { "width_mm": 14.8, "length_mm": 12.0, "curve_adjusted_width_mm": 16.0, "recommended_size": "4", "source_measurement": "msr_def456" },
    "ring":   { "width_mm": 13.2, "length_mm": 10.5, "curve_adjusted_width_mm": 14.2, "recommended_size": "6", "source_measurement": "msr_def456" },
    "pinky":  { "width_mm": 11.0, "length_mm":  8.8, "curve_adjusted_width_mm": 11.8, "recommended_size": "8", "source_measurement": "msr_def456" }
  },
  "confidence": 0.92
}
```

## Size Mapping

Need to physically measure every clip-on nail size Sev sells (typically sizes 0-9). Map curve-adjusted width to nearest size, round down (snug > loose for press-ons). Store as size profile: e.g., `3-5-4-6-8`.

## Try-On Visualization

### MVP: 2D Overlay (server-side)

1. Use nail masks + landmarks from CV pipeline
2. Warp product nail images (top-down photography) to match detected nail shape
3. Blend with `cv2.seamlessClone` (Poisson editing)
4. Apply lighting/color correction

### P1 Mobile: Real-Time AR

- iOS: ARKit + RealityKit hand tracking (iOS 17+)
- Cross-platform: Expo + VisionCamera frame processor

## Shopify Integration

**Pattern:** Shopify Custom App with App Bridge + App Proxy

- **App Proxy:** `sev.myshopify.com/apps/nail-sizer` → Next.js frontend (lives inside storefront)
- **Customer Metafields:** `sev_nails.size_profile`, `sev_nails.measurements`, `sev_nails.measured_at`
- **Product Pages:** Theme app extension injects size banner from metafields
- **Auth:** Shopify Customer Account API — no separate auth needed

## Tech Stack

| Component | Tech | Why |
|-----------|------|-----|
| Frontend (web) | Next.js 15 + Tailwind + shadcn/ui | Shopify App Bridge compatible |
| Frontend (mobile, P1) | React Native (Expo) | Share business logic with web |
| Backend API | Hono on Cloudflare Workers | Edge-deployed, fast, cheap |
| CV Pipeline | Python FastAPI on Modal | Serverless GPU, pay-per-inference |
| CV Libraries | OpenCV, MediaPipe, SAM 2 | Battle-tested, zero-shot segmentation |
| Database | PlanetScale (MySQL) | Serverless MySQL, edge-friendly |
| Object Storage | Cloudflare R2 | S3-compatible, no egress fees |
| Shopify | App Bridge, Admin API, Storefront API | Standard app pattern |

## MVP Scope (~4-6 weeks)

1. Guided photo upload UX (overlay showing hand + card placement)
2. Card detection + scale calibration (classical CV)
3. Nail detection via SAM 2 (zero-shot, no training)
4. Measurement extraction with lookup-table curve adjustment
5. Size mapping to Sev's product sizes
6. Shopify integration (metafields + product page display)
7. Profile persistence (measure once)

## v2
- Try-on visualization (2D composite)
- Both-hands support
- Trained curve-adjustment model
- Feedback loop for size refinement

## v3 (Mobile App)
- React Native app with camera guidance
- AR try-on
- On-device inference (ONNX Runtime)

## Open Questions for Sev

1. Exact dimensions of each nail size (measure with calipers)
2. Pre-packaged sets vs custom size selection?
3. Product photography available for try-on?
4. Customer accounts enabled in Shopify?
5. Between-sizes tolerance — size up or down?
