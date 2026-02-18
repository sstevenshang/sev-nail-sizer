"""End-to-end pipeline test using a synthetic image.

The synthetic image contains:
  - A dark background
  - A credit-card-proportioned white rectangle (for detect_card)
  - Five skin-toned finger shapes extending above the card (for visual realism)

Because MediaPipe requires a real photograph to detect hand landmarks reliably,
hand detection is injected via monkeypatch.  All other pipeline stages
(preprocess, card_detect, nail_segment, measure, curve_adjust, debug_viz) run
on real synthetic data — giving us true end-to-end coverage without network
calls or API keys.
"""

from __future__ import annotations

import io
import sys
import os

import cv2
import numpy as np
import pytest
from PIL import Image

# Ensure we can import pipeline modules regardless of working directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Synthetic image builder
# ---------------------------------------------------------------------------

CARD_ASPECT = 85.6 / 53.98   # ≈ 1.5857
IMG_W, IMG_H = 900, 700


def _make_synthetic_hand_card_image() -> np.ndarray:
    """
    Draw a synthetic scene:
      • Dark grey background (30, 30, 30)
      • White credit-card rectangle in the lower portion (clear of fingers)
      • Five skin-toned finger columns in the upper portion

    The card and finger regions are separated to ensure the card's rectangular
    outline produces a clean 4-vertex contour for detect_card.
    """
    img = np.full((IMG_H, IMG_W, 3), 30, dtype=np.uint8)

    # --- Credit card (lower portion, clear of fingers) ---
    card_w = 540
    card_h = int(round(card_w / CARD_ASPECT))   # ≈ 340
    cx = IMG_W // 2
    # Place card in lower 60% of image, well away from finger tips
    card_x1 = cx - card_w // 2
    card_y1 = 320
    card_x2 = card_x1 + card_w
    card_y2 = card_y1 + card_h

    # Fill card white, then draw thick dark border for strong edge detection
    cv2.rectangle(img, (card_x1, card_y1), (card_x2, card_y2), (220, 220, 220), -1)
    cv2.rectangle(img, (card_x1, card_y1), (card_x2, card_y2), (60, 60, 60), 3)

    # --- Fingers in upper portion (well above card_y1) ---
    skin_color_bgr = (100, 150, 200)   # BGR medium skin tone
    nail_color_bgr = (190, 205, 225)   # lighter for nail plate

    # Fingertip y-positions well above the card top
    tip_ys = [160, 120, 100, 115, 145]  # thumb..pinky (middle finger tallest)
    tip_xs = [
        card_x1 + int(card_w * 0.15),   # thumb
        card_x1 + int(card_w * 0.30),   # index
        card_x1 + int(card_w * 0.47),   # middle
        card_x1 + int(card_w * 0.64),   # ring
        card_x1 + int(card_w * 0.80),   # pinky
    ]
    finger_half_ws = [22, 18, 20, 17, 14]
    finger_half_hs = [80, 100, 115, 100, 80]

    for tx, ty, fw, fh in zip(tip_xs, tip_ys, finger_half_ws, finger_half_hs):
        # Finger body: tall ellipse, tip at (tx, ty)
        body_cy = ty + fh
        cv2.ellipse(img, (tx, body_cy), (fw, fh), 0, 0, 360, skin_color_bgr, -1)
        # Nail plate: small ellipse right at the fingertip
        cv2.ellipse(img, (tx, ty + fw - 2), (fw - 5, fw - 3), 0, 0, 360, nail_color_bgr, -1)

    return img


def _bgr_to_jpeg_bytes(img: np.ndarray, quality: int = 95) -> bytes:
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def synthetic_image() -> np.ndarray:
    return _make_synthetic_hand_card_image()


@pytest.fixture(scope="module")
def synthetic_image_bytes(synthetic_image) -> bytes:
    return _bgr_to_jpeg_bytes(synthetic_image)


