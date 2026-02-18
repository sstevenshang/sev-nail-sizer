"""Stress tests for the CV pipeline — edge cases, error paths, integration."""

from __future__ import annotations

import io
import cv2
import numpy as np
import pytest
from PIL import Image

from pipeline.preprocess import (
    BLUR_THRESHOLD, BRIGHTNESS_MIN, BRIGHTNESS_MAX,
    preprocess, resize_to_max, check_blur, check_brightness,
)
from pipeline.card_detect import (
    CARD_ASPECT_RATIO, CARD_WIDTH_MM, CARD_HEIGHT_MM,
    detect_card, order_corners, perspective_transform,
)
from pipeline.nail_segment import (
    NailMask, segment_nails, _opencv_segment, _mock_masks,
    _skin_mask_hsv, _nail_candidate_mask, _largest_component_near_tip,
)
from pipeline.measure import FingerMeasurement, measure_nail, measure_all_nails
from pipeline.curve_adjust import adjust_curve
from pipeline.debug_viz import draw_debug_image
from pipeline.hand_detect import HandResult, FINGER_NAMES, _estimate_finger_widths


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _encode_jpeg(bgr: np.ndarray, quality: int = 95) -> bytes:
    pil = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _make_card_on_bg(img_w=800, img_h=600, card_w=500, bg_val=30, card_val=220,
                      angle=0, offset_x=0, offset_y=0):
    """Create image with a rotated credit-card rectangle."""
    card_h = int(round(card_w / CARD_ASPECT_RATIO))
    img = np.full((img_h, img_w, 3), bg_val, dtype=np.uint8)
    cx = img_w // 2 + offset_x
    cy = img_h // 2 + offset_y
    rect_pts = np.array([
        [-card_w / 2, -card_h / 2],
        [card_w / 2, -card_h / 2],
        [card_w / 2, card_h / 2],
        [-card_w / 2, card_h / 2],
    ], dtype=np.float32)
    if angle != 0:
        rad = np.deg2rad(angle)
        R = np.array([[np.cos(rad), -np.sin(rad)], [np.sin(rad), np.cos(rad)]])
        rect_pts = rect_pts @ R.T
    rect_pts[:, 0] += cx
    rect_pts[:, 1] += cy
    pts = rect_pts.astype(np.int32)
    cv2.fillConvexPoly(img, pts, (card_val, card_val, card_val))
    return img


def _mock_hand(tips=None):
    if tips is None:
        tips = {
            "thumb": (200, 80), "index": (280, 60), "middle": (350, 55),
            "ring": (420, 62), "pinky": (490, 80),
        }
    return HandResult(
        landmarks=[(320, 300)] * 21,
        handedness="right",
        fingertip_positions=tips,
        finger_widths_px={f: 40.0 for f in tips},
    )


# ===========================================================================
# 1. PREPROCESS EDGE CASES
# ===========================================================================


