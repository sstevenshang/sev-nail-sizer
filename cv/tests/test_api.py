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