@pytest.fixture
def mock_hand_result_e2e(synthetic_image):
    """Hand result with fingertip positions matching the synthetic image."""
    from pipeline.hand_detect import HandResult

    card_w = 540
    cx = IMG_W // 2
    card_x1 = cx - card_w // 2

    # Must match _make_synthetic_hand_card_image fingertip positions
    tip_ys = [160, 120, 100, 115, 145]
    tip_xs = [
        card_x1 + int(card_w * 0.15),
        card_x1 + int(card_w * 0.30),
        card_x1 + int(card_w * 0.47),
        card_x1 + int(card_w * 0.64),
        card_x1 + int(card_w * 0.80),
    ]
    finger_names = ["thumb", "index", "middle", "ring", "pinky"]
    tips = {name: (tx, ty) for name, tx, ty in zip(finger_names, tip_xs, tip_ys)}

    # 21 landmarks: spread evenly (palm region)
    palm_cx, palm_cy = cx, 450
    landmarks = [(palm_cx, palm_cy)] * 21
    return HandResult(
        landmarks=landmarks,
        handedness="right",
        fingertip_positions=tips,
        finger_widths_px={name: 40.0 for name in finger_names},
    )


# ---------------------------------------------------------------------------
# Preprocess stage
# ---------------------------------------------------------------------------

class TestPreprocessStage:
    def test_preprocess_returns_bgr_array(self, synthetic_image_bytes):
        from pipeline.preprocess import preprocess

        img, quality = preprocess(synthetic_image_bytes)
        assert img.ndim == 3
        assert img.shape[2] == 3
        assert img.dtype == np.uint8

    def test_preprocess_quality_is_sharp(self, synthetic_image_bytes):
        from pipeline.preprocess import preprocess

        _, quality = preprocess(synthetic_image_bytes)
        assert quality.is_sharp

    def test_preprocess_brightness_normal(self, synthetic_image_bytes):
        from pipeline.preprocess import preprocess

        _, quality = preprocess(synthetic_image_bytes)
        # A mixed dark-bg + light card image should land in "normal" range
        assert quality.brightness_level in ("normal", "dark")


# ---------------------------------------------------------------------------
# Card detect stage
# ---------------------------------------------------------------------------

class TestCardDetectStage:
    def test_card_detected(self, synthetic_image):
        from pipeline.card_detect import detect_card

        result = detect_card(synthetic_image)
        assert result is not None, "detect_card should find the synthetic card"

    def test_card_px_per_mm_reasonable(self, synthetic_image):
        from pipeline.card_detect import detect_card

        result = detect_card(synthetic_image)
        assert result is not None
        # card_w=540px / 85.6mm ≈ 6.31; allow ±30%
        assert 3.0 < result.px_per_mm < 12.0

    def test_card_corners_shape(self, synthetic_image):
        from pipeline.card_detect import detect_card

        result = detect_card(synthetic_image)
        assert result is not None
        assert result.corners.shape == (4, 2)

    def test_card_confidence_positive(self, synthetic_image):
        from pipeline.card_detect import detect_card

        result = detect_card(synthetic_image)
        assert result is not None
        assert result.confidence > 0


# ---------------------------------------------------------------------------
# Nail segment stage (OpenCV HSV fallback)
# ---------------------------------------------------------------------------

class TestNailSegmentStage:
    def test_opencv_segment_returns_five_masks(self, synthetic_image, mock_hand_result_e2e):
        """OpenCV HSV segmentation should return one mask per finger."""
        from pipeline.nail_segment import _opencv_segment

        masks = _opencv_segment(synthetic_image, mock_hand_result_e2e.fingertip_positions)
        assert len(masks) == 5

    def test_opencv_segment_finger_names_correct(self, synthetic_image, mock_hand_result_e2e):
        from pipeline.nail_segment import _opencv_segment

        masks = _opencv_segment(synthetic_image, mock_hand_result_e2e.fingertip_positions)
        names = {m.finger for m in masks}
        assert names == {"thumb", "index", "middle", "ring", "pinky"}

    def test_opencv_segment_masks_are_boolean(self, synthetic_image, mock_hand_result_e2e):
        from pipeline.nail_segment import _opencv_segment

        masks = _opencv_segment(synthetic_image, mock_hand_result_e2e.fingertip_positions)
        for m in masks:
            assert m.mask.dtype == bool
            assert m.mask.shape == synthetic_image.shape[:2]

    def test_opencv_segment_confidence_in_range(self, synthetic_image, mock_hand_result_e2e):
        from pipeline.nail_segment import _opencv_segment

        masks = _opencv_segment(synthetic_image, mock_hand_result_e2e.fingertip_positions)
        for m in masks:
            assert 0.0 <= m.confidence <= 1.0

    def test_mock_segment_returns_non_empty_masks(self, synthetic_image, mock_hand_result_e2e):
        """Mock (ellipse) segmentation should always produce non-empty masks."""
        from pipeline.nail_segment import _mock_masks

        masks = _mock_masks(synthetic_image, mock_hand_result_e2e.fingertip_positions)
        assert len(masks) == 5
        for m in masks:
            assert m.mask.any(), f"Mask for {m.finger} should not be empty"