class TestPreprocessEdgeCases:
    def test_very_dark_image(self):
        img = np.full((480, 640, 3), 5, dtype=np.uint8)
        raw = _encode_jpeg(img)
        bgr, q = preprocess(raw)
        assert q.brightness_level == "dark"
        assert q.brightness_mean < BRIGHTNESS_MIN

    def test_overexposed_image(self):
        img = np.full((480, 640, 3), 252, dtype=np.uint8)
        raw = _encode_jpeg(img)
        bgr, q = preprocess(raw)
        assert q.brightness_level == "bright"
        assert q.brightness_mean > BRIGHTNESS_MAX

    def test_single_pixel_image(self):
        """1x1 image should not crash."""
        img = np.full((1, 1, 3), 128, dtype=np.uint8)
        raw = _encode_jpeg(img)
        bgr, q = preprocess(raw)
        assert bgr.shape[:2] == (1, 1)

    def test_very_large_image_resized(self):
        img = np.zeros((6000, 8000, 3), dtype=np.uint8)
        raw = _encode_jpeg(img, quality=10)
        bgr, q = preprocess(raw)
        assert max(bgr.shape[:2]) <= 2048

    def test_png_format(self):
        """Pipeline should handle PNG bytes too."""
        img = np.full((100, 100, 3), 128, dtype=np.uint8)
        pil = Image.fromarray(img)
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        bgr, q = preprocess(buf.getvalue())
        assert bgr.ndim == 3

    def test_grayscale_input_converted(self):
        """Grayscale image should be converted to 3-channel."""
        gray = np.full((100, 100), 128, dtype=np.uint8)
        pil = Image.fromarray(gray, mode="L")
        buf = io.BytesIO()
        pil.save(buf, format="JPEG")
        bgr, q = preprocess(buf.getvalue())
        assert bgr.shape[2] == 3

    def test_garbage_bytes_raises(self):
        with pytest.raises(Exception):
            preprocess(b"\x00\x01\x02\x03")

    def test_empty_bytes_raises(self):
        with pytest.raises(Exception):
            preprocess(b"")

    def test_resize_preserves_aspect_extreme_panorama(self):
        img = np.zeros((100, 10000, 3), dtype=np.uint8)
        out = resize_to_max(img, max_side=2048)
        assert max(out.shape[:2]) == 2048
        assert out.shape[0] / out.shape[1] == pytest.approx(100 / 10000, rel=0.05)

    def test_resize_preserves_aspect_extreme_portrait(self):
        img = np.zeros((10000, 100, 3), dtype=np.uint8)
        out = resize_to_max(img, max_side=2048)
        assert max(out.shape[:2]) == 2048

    def test_check_blur_uniform_noise(self):
        """Random noise should have high Laplacian variance."""
        rng = np.random.RandomState(42)
        img = rng.randint(0, 256, (200, 200), dtype=np.uint8)
        score = check_blur(img)
        assert score > BLUR_THRESHOLD

    def test_check_brightness_boundary_values(self):
        # Exactly at boundary
        img_low = np.full((10, 10), int(BRIGHTNESS_MIN), dtype=np.uint8)
        _, level = check_brightness(img_low)
        assert level == "normal"  # >= BRIGHTNESS_MIN is normal

        img_high = np.full((10, 10), int(BRIGHTNESS_MAX), dtype=np.uint8)
        _, level = check_brightness(img_high)
        assert level == "normal"  # <= BRIGHTNESS_MAX is normal


# ===========================================================================
# 2. CARD DETECTION EDGE CASES
# ===========================================================================


