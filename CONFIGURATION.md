# Sev Nail Sizer — Configuration & Calibration Guide

All tunable parameters in the CV pipeline, where they live, what they do, and how to calibrate them.

---

## 1. Image Preprocessing (`pipeline/preprocess.py`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `MAX_LONG_SIDE` | `2048` | Images larger than this (px) are downscaled, preserving aspect ratio. Larger = more detail but slower. |
| `BLUR_THRESHOLD` | `100.0` | Laplacian variance below this → image flagged as blurry (`is_sharp=False`). Higher = stricter. |
| `BRIGHTNESS_MIN` | `40.0` | Mean gray value below this → `"dark"`. |
| `BRIGHTNESS_MAX` | `240.0` | Mean gray value above this → `"bright"`. |

**Calibration:** Take 10-20 test photos at varying lighting. Run `preprocess()` and check `blur_score` and `brightness_mean`. Adjust thresholds so real-world "acceptable" images pass and genuinely bad ones don't.

---

## 2. Card Detection (`pipeline/card_detect.py`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `CARD_WIDTH_MM` | `85.6` | ISO 7810 credit card width in mm. **Do not change** unless using a different reference card. |
| `CARD_HEIGHT_MM` | `53.98` | ISO 7810 credit card height in mm. |
| `CARD_ASPECT_RATIO` | `≈1.5857` | Derived from width/height. Used to validate detected rectangles. |
| `ASPECT_TOLERANCE` | `0.15` | How far the detected rectangle's aspect ratio can differ from `CARD_ASPECT_RATIO`. Wider = more forgiving for angled/warped cards. |
| `MIN_CARD_AREA_FRACTION` | `0.05` | Card must occupy at least 5% of image area. Prevents detecting tiny rectangles. |
| Canny thresholds | `50, 150` | In `detect_card()` → `cv2.Canny(blurred, 50, 150)`. Lower threshold = more edges; higher = fewer. |
| GaussianBlur kernel | `(5, 5)` | Pre-Canny blur. Larger kernel = smoother edges, may lose thin card outlines. |
| Adaptive threshold block size | `11` | Block size for `cv2.adaptiveThreshold`. Must be odd. Larger = less sensitive to local contrast. |
| Adaptive threshold C | `2` | Constant subtracted from adaptive threshold mean. |
| Morphological kernel size | `(5, 5)` / `(7, 7)` | Closing/opening kernels for fallback methods. Larger = fills bigger gaps. |
| `approxPolyDP` epsilon multipliers | `0.02, 0.04, 0.06, 0.08` | Polygon approximation tolerance (fraction of perimeter). Tried in order; first 4-vertex match wins. |
| Rectangularity threshold | `0.7` | `contour_area / minAreaRect_area` must be ≥ 0.7. Filters out non-rectangular shapes. |
| Bright threshold values | `180, 160, 140` | Fallback binary thresholds for isolating bright card on dark backgrounds. |

**Calibration:** If cards aren't detected:
1. Lower `MIN_CARD_AREA_FRACTION` if card is far from camera
2. Widen `ASPECT_TOLERANCE` if cards appear warped
3. Adjust Canny thresholds (try `30, 100` for low-contrast scenes)

---

## 3. Hand Detection (`pipeline/hand_detect.py`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_detection_confidence` | `0.5` | MediaPipe Hands detection confidence threshold. Lower = detects more hands (with more false positives). |
| `max_num_hands` | `1` | Only detect one hand per image. |
| `static_image_mode` | `True` | Treats each image independently (no tracking). |
| Finger width heuristic factor | `0.6` | `_estimate_finger_widths`: width ≈ 60% of average distance to neighboring DIP joints. |
| `FINGERTIP_INDICES` | `[4, 8, 12, 16, 20]` | MediaPipe landmark indices for fingertips. **Do not change.** |
| `DIP_INDICES` | `[3, 7, 11, 15, 19]` | Distal interphalangeal joint indices. **Do not change.** |

**Calibration:** If hands aren't detected, lower `min_detection_confidence` to `0.3`. The `0.6` finger-width factor is an approximation; measure real fingers and adjust if consistently off.

---

## 4. Nail Segmentation (`pipeline/nail_segment.py`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `MOCK_NAIL_HALF_W` | `15` | Half-width (px) of synthetic ellipse in mock mode. |
| `MOCK_NAIL_HALF_H` | `22` | Half-height (px) of synthetic ellipse in mock mode. |
| `ROI_HALF_W_FRAC` | `0.05` | ROI width around fingertip as fraction of image width. |
| `ROI_HALF_H_FRAC` | `0.06` | ROI height around fingertip as fraction of image height. |
| `ROI_MIN_PX` | `20` | Minimum ROI half-size in pixels. |
| `ROI_MAX_PX` | `80` | Maximum ROI half-size in pixels. |