# ---------------------------------------------------------------------------
# Measure stage
# ---------------------------------------------------------------------------

class TestMeasureStage:
    def test_measure_all_with_mock_masks(self, synthetic_image, mock_hand_result_e2e):
        from pipeline.nail_segment import _mock_masks
        from pipeline.measure import measure_all_nails

        masks = _mock_masks(synthetic_image, mock_hand_result_e2e.fingertip_positions)
        px_per_mm = 540 / 85.6  # ≈ 6.31
        measurements = measure_all_nails(masks, px_per_mm)

        assert len(measurements) == 5
        for finger, meas in measurements.items():
            assert meas.width_mm > 0, f"{finger} width should be > 0"
            assert meas.length_mm > 0, f"{finger} length should be > 0"

    def test_measure_width_in_realistic_range(self, synthetic_image, mock_hand_result_e2e):
        """Mock nail half-width=15px → width ≈ 30px / 6.31px_per_mm ≈ 4.75mm."""
        from pipeline.nail_segment import _mock_masks
        from pipeline.measure import measure_all_nails

        masks = _mock_masks(synthetic_image, mock_hand_result_e2e.fingertip_positions)
        px_per_mm = 540 / 85.6
        measurements = measure_all_nails(masks, px_per_mm)

        for finger, meas in measurements.items():
            # Human nail widths: 8–18mm; mock is small but should be > 0
            assert 0.5 < meas.width_mm < 30.0, f"{finger} width {meas.width_mm} out of range"


# ---------------------------------------------------------------------------
# Curve adjust stage
# ---------------------------------------------------------------------------

class TestCurveAdjustStage:
    def test_curve_adjust_increases_width(self, synthetic_image, mock_hand_result_e2e):
        from pipeline.nail_segment import _mock_masks
        from pipeline.measure import measure_all_nails
        from pipeline.curve_adjust import adjust_curve

        masks = _mock_masks(synthetic_image, mock_hand_result_e2e.fingertip_positions)
        px_per_mm = 540 / 85.6
        measurements = measure_all_nails(masks, px_per_mm)

        for finger, meas in measurements.items():
            finger_width_px = mock_hand_result_e2e.finger_widths_px[finger]
            adjusted = adjust_curve(meas, finger_width_px, px_per_mm)
            assert adjusted >= meas.width_mm, (
                f"{finger}: curve_adj {adjusted} should be >= raw {meas.width_mm}"
            )


# ---------------------------------------------------------------------------
# Debug viz stage
# ---------------------------------------------------------------------------

class TestDebugVizStage:
    def test_debug_image_same_shape(self, synthetic_image, mock_hand_result_e2e):
        from pipeline.nail_segment import _mock_masks
        from pipeline.measure import measure_all_nails
        from pipeline.card_detect import detect_card
        from pipeline.debug_viz import draw_debug_image

        card_result = detect_card(synthetic_image)
        assert card_result is not None

        masks = _mock_masks(synthetic_image, mock_hand_result_e2e.fingertip_positions)
        measurements = measure_all_nails(masks, card_result.px_per_mm)

        debug = draw_debug_image(
            synthetic_image,
            card_result=card_result,
            hand_result=mock_hand_result_e2e,
            nail_masks=masks,
            measurements=measurements,
        )
        assert debug.shape == synthetic_image.shape

    def test_debug_image_is_modified(self, synthetic_image, mock_hand_result_e2e):
        """Debug image should differ from the input (annotations drawn)."""
        from pipeline.nail_segment import _mock_masks
        from pipeline.measure import measure_all_nails
        from pipeline.card_detect import detect_card
        from pipeline.debug_viz import draw_debug_image

        card_result = detect_card(synthetic_image)
        assert card_result is not None

        masks = _mock_masks(synthetic_image, mock_hand_result_e2e.fingertip_positions)
        measurements = measure_all_nails(masks, card_result.px_per_mm)

        debug = draw_debug_image(
            synthetic_image,
            card_result=card_result,
            hand_result=mock_hand_result_e2e,
            nail_masks=masks,
            measurements=measurements,
        )
        assert not np.array_equal(debug, synthetic_image)