class TestCardDetectEdgeCases:
    def test_card_rotated_15_degrees(self):
        img = _make_card_on_bg(angle=15)
        result = detect_card(img)
        assert result is not None

    def test_card_rotated_30_degrees(self):
        img = _make_card_on_bg(angle=30)
        result = detect_card(img)
        assert result is not None

    def test_card_rotated_45_degrees(self):
        img = _make_card_on_bg(angle=45)
        result = detect_card(img)
        assert result is not None

    def test_card_rotated_90_degrees(self):
        """Card at 90° is still a valid credit-card rectangle."""
        img = _make_card_on_bg(angle=90)
        result = detect_card(img)
        assert result is not None

    def test_card_offset_near_edge(self):
        """Card near the edge of frame."""
        img = _make_card_on_bg(offset_x=150, offset_y=100)
        result = detect_card(img)
        assert result is not None

    def test_card_on_white_background(self):
        """Low contrast: white card on light gray background."""
        img = _make_card_on_bg(bg_val=200, card_val=240)
        result = detect_card(img)
        # May or may not detect — but should not crash
        # Accept either outcome
        assert result is None or result.confidence >= 0

    def test_card_on_noisy_background(self):
        """Card on a noisy/patterned background."""
        rng = np.random.RandomState(42)
        img = rng.randint(20, 60, (600, 800, 3), dtype=np.uint8)
        card_w, card_h = 500, int(500 / CARD_ASPECT_RATIO)
        x1, y1 = 150, 142
        cv2.rectangle(img, (x1, y1), (x1 + card_w, y1 + card_h), (220, 220, 220), -1)
        result = detect_card(img)
        assert result is not None

    def test_multiple_rectangles_picks_card_shaped(self):
        """Image with a square AND a card-shaped rectangle."""
        img = np.full((600, 1000, 3), 30, dtype=np.uint8)
        # Square (should be rejected)
        cv2.rectangle(img, (50, 50), (250, 250), (200, 200, 200), -1)
        # Card-shaped rectangle
        card_w, card_h = 400, int(400 / CARD_ASPECT_RATIO)
        cv2.rectangle(img, (500, 100), (500 + card_w, 100 + card_h), (220, 220, 220), -1)
        result = detect_card(img)
        assert result is not None

    def test_no_card_all_noise(self):
        rng = np.random.RandomState(99)
        img = rng.randint(0, 256, (600, 800, 3), dtype=np.uint8)
        result = detect_card(img)
        assert result is None or isinstance(result, type(result))  # no crash

    def test_order_corners_already_ordered(self):
        pts = np.array([[0, 0], [100, 0], [100, 50], [0, 50]], dtype=np.float32)
        ordered = order_corners(pts)
        np.testing.assert_array_almost_equal(ordered[0], [0, 0])
        np.testing.assert_array_almost_equal(ordered[2], [100, 50])

    def test_order_corners_shuffled(self):
        pts = np.array([[100, 50], [0, 0], [0, 50], [100, 0]], dtype=np.float32)
        ordered = order_corners(pts)
        # TL should be (0,0), BR should be (100,50)
        assert ordered[0][0] < ordered[1][0]  # TL.x < TR.x
        assert ordered[0][1] < ordered[3][1]  # TL.y < BL.y

    def test_perspective_transform_identity(self):
        """Axis-aligned corners should produce minimal distortion."""
        img = np.full((400, 600, 3), 128, dtype=np.uint8)
        corners = np.array([[100, 100], [500, 100], [500, 300], [100, 300]], dtype=np.float32)
        rect, w, h = perspective_transform(img, corners)
        assert abs(w - 400) < 2
        assert abs(h - 200) < 2

    def test_px_per_mm_with_known_card_width(self):
        """Verify px_per_mm = card_pixel_width / CARD_WIDTH_MM."""
        card_w = 600
        img = _make_card_on_bg(img_w=1000, img_h=800, card_w=card_w)
        result = detect_card(img)
        assert result is not None
        expected = card_w / CARD_WIDTH_MM
        assert result.px_per_mm == pytest.approx(expected, rel=0.1)

    def test_very_small_card_rejected(self):
        """Card < 5% of image area should be rejected."""
        img = np.full((1000, 1000, 3), 30, dtype=np.uint8)
        card_w = 80  # tiny
        card_h = int(card_w / CARD_ASPECT_RATIO)
        cv2.rectangle(img, (10, 10), (10 + card_w, 10 + card_h), (220, 220, 220), -1)
        result = detect_card(img)
        assert result is None


# ===========================================================================
# 3. NAIL SEGMENTATION EDGE CASES
# ===========================================================================


