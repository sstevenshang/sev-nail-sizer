"""FastAPI endpoint tests — all pipeline dependencies mocked where needed."""

from __future__ import annotations

import io

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _jpeg_bytes(img: np.ndarray) -> bytes:
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _card_image_bytes() -> bytes:
    """800×600 image with a crisp white credit-card rectangle."""
    from pipeline.card_detect import CARD_ASPECT_RATIO
    img = np.full((600, 800, 3), 30, dtype=np.uint8)
    card_w, card_h = 500, int(round(500 / CARD_ASPECT_RATIO))
    x1, y1 = (800 - card_w) // 2, (600 - card_h) // 2
    cv2.rectangle(img, (x1, y1), (x1 + card_w, y1 + card_h), (220, 220, 220), -1)
    return _jpeg_bytes(img)


def _mock_card():
    from pipeline.card_detect import CardResult
    corners = np.array(
        [[150, 143], [650, 143], [650, 457], [150, 457]], dtype=np.float32
    )
    return CardResult(
        corners=corners,
        px_per_mm=500 / 85.6,
        rectified=np.zeros((314, 500, 3), dtype=np.uint8),
        confidence=0.97,
    )


def _mock_hand():
    from pipeline.hand_detect import HandResult
    tips = {
        "thumb":  (200, 80),
        "index":  (280, 60),
        "middle": (350, 55),
        "ring":   (420, 62),
        "pinky":  (490, 80),
    }
    return HandResult(
        landmarks=[(320, 300)] * 21,
        handedness="right",
        fingertip_positions=tips,
        finger_widths_px={f: 40.0 for f in tips},
    )


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# POST /pipeline/validate
# ---------------------------------------------------------------------------


def test_validate_bad_file(client):
    resp = client.post(
        "/pipeline/validate",
        files={"image": ("bad.jpg", b"notanimage", "image/jpeg")},
    )
    assert resp.status_code == 422