# ---------------------------------------------------------------------------
# Full end-to-end pipeline
# ---------------------------------------------------------------------------

class TestFullPipeline:
    def test_full_pipeline_with_mock_hand(self, synthetic_image_bytes, mock_hand_result_e2e, monkeypatch):
        """
        Run the complete pipeline on a synthetic image:
          preprocess → card_detect → (mock) hand_detect → nail_segment (OpenCV)
          → measure → curve_adjust → debug_viz

        Hand detection is mocked since MediaPipe needs a real photo.
        """
        import app as app_mod
        from pipeline.hand_detect import HandResult

        monkeypatch.setattr(
            app_mod, "detect_hand",
            lambda img, hands_model=None: mock_hand_result_e2e
        )
        # Use OpenCV segmentation (not mock ellipses) — unset the mock env var
        monkeypatch.delenv("SEV_MOCK_SEGMENTATION", raising=False)

        from fastapi.testclient import TestClient
        client = TestClient(app_mod.app)

        resp = client.post(
            "/pipeline/measure",
            files={"image": ("synthetic.jpg", synthetic_image_bytes, "image/jpeg")},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        # Check top-level keys
        assert data["id"].startswith("msr_")
        assert data["hand"] in ("left", "right")
        assert data["scale_px_per_mm"] > 0
        assert data["card_detected"] is True
        assert "fingers" in data
        assert "overall_confidence" in data
        assert "debug_image_b64" in data
        assert isinstance(data["warnings"], list)

    def test_full_pipeline_returns_finger_measurements(self, synthetic_image_bytes, mock_hand_result_e2e, monkeypatch):
        """At least some fingers should have valid measurements."""
        import app as app_mod

        monkeypatch.setattr(
            app_mod, "detect_hand",
            lambda img, hands_model=None: mock_hand_result_e2e
        )
        monkeypatch.delenv("SEV_MOCK_SEGMENTATION", raising=False)

        from fastapi.testclient import TestClient
        client = TestClient(app_mod.app)

        resp = client.post(
            "/pipeline/measure",
            files={"image": ("synthetic.jpg", synthetic_image_bytes, "image/jpeg")},
        )
        assert resp.status_code == 200
        fingers = resp.json()["fingers"]
        assert len(fingers) > 0

        for name, data in fingers.items():
            assert data["width_mm"] > 0
            assert data["length_mm"] > 0
            assert data["curve_adj_width_mm"] >= data["width_mm"]
            assert 0 <= data["confidence"] <= 1

    def test_validate_endpoint_with_synthetic_image(self, synthetic_image_bytes, mock_hand_result_e2e, monkeypatch):
        """Validate endpoint should succeed with mocked card+hand."""
        import app as app_mod
        from pipeline.card_detect import CardResult

        card_w = 540
        mock_card = CardResult(
            corners=np.array(
                [[180, 190], [720, 190], [720, 510], [180, 510]], dtype=np.float32
            ),
            px_per_mm=card_w / 85.6,
            rectified=np.zeros((320, card_w, 3), dtype=np.uint8),
            confidence=0.95,
        )

        monkeypatch.setattr(app_mod, "detect_card", lambda img: mock_card)
        monkeypatch.setattr(
            app_mod, "detect_hand",
            lambda img, hands_model=None: mock_hand_result_e2e
        )

        from fastapi.testclient import TestClient
        client = TestClient(app_mod.app)

        resp = client.post(
            "/pipeline/validate",
            files={"image": ("synthetic.jpg", synthetic_image_bytes, "image/jpeg")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["checks"]["card_detected"] is True
        assert data["checks"]["hand_detected"] is True
        assert data["valid"] is True

    def test_pipeline_with_mock_segmentation_mode(self, synthetic_image_bytes, mock_hand_result_e2e, monkeypatch):
        """Smoke test: full pipeline using the ellipse-mock segmentation."""
        import app as app_mod

        monkeypatch.setattr(
            app_mod, "detect_hand",
            lambda img, hands_model=None: mock_hand_result_e2e
        )
        monkeypatch.setenv("SEV_MOCK_SEGMENTATION", "1")

        from fastapi.testclient import TestClient
        client = TestClient(app_mod.app)

        resp = client.post(
            "/pipeline/measure",
            files={"image": ("synthetic.jpg", synthetic_image_bytes, "image/jpeg")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["fingers"]) == 5
        for name, f in data["fingers"].items():
            assert f["width_mm"] > 0