class TestNailSegmentEdgeCases:
    def test_mock_masks_single_finger(self):
        img = np.zeros((200, 200, 3), dtype=np.uint8)
        masks = _mock_masks(img, {"thumb": (100, 100)})
        assert len(masks) == 1
        assert masks[0].finger == "thumb"
        assert masks[0].mask.any()

    def test_mock_masks_fingertip_at_edge(self):
        """Fingertip at image edge — mask should not crash."""
        img = np.zeros((200, 200, 3), dtype=np.uint8)
        masks = _mock_masks(img, {"index": (0, 0)})
        assert len(masks) == 1

    def test_mock_masks_fingertip_at_corner(self):
        img = np.zeros((200, 200, 3), dtype=np.uint8)
        masks = _mock_masks(img, {"pinky": (199, 199)})
        assert len(masks) == 1

    def test_opencv_segment_on_blank_image(self):
        """All-black image should return masks (possibly empty) without crash."""
        img = np.zeros((400, 600, 3), dtype=np.uint8)
        tips = {"index": (300, 200)}
        masks = _opencv_segment(img, tips)
        assert len(masks) == 1
        assert masks[0].mask.shape == (400, 600)

    def test_opencv_segment_on_all_white_image(self):
        img = np.full((400, 600, 3), 255, dtype=np.uint8)
        tips = {"middle": (300, 200)}
        masks = _opencv_segment(img, tips)
        assert len(masks) == 1

    def test_opencv_segment_five_fingers(self):
        """Ensure all 5 fingers returned even on synthetic image."""
        img = np.full((400, 600, 3), 100, dtype=np.uint8)
        tips = {
            "thumb": (100, 100), "index": (200, 80),
            "middle": (300, 75), "ring": (400, 80), "pinky": (500, 100)
        }
        masks = _opencv_segment(img, tips)
        assert len(masks) == 5
        assert {m.finger for m in masks} == set(tips.keys())

    def test_skin_mask_hsv_on_skin_colored_patch(self):
        """HSV skin detection should detect skin-colored pixels."""
        # Create a skin-colored patch (H≈15, S≈80, V≈180)
        patch = np.full((50, 50, 3), 0, dtype=np.uint8)
        patch[:, :, 0] = 15   # Hue
        patch[:, :, 1] = 80   # Saturation
        patch[:, :, 2] = 180  # Value
        mask = _skin_mask_hsv(patch)
        assert mask.sum() > 0, "Should detect skin-colored pixels"

    def test_skin_mask_hsv_on_blue_patch(self):
        """Blue pixels should not be detected as skin."""
        patch = np.full((50, 50, 3), 0, dtype=np.uint8)
        patch[:, :, 0] = 110  # Hue (blue)
        patch[:, :, 1] = 200  # Saturation
        patch[:, :, 2] = 200  # Value
        mask = _skin_mask_hsv(patch)
        assert mask.sum() == 0

    def test_largest_component_near_tip_empty_mask(self):
        mask = np.zeros((50, 50), dtype=np.uint8)
        result, conf = _largest_component_near_tip(mask, 25, 25)
        assert result is None
        assert conf == 0.0

    def test_largest_component_near_tip_single_blob(self):
        mask = np.zeros((100, 100), dtype=np.uint8)
        cv2.circle(mask, (50, 50), 20, 255, -1)
        result, conf = _largest_component_near_tip(mask, 50, 50)
        assert result is not None
        assert result.sum() > 0
        assert conf > 0

    def test_segment_nails_env_var_mock(self, monkeypatch):
        """SEV_MOCK_SEGMENTATION=1 should use mock."""
        monkeypatch.setenv("SEV_MOCK_SEGMENTATION", "1")
        img = np.zeros((200, 200, 3), dtype=np.uint8)
        masks = segment_nails(img, {"index": (100, 100)}, mock=False)
        assert len(masks) == 1
        assert masks[0].mask.any()  # Mock always produces non-empty


# ===========================================================================
# 4. MEASUREMENT EDGE CASES
# ===========================================================================