def test_validate_card_and_hand_mocked(client, monkeypatch):
    """With card + hand mocked → valid=True."""
    import app as app_mod

    monkeypatch.setattr(app_mod, "detect_card", lambda img: _mock_card())
    monkeypatch.setattr(app_mod, "detect_hand", lambda img, hands_model=None: _mock_hand())

    resp = client.post(
        "/pipeline/validate",
        files={"image": ("img.jpg", _card_image_bytes(), "image/jpeg")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["checks"]["card_detected"] is True
    assert data["checks"]["hand_detected"] is True
    assert data["guidance"] is None


def test_validate_no_card(client, monkeypatch):
    """Card not detected → valid=False with guidance."""
    import app as app_mod

    monkeypatch.setattr(app_mod, "detect_card", lambda img: None)
    monkeypatch.setattr(app_mod, "detect_hand", lambda img, hands_model=None: _mock_hand())

    resp = client.post(
        "/pipeline/validate",
        files={"image": ("img.jpg", _card_image_bytes(), "image/jpeg")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert data["checks"]["card_detected"] is False
    assert data["guidance"] is not None


def test_validate_no_hand(client, monkeypatch):
    """Hand not detected → valid=False with guidance."""
    import app as app_mod

    monkeypatch.setattr(app_mod, "detect_card", lambda img: _mock_card())
    monkeypatch.setattr(app_mod, "detect_hand", lambda img, hands_model=None: None)

    resp = client.post(
        "/pipeline/validate",
        files={"image": ("img.jpg", _card_image_bytes(), "image/jpeg")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert data["checks"]["hand_detected"] is False


def test_validate_checks_schema(client, monkeypatch):
    import app as app_mod

    monkeypatch.setattr(app_mod, "detect_card", lambda img: _mock_card())
    monkeypatch.setattr(app_mod, "detect_hand", lambda img, hands_model=None: _mock_hand())

    resp = client.post(
        "/pipeline/validate",
        files={"image": ("img.jpg", _card_image_bytes(), "image/jpeg")},
    )
    checks = resp.json()["checks"]
    assert "card_detected" in checks
    assert "hand_detected" in checks
    assert "image_quality" in checks
    assert "blur_score" in checks
    assert "brightness" in checks


# ---------------------------------------------------------------------------
# POST /pipeline/measure
# ---------------------------------------------------------------------------


def test_measure_bad_file(client):
    resp = client.post(
        "/pipeline/measure",
        files={"image": ("bad.jpg", b"notanimage", "image/jpeg")},
    )
    assert resp.status_code == 422


def test_measure_no_card_returns_400(client, monkeypatch):
    import app as app_mod

    monkeypatch.setattr(app_mod, "detect_card", lambda img: None)
    monkeypatch.setattr(app_mod, "detect_hand", lambda img, hands_model=None: _mock_hand())

    resp = client.post(
        "/pipeline/measure",
        files={"image": ("img.jpg", _card_image_bytes(), "image/jpeg")},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "card_not_detected"


def test_measure_no_hand_returns_400(client, monkeypatch):
    import app as app_mod

    monkeypatch.setattr(app_mod, "detect_card", lambda img: _mock_card())
    monkeypatch.setattr(app_mod, "detect_hand", lambda img, hands_model=None: None)

    resp = client.post(
        "/pipeline/measure",
        files={"image": ("img.jpg", _card_image_bytes(), "image/jpeg")},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "hand_not_detected"


def test_measure_success_schema(client, monkeypatch):
    """Full measure pipeline with mocked card+hand; nail seg uses mock env var."""
    import app as app_mod

    monkeypatch.setattr(app_mod, "detect_card", lambda img: _mock_card())
    monkeypatch.setattr(app_mod, "detect_hand", lambda img, hands_model=None: _mock_hand())

    resp = client.post(
        "/pipeline/measure",
        files={"image": ("img.jpg", _card_image_bytes(), "image/jpeg")},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "id" in data
    assert data["id"].startswith("msr_")
    assert "hand" in data
    assert data["scale_px_per_mm"] > 0
    assert data["card_detected"] is True
    assert "fingers" in data
    assert len(data["fingers"]) == 5
    assert "overall_confidence" in data
    assert "debug_image_b64" in data
    assert isinstance(data["warnings"], list)


def test_measure_finger_schema(client, monkeypatch):
    import app as app_mod

    monkeypatch.setattr(app_mod, "detect_card", lambda img: _mock_card())
    monkeypatch.setattr(app_mod, "detect_hand", lambda img, hands_model=None: _mock_hand())

    resp = client.post(
        "/pipeline/measure",
        files={"image": ("img.jpg", _card_image_bytes(), "image/jpeg")},
    )
    fingers = resp.json()["fingers"]
    for name in ["thumb", "index", "middle", "ring", "pinky"]:
        assert name in fingers
        f = fingers[name]
        assert "width_mm" in f
        assert "length_mm" in f
        assert "curve_adj_width_mm" in f
        assert "confidence" in f
        assert f["width_mm"] > 0
        assert f["curve_adj_width_mm"] >= f["width_mm"]


def test_measure_hand_param_overrides_detected(client, monkeypatch):
    import app as app_mod

    monkeypatch.setattr(app_mod, "detect_card", lambda img: _mock_card())
    monkeypatch.setattr(app_mod, "detect_hand", lambda img, hands_model=None: _mock_hand())

    resp = client.post(
        "/pipeline/measure",
        files={"image": ("img.jpg", _card_image_bytes(), "image/jpeg")},
        data={"hand": "left"},
    )
    assert resp.status_code == 200
    assert resp.json()["hand"] == "left"


# ---------------------------------------------------------------------------
# photo_type helpers
# ---------------------------------------------------------------------------


def _mock_hand_four_finger():
    """HandResult with index/middle/ring/pinky tips; thumb at (0, 0)."""
    from pipeline.hand_detect import HandResult

    tips = {
        "thumb":  (0, 0),
        "index":  (280, 60),
        "middle": (350, 55),
        "ring":   (420, 62),
        "pinky":  (490, 80),
    }
    widths = {
        "thumb": 0.0,
        "index": 40.0,
        "middle": 40.0,
        "ring": 40.0,
        "pinky": 40.0,
    }
    return HandResult(
        landmarks=[(320, 300)] * 21,
        handedness="right",
        fingertip_positions=tips,
        finger_widths_px=widths,
    )


def _mock_hand_thumb_only():
    """HandResult with only thumb tip meaningful; index–pinky at (0, 0)."""
    from pipeline.hand_detect import HandResult

    tips = {
        "thumb":  (200, 80),
        "index":  (0, 0),
        "middle": (0, 0),
        "ring":   (0, 0),
        "pinky":  (0, 0),
    }
    widths = {
        "thumb": 40.0,
        "index": 0.0,
        "middle": 0.0,
        "ring": 0.0,
        "pinky": 0.0,
    }
    return HandResult(
        landmarks=[(320, 300)] * 21,
        handedness="right",
        fingertip_positions=tips,
        finger_widths_px=widths,
    )


# ---------------------------------------------------------------------------
# photo_type — auto-detect tests
# ---------------------------------------------------------------------------


def test_measure_photo_type_auto_detect_four_finger(client, monkeypatch):
    """Auto-detect: hand with 4 fingers (thumb at origin) → photo_type='four_finger'."""
    import app as app_mod

    monkeypatch.setattr(app_mod, "detect_card", lambda img: _mock_card())
    monkeypatch.setattr(app_mod, "detect_hand", lambda img, hands_model=None: _mock_hand_four_finger())

    resp = client.post(
        "/pipeline/measure",
        files={"image": ("img.jpg", _card_image_bytes(), "image/jpeg")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["photo_type"] == "four_finger"


def test_measure_photo_type_auto_detect_thumb(client, monkeypatch):
    """Auto-detect: hand with only thumb → photo_type='thumb'."""
    import app as app_mod

    monkeypatch.setattr(app_mod, "detect_card", lambda img: _mock_card())
    monkeypatch.setattr(app_mod, "detect_hand", lambda img, hands_model=None: _mock_hand_thumb_only())

    resp = client.post(
        "/pipeline/measure",
        files={"image": ("img.jpg", _card_image_bytes(), "image/jpeg")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["photo_type"] == "thumb"


def test_measure_photo_type_explicit_param(client, monkeypatch):
    """Explicit photo_type param overrides auto-detection."""
    import app as app_mod

    monkeypatch.setattr(app_mod, "detect_card", lambda img: _mock_card())
    monkeypatch.setattr(app_mod, "detect_hand", lambda img, hands_model=None: _mock_hand_thumb_only())

    resp = client.post(
        "/pipeline/measure",
        files={"image": ("img.jpg", _card_image_bytes(), "image/jpeg")},
        data={"photo_type": "thumb"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["photo_type"] == "thumb"


def test_measure_four_finger_only_has_four_fingers(client, monkeypatch):
    """four_finger photo: response has only index/middle/ring/pinky, no thumb, no thumb warning."""
    import app as app_mod

    monkeypatch.setattr(app_mod, "detect_card", lambda img: _mock_card())
    monkeypatch.setattr(app_mod, "detect_hand", lambda img, hands_model=None: _mock_hand_four_finger())

    resp = client.post(
        "/pipeline/measure",
        files={"image": ("img.jpg", _card_image_bytes(), "image/jpeg")},
        data={"photo_type": "four_finger"},
    )
    assert resp.status_code == 200
    data = resp.json()
    fingers = data["fingers"]
    assert "thumb" not in fingers
    for name in ["index", "middle", "ring", "pinky"]:
        assert name in fingers
    # No thumb_not_detected warning
    assert "thumb_not_detected" not in data["warnings"]


def test_measure_thumb_only_has_thumb(client, monkeypatch):
    """thumb photo: response has only thumb, no four-finger warnings."""
    import app as app_mod

    monkeypatch.setattr(app_mod, "detect_card", lambda img: _mock_card())
    monkeypatch.setattr(app_mod, "detect_hand", lambda img, hands_model=None: _mock_hand_thumb_only())

    resp = client.post(
        "/pipeline/measure",
        files={"image": ("img.jpg", _card_image_bytes(), "image/jpeg")},
        data={"photo_type": "thumb"},
    )
    assert resp.status_code == 200
    data = resp.json()
    fingers = data["fingers"]
    assert "thumb" in fingers
    for name in ["index", "middle", "ring", "pinky"]:
        assert name not in fingers
    # No warnings about the four fingers not being detected
    for name in ["index", "middle", "ring", "pinky"]:
        assert f"{name}_not_detected" not in data["warnings"]


# ---------------------------------------------------------------------------
# /pipeline/merge tests
# ---------------------------------------------------------------------------


def _insert_measurement(client, monkeypatch, hand_fn, photo_type_param, hand="right"):
    """Helper: call /pipeline/measure and return the measurement ID."""
    import app as app_mod

    monkeypatch.setattr(app_mod, "detect_card", lambda img: _mock_card())
    monkeypatch.setattr(app_mod, "detect_hand", lambda img, hands_model=None: hand_fn())

    resp = client.post(
        "/pipeline/measure",
        files={"image": ("img.jpg", _card_image_bytes(), "image/jpeg")},
        data={"photo_type": photo_type_param, "hand": hand},
    )
    assert resp.status_code == 200
    return resp.json()["id"]


def test_merge_success(client, monkeypatch):
    """Merge a thumb + four_finger measurement → complete 5-finger response."""
    thumb_id = _insert_measurement(client, monkeypatch, _mock_hand_thumb_only, "thumb")
    four_id = _insert_measurement(client, monkeypatch, _mock_hand_four_finger, "four_finger")

    resp = client.post(
        "/pipeline/merge",
        json={"thumb_measurement_id": thumb_id, "four_finger_measurement_id": four_id},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["photo_type"] == "merged"
    assert "id" in data
    assert data["id"].startswith("msr_")
    fingers = data["fingers"]
    assert "thumb" in fingers
    for name in ["index", "middle", "ring", "pinky"]:
        assert name in fingers
    # Each finger should have source_measurement
    assert fingers["thumb"]["source_measurement"] == thumb_id
    assert fingers["index"]["source_measurement"] == four_id
    assert "source_measurements" in data


def test_merge_same_photo_type_fails(client, monkeypatch):
    """Merging two thumb measurements → 400."""
    thumb_id1 = _insert_measurement(client, monkeypatch, _mock_hand_thumb_only, "thumb")
    thumb_id2 = _insert_measurement(client, monkeypatch, _mock_hand_thumb_only, "thumb")

    resp = client.post(
        "/pipeline/merge",
        json={"thumb_measurement_id": thumb_id1, "four_finger_measurement_id": thumb_id2},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "wrong_photo_type"


def test_merge_different_hands_fails(client, monkeypatch):
    """Merging left thumb + right four_finger → 400."""
    thumb_id = _insert_measurement(client, monkeypatch, _mock_hand_thumb_only, "thumb", hand="left")
    four_id = _insert_measurement(client, monkeypatch, _mock_hand_four_finger, "four_finger", hand="right")

    resp = client.post(
        "/pipeline/merge",
        json={"thumb_measurement_id": thumb_id, "four_finger_measurement_id": four_id},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "hand_mismatch"


def test_merge_not_found(client, monkeypatch):
    """Merging with a nonexistent ID → 404."""
    thumb_id = _insert_measurement(client, monkeypatch, _mock_hand_thumb_only, "thumb")

    resp = client.post(
        "/pipeline/merge",
        json={"thumb_measurement_id": thumb_id, "four_finger_measurement_id": "msr_nonexistent"},
    )
    assert resp.status_code == 404