### HSV Skin Detection (`_skin_mask_hsv`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| Skin range 1 | H: 0–20, S: 15–170, V: 50–255 | Warm reds/oranges (most skin tones). |
| Skin range 2 | H: 160–180, S: 15–170, V: 50–255 | Wrap-around reds. |

### Nail Candidate Detection (`_nail_candidate_mask`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| Saturation threshold | `< 80` | Nail plates have lower saturation than surrounding skin. |
| Value threshold | `> 130` | Nail plates are lighter/brighter. |
| Skin dilation kernel | `(3, 3)`, 1 iteration | Slightly expand skin region before intersecting with nail candidates. |

### Connected Component Selection (`_largest_component_near_tip`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `radius_frac` | `0.8` | Component centroid must be within this fraction of ROI diagonal from fingertip. |
| Min pixel count | `20` | Components smaller than 20 pixels fall back to skin-only detection. |
| Fallback `radius_frac` | `0.6` | Used when falling back to skin mask. |
| Fallback confidence multiplier | `0.5` | Skin-only fallback gets halved confidence. |

**Calibration for diverse skin tones:**
- Expand HSV ranges for very dark or very light skin
- For painted nails: nail saturation threshold may need increasing (painted nails can be highly saturated)
- For very short nails: decrease `ROI_MIN_PX` or increase `ROI_HALF_H_FRAC`

---

## 5. Measurement (`pipeline/measure.py`)

No tunable constants — measurements are purely derived from mask geometry and `px_per_mm`:
- **Width** = widest horizontal span in mask / `px_per_mm`
- **Length** = top-to-bottom span in mask / `px_per_mm`

If measurements are consistently off, the issue is likely in `px_per_mm` (card detection) or mask quality (segmentation).

---

## 6. Curvature Adjustment (`pipeline/curve_adjust.py`)

| Nail-to-Finger Ratio | Factor | Description |
|-----------------------|--------|-------------|
| `< 0.70` | `1.05` | Narrow nail relative to finger — minimal curvature. |
| `0.70 – 0.85` | `1.12` | Medium curvature. |
| `≥ 0.85` | `1.18` | Wide nail — significant curvature compensation. |

**Calibration:** These factors approximate the 2D→3D arc adjustment. To calibrate:
1. Measure real nails with calipers (true 3D width)
2. Compare to pipeline's flat `width_mm`
3. Adjust factors so `width_mm × factor ≈ caliper measurement`

---

## 7. Debug Visualization (`pipeline/debug_viz.py`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| Overlay alpha | `0.4` (overlay) / `0.6` (base) | Nail mask transparency. |
| Colors | Green=card, Blue=landmarks, Red=tips, Pink=masks, Yellow=measurements | |
| Font scale | `0.55` (card), `0.4` (finger labels), `0.35` (measurements) | |

Purely cosmetic — adjust for readability.

---

## 8. Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SEV_MOCK_SEGMENTATION` | unset | Set to `"1"` to use synthetic ellipse masks instead of OpenCV/SAM. |
| `SEV_USE_REPLICATE` | unset | Set to `"1"` + provide `REPLICATE_API_TOKEN` to use SAM 2 cloud segmentation. |
| `REPLICATE_API_TOKEN` | unset | API key for Replicate (SAM 2). |
| `SEV_DB_PATH` | `./sev_nails.db` | SQLite database path. |
| `SEV_IMAGE_DIR` | `./debug_images/` | Directory for saved debug images. |
| `SEV_PERSIST` | `"1"` | Set to `"0"` to disable SQLite + filesystem persistence. |

---

## Recommended Calibration Workflow

### Step 1: Capture Test Photos
Take 20+ photos covering:
- Different skin tones (light, medium, dark)
- Various lighting (natural daylight, fluorescent, dim)
- Card angles (flat, 10°, 20° tilt)
- Nail types (natural, painted, short, long)

### Step 2: Run Pipeline & Collect Data
```bash
cd cv
for img in test_photos/*.jpg; do
  .venv/bin/python -c "
from pipeline.preprocess import preprocess
from pipeline.card_detect import detect_card
img_bytes = open('$img', 'rb').read()
bgr, q = preprocess(img_bytes)
card = detect_card(bgr)
print(f'$img: blur={q.blur_score:.1f} bright={q.brightness_mean:.1f} card={card is not None}')
if card: print(f'  px_per_mm={card.px_per_mm:.2f} conf={card.confidence:.2f}')
"
done
```

### Step 3: Compare & Adjust
1. **Blur threshold**: If good photos fail → lower `BLUR_THRESHOLD`
2. **Brightness bounds**: If well-lit photos flag as dark/bright → widen range
3. **Card detection**: If cards missed → widen `ASPECT_TOLERANCE`, lower `MIN_CARD_AREA_FRACTION`
4. **Skin detection**: If segmentation misses nails → expand HSV ranges
5. **Curvature factors**: Compare to caliper measurements → adjust factors

### Step 4: Validate
Run the test suite to ensure changes don't break anything:
```bash
cd cv && .venv/bin/python -m pytest --tb=short -q
```