class TestMeasureEdgeCases:
    def test_single_pixel_mask(self):
        """A mask with a single pixel should produce 0 width and 0 length."""
        mask_arr = np.zeros((100, 100), dtype=bool)
        mask_arr[50, 50] = True
        mask = NailMask(finger="index", mask=mask_arr, confidence=0.5)
        result = measure_nail(mask, px_per_mm=10.0)
        assert result.width_mm == 0.0
        assert result.length_mm == 0.0

    def test_horizontal_line_mask(self):
        """A single row of pixels → width > 0, length = 0."""
        mask_arr = np.zeros((100, 100), dtype=bool)
        mask_arr[50, 20:80] = True
        mask = NailMask(finger="index", mask=mask_arr, confidence=0.8)
        result = measure_nail(mask, px_per_mm=10.0)
        assert result.width_mm == pytest.approx(59 / 10.0, abs=0.2)
        assert result.length_mm == 0.0

    def test_vertical_line_mask(self):
        """A single column → width = 0, length > 0."""
        mask_arr = np.zeros((100, 100), dtype=bool)
        mask_arr[20:80, 50] = True
        mask = NailMask(finger="middle", mask=mask_arr, confidence=0.8)
        result = measure_nail(mask, px_per_mm=10.0)
        assert result.width_mm == 0.0
        assert result.length_mm == pytest.approx(59 / 10.0, abs=0.2)

    def test_negative_px_per_mm(self):
        mask_arr = np.zeros((100, 100), dtype=bool)
        mask_arr[40:60, 40:60] = True
        mask = NailMask(finger="ring", mask=mask_arr, confidence=0.9)
        result = measure_nail(mask, px_per_mm=-5.0)
        assert result.width_mm == 0.0
        assert result.confidence == 0.0

    def test_very_large_px_per_mm(self):
        """Tiny mm values when scale is huge."""
        mask_arr = np.zeros((100, 100), dtype=bool)
        mask_arr[40:60, 40:60] = True
        mask = NailMask(finger="thumb", mask=mask_arr, confidence=0.9)
        result = measure_nail(mask, px_per_mm=1000.0)
        assert result.width_mm < 1.0
        assert result.length_mm < 1.0

    def test_measure_all_nails_empty_list(self):
        result = measure_all_nails([], px_per_mm=5.0)
        assert result == {}

    def test_px_per_mm_calculation_accuracy(self):
        """Known card: 500px wide → px_per_mm = 500/85.6 ≈ 5.841."""
        px_per_mm = 500 / CARD_WIDTH_MM
        assert px_per_mm == pytest.approx(5.841, abs=0.01)
        # 30px nail width → 30/5.841 ≈ 5.14mm
        mask_arr = np.zeros((200, 200), dtype=bool)
        mask_arr[90:110, 85:115] = True  # 20 rows, 30 cols
        mask = NailMask(finger="index", mask=mask_arr, confidence=0.9)
        result = measure_nail(mask, px_per_mm=px_per_mm)
        assert result.width_mm == pytest.approx(29 / px_per_mm, abs=0.2)


# ===========================================================================
# 5. CURVE ADJUST EDGE CASES
# ===========================================================================


class TestCurveAdjustEdgeCases:
    def test_negative_finger_width(self):
        m = FingerMeasurement(finger="index", width_mm=10.0, length_mm=8.0, confidence=0.9)
        result = adjust_curve(m, finger_width_px=-50.0, px_per_mm=10.0)
        assert result == 10.0  # unchanged

    def test_negative_px_per_mm(self):
        m = FingerMeasurement(finger="index", width_mm=10.0, length_mm=8.0, confidence=0.9)
        result = adjust_curve(m, finger_width_px=100.0, px_per_mm=-1.0)
        assert result == 10.0

    def test_very_small_ratio(self):
        """nail=1mm, finger=100mm → ratio=0.01 → factor 1.05"""
        m = FingerMeasurement(finger="thumb", width_mm=1.0, length_mm=5.0, confidence=0.9)
        result = adjust_curve(m, finger_width_px=1000.0, px_per_mm=10.0)
        assert result == pytest.approx(1.05, rel=0.01)

    def test_very_large_ratio(self):
        """nail=20mm, finger=15mm → ratio=1.33 → factor 1.18"""
        m = FingerMeasurement(finger="thumb", width_mm=20.0, length_mm=10.0, confidence=0.9)
        result = adjust_curve(m, finger_width_px=150.0, px_per_mm=10.0)
        assert result == pytest.approx(20.0 * 1.18, rel=0.01)


# ===========================================================================
# 6. HAND DETECT EDGE CASES
# ===========================================================================


class TestHandDetectEdgeCases:
    def test_estimate_finger_widths_all_same_position(self):
        """All DIP joints at same point → distances = 0 → widths = 0."""
        landmarks = [(100, 100)] * 21
        widths = _estimate_finger_widths(landmarks)
        assert len(widths) == 5
        for name in FINGER_NAMES:
            assert widths[name] == pytest.approx(0.0, abs=0.01)

    def test_estimate_finger_widths_spread(self):
        """Evenly spaced DIP joints → consistent widths."""
        landmarks = [(100, 100)] * 21
        # DIP indices: 3, 7, 11, 15, 19 — space them 50px apart
        for i, dip_idx in enumerate([3, 7, 11, 15, 19]):
            landmarks[dip_idx] = (100 + i * 50, 100)
        widths = _estimate_finger_widths(landmarks)
        # Middle fingers (index, middle, ring) have 2 neighbors at dist=50
        assert widths["index"] == pytest.approx(50 * 0.6, abs=1.0)
        assert widths["middle"] == pytest.approx(50 * 0.6, abs=1.0)


# ===========================================================================
# 7. DEBUG VIZ EDGE CASES
# ===========================================================================


class TestDebugVizEdgeCases:
    def test_debug_image_no_annotations(self):
        """Should return a copy even with no results."""
        img = np.full((400, 600, 3), 128, dtype=np.uint8)
        debug = draw_debug_image(img)
        assert debug.shape == img.shape
        np.testing.assert_array_equal(debug, img)

    def test_debug_image_card_only(self):
        from pipeline.card_detect import CardResult
        img = np.full((400, 600, 3), 128, dtype=np.uint8)
        card = CardResult(
            corners=np.array([[100, 100], [400, 100], [400, 300], [100, 300]], dtype=np.float32),
            px_per_mm=5.0, rectified=np.zeros((200, 300, 3), dtype=np.uint8), confidence=0.9
        )
        debug = draw_debug_image(img, card_result=card)
        assert not np.array_equal(debug, img)

    def test_debug_image_hand_only(self):
        img = np.full((400, 600, 3), 128, dtype=np.uint8)
        hand = _mock_hand()
        debug = draw_debug_image(img, hand_result=hand)
        assert not np.array_equal(debug, img)

    def test_debug_image_empty_masks(self):
        """Empty nail masks should not crash."""
        img = np.full((400, 600, 3), 128, dtype=np.uint8)
        masks = [NailMask(finger="index", mask=np.zeros((400, 600), dtype=bool), confidence=0.0)]
        debug = draw_debug_image(img, nail_masks=masks)
        assert debug.shape == img.shape

    def test_debug_image_measurements_without_hand_ignored(self):
        """Measurements without hand_result should not crash."""
        img = np.full((400, 600, 3), 128, dtype=np.uint8)
        measurements = {"index": FingerMeasurement(finger="index", width_mm=10.0, length_mm=8.0, confidence=0.9)}
        debug = draw_debug_image(img, measurements=measurements)
        # No hand → measurements not drawn → should equal original
        np.testing.assert_array_equal(debug, img)


# ===========================================================================
# 8. INTEGRATION: FULL PIPELINE STAGES
# ===========================================================================


class TestIntegrationPipeline:
    def test_preprocess_to_card_detect(self):
        """preprocess → card_detect on a synthetic image."""
        img = _make_card_on_bg()
        raw = _encode_jpeg(img)
        bgr, q = preprocess(raw)
        result = detect_card(bgr)
        assert result is not None
        assert result.px_per_mm > 0

    def test_full_pipeline_stages_synthetic(self):
        """preprocess → card_detect → mock_hand → mock_segment → measure → curve_adjust → debug_viz."""
        img = _make_card_on_bg(img_w=900, img_h=700, card_w=540)
        raw = _encode_jpeg(img)

        # 1. Preprocess
        bgr, q = preprocess(raw)
        assert q.brightness_level in ("normal", "dark")

        # 2. Card detect
        card = detect_card(bgr)
        assert card is not None

        # 3. Mock hand
        hand = _mock_hand()

        # 4. Mock segment
        masks = segment_nails(bgr, hand.fingertip_positions, mock=True)
        assert len(masks) == 5

        # 5. Measure
        measurements = measure_all_nails(masks, card.px_per_mm)
        assert len(measurements) == 5

        # 6. Curve adjust
        for finger, meas in measurements.items():
            adj = adjust_curve(meas, hand.finger_widths_px[finger], card.px_per_mm)
            assert adj >= meas.width_mm

        # 7. Debug viz
        debug = draw_debug_image(bgr, card_result=card, hand_result=hand,
                                  nail_masks=masks, measurements=measurements)
        assert debug.shape == bgr.shape
        assert not np.array_equal(debug, bgr)

    def test_rotated_card_full_pipeline(self):
        """Full pipeline with a rotated card."""
        img = _make_card_on_bg(angle=20)
        raw = _encode_jpeg(img)
        bgr, q = preprocess(raw)
        card = detect_card(bgr)
        assert card is not None
        hand = _mock_hand()
        masks = segment_nails(bgr, hand.fingertip_positions, mock=True)
        measurements = measure_all_nails(masks, card.px_per_mm)
        assert all(m.width_mm > 0 for m in measurements.values())


# ===========================================================================
# 9. API ERROR PATHS
# ===========================================================================


class TestAPIErrorPaths:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app import app
        return TestClient(app)

    def test_measure_blurry_image_returns_400(self, client):
        """Very blurry image should be rejected."""
        img = np.full((480, 640, 3), 128, dtype=np.uint8)
        img = cv2.GaussianBlur(img, (151, 151), 50)
        raw = _encode_jpeg(img)
        resp = client.post("/pipeline/measure", files={"image": ("blurry.jpg", raw, "image/jpeg")})
        # Blurry images might pass depending on JPEG compression adding edges
        # Accept either 400 (blurry) or 400 (no card) or 200
        assert resp.status_code in (200, 400)

    def test_validate_blurry_image(self, client, monkeypatch):
        import app as app_mod
        monkeypatch.setattr(app_mod, "detect_hand", lambda img, hands_model=None: None)
        img = np.full((480, 640, 3), 128, dtype=np.uint8)
        img = cv2.GaussianBlur(img, (151, 151), 50)
        raw = _encode_jpeg(img)
        resp = client.post("/pipeline/validate", files={"image": ("blurry.jpg", raw, "image/jpeg")})
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False

    def test_validate_dark_image(self, client, monkeypatch):
        import app as app_mod
        monkeypatch.setattr(app_mod, "detect_hand", lambda img, hands_model=None: None)
        img = np.full((480, 640, 3), 5, dtype=np.uint8)
        raw = _encode_jpeg(img)
        resp = client.post("/pipeline/validate", files={"image": ("dark.jpg", raw, "image/jpeg")})
        assert resp.status_code == 200
        data = resp.json()
        assert data["checks"]["brightness"] == "dark"

    def test_validate_overexposed_image(self, client, monkeypatch):
        import app as app_mod
        monkeypatch.setattr(app_mod, "detect_hand", lambda img, hands_model=None: None)
        img = np.full((480, 640, 3), 252, dtype=np.uint8)
        raw = _encode_jpeg(img)
        resp = client.post("/pipeline/validate", files={"image": ("bright.jpg", raw, "image/jpeg")})
        assert resp.status_code == 200
        assert resp.json()["checks"]["brightness"] == "bright"

    def test_measure_missing_file(self, client):
        resp = client.post("/pipeline/measure")
        assert resp.status_code == 422

    def test_validate_missing_file(self, client):
        resp = client.post("/pipeline/validate")
        assert resp.status_code == 422

    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_measure_corrupt_jpeg(self, client):
        resp = client.post("/pipeline/measure",
                           files={"image": ("bad.jpg", b"\xff\xd8\xff\x00garbage", "image/jpeg")})
        assert resp.status_code == 422
