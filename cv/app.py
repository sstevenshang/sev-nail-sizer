"""FastAPI CV service — /pipeline/validate and /pipeline/measure.

Local storage:
  - SQLite DB at $SEV_DB_PATH (default: ./sev_nails.db)
  - Debug images saved to $SEV_IMAGE_DIR (default: ./debug_images/)

Set SEV_PERSIST=0 to disable local storage (useful in tests).
"""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import cv2
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from pipeline.card_detect import detect_card
from pipeline.curve_adjust import adjust_curve
from pipeline.debug_viz import draw_debug_image
from pipeline.hand_detect import detect_hand
from pipeline.measure import measure_all_nails
from pipeline.nail_segment import segment_nails
from pipeline.preprocess import preprocess

app = FastAPI(title="Sev Nail Sizer — CV Service", version="1.0.0")

FINGER_NAMES = ["thumb", "index", "middle", "ring", "pinky"]

# ---------------------------------------------------------------------------
# Local storage configuration
# ---------------------------------------------------------------------------

_DB_PATH = Path(os.environ.get("SEV_DB_PATH", "sev_nails.db"))
_IMAGE_DIR = Path(os.environ.get("SEV_IMAGE_DIR", "debug_images"))
_PERSIST = os.environ.get("SEV_PERSIST", "1") != "0"


def _ensure_storage() -> None:
    """Create the SQLite DB and image directory if they don't exist."""
    if not _PERSIST:
        return
    _IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    with _get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS measurements (
                id          TEXT PRIMARY KEY,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                hand        TEXT,
                px_per_mm   REAL,
                fingers_json TEXT,
                confidence  REAL,
                warnings_json TEXT,
                debug_image_path TEXT
            )
        """)


@contextmanager
def _get_db():
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _save_measurement(
    measurement_id: str,
    hand: str,
    px_per_mm: float,
    fingers: dict,
    confidence: float,
    warnings: list,
    debug_jpg_bytes: bytes,
) -> Optional[str]:
    """Persist a measurement record to SQLite and save the debug image.

    Returns the path to the saved debug image, or None if persistence is off.
    """
    if not _PERSIST:
        return None

    _ensure_storage()

    # Save debug image
    img_path = _IMAGE_DIR / f"{measurement_id}.jpg"
    img_path.write_bytes(debug_jpg_bytes)

    with _get_db() as conn:
        conn.execute(
            """
            INSERT INTO measurements
                (id, hand, px_per_mm, fingers_json, confidence, warnings_json, debug_image_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                measurement_id,
                hand,
                px_per_mm,
                json.dumps(fingers),
                confidence,
                json.dumps(warnings),
                str(img_path),
            ),
        )

    return str(img_path)


# Initialise storage on startup (non-blocking — only creates if not exists)
try:
    _ensure_storage()
except Exception:
    pass  # Don't crash the service if storage init fails


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /measurements — list stored measurements
# ---------------------------------------------------------------------------


@app.get("/measurements")
def list_measurements(limit: int = 20) -> dict:
    """Return recently stored measurement records from SQLite."""
    if not _PERSIST:
        return {"measurements": [], "note": "Persistence disabled"}

    try:
        with _get_db() as conn:
            rows = conn.execute(
                """
                SELECT id, created_at, hand, px_per_mm, confidence, debug_image_path
                FROM measurements
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return {
            "measurements": [dict(r) for r in rows],
            "db_path": str(_DB_PATH),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB error: {exc}")


# ---------------------------------------------------------------------------
# GET /measurements/{id}
# ---------------------------------------------------------------------------


@app.get("/measurements/{measurement_id}")
def get_measurement(measurement_id: str) -> dict:
    """Retrieve a single measurement by ID."""
    if not _PERSIST:
        raise HTTPException(status_code=404, detail="Persistence disabled")

    try:
        with _get_db() as conn:
            row = conn.execute(
                "SELECT * FROM measurements WHERE id = ?", (measurement_id,)
            ).fetchone()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DB error: {exc}")

    if row is None:
        raise HTTPException(status_code=404, detail="Measurement not found")

    data = dict(row)
    data["fingers"] = json.loads(data.pop("fingers_json"))
    data["warnings"] = json.loads(data.pop("warnings_json"))
    return data


# ---------------------------------------------------------------------------
# POST /pipeline/validate
# ---------------------------------------------------------------------------


@app.post("/pipeline/validate")
async def validate_image(image: UploadFile = File(...)) -> dict:
    """
    Quick pre-check: blur/brightness, card detection, hand detection.
    Returns {valid, checks, guidance}.  No segmentation call is made.
    """
    raw = await image.read()

    try:
        img, quality = preprocess(raw)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Cannot decode image: {exc}")

    card_result = detect_card(img)
    card_detected = card_result is not None

    hand_result = detect_hand(img)
    hand_detected = hand_result is not None

    is_sharp = quality.is_sharp
    brightness_ok = quality.brightness_level == "normal"

    if is_sharp and brightness_ok:
        image_quality = "good"
    elif is_sharp or brightness_ok:
        image_quality = "fair"
    else:
        image_quality = "poor"

    checks = {
        "card_detected": card_detected,
        "hand_detected": hand_detected,
        "image_quality": image_quality,
        "blur_score": round(quality.blur_score, 1),
        "brightness": quality.brightness_level,
    }

    valid = card_detected and hand_detected and is_sharp and brightness_ok

    guidance: Optional[str] = None
    if not valid:
        parts: list[str] = []
        if not card_detected:
            parts.append("Place the full credit card in the frame")
        if not hand_detected:
            parts.append("place your hand flat on the card")
        if not is_sharp:
            parts.append("hold the camera steady for a sharper image")
        if quality.brightness_level == "dark":
            parts.append("use better lighting")
        elif quality.brightness_level == "bright":
            parts.append("reduce glare or move away from direct light")
        if parts:
            guidance = (parts[0][0].upper() + parts[0][1:] + (
                "; " + "; ".join(parts[1:]) if len(parts) > 1 else ""
            ))

    return {"valid": valid, "checks": checks, "guidance": guidance}


# ---------------------------------------------------------------------------
# POST /pipeline/measure
# ---------------------------------------------------------------------------


@app.post("/pipeline/measure")
async def measure_image(
    image: UploadFile = File(...),
    hand: Optional[str] = Form(None),
) -> dict:
    """
    Full pipeline: preprocess → card detect → hand detect → nail segment
    → measure → curve-adjust → debug image.
    Saves result to SQLite + local filesystem.
    Returns per-finger measurements.
    """
    raw = await image.read()

    try:
        img, quality = preprocess(raw)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Cannot decode image: {exc}")

    if not quality.is_sharp:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "image_too_blurry",
                "message": "Image is too blurry. Hold camera steady and ensure good lighting.",
                "guidance": "Hold camera steady, ensure good lighting",
            },
        )

    card_result = detect_card(img)
    if card_result is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "card_not_detected",
                "message": "Could not find a credit card in the image.",
                "guidance": "Place card fully visible in frame",
            },
        )

    hand_result = detect_hand(img)
    if hand_result is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "hand_not_detected",
                "message": "Could not detect a hand in the image.",
                "guidance": "Place hand flat on card",
            },
        )

    detected_hand = hand or hand_result.handedness
    mock_seg = os.environ.get("SEV_MOCK_SEGMENTATION") == "1"

    nail_masks = segment_nails(
        img,
        hand_result.fingertip_positions,
        mock=mock_seg,
    )
    raw_measurements = measure_all_nails(nail_masks, card_result.px_per_mm)

    fingers_out: dict = {}
    warnings: list[str] = []
    total_conf = 0.0
    n = 0

    for finger_name in FINGER_NAMES:
        meas = raw_measurements.get(finger_name)
        if meas is None or meas.width_mm == 0:
            warnings.append(f"{finger_name}_not_detected")
            continue

        finger_width_px = hand_result.finger_widths_px.get(finger_name, 0.0)
        curve_adj = adjust_curve(meas, finger_width_px, card_result.px_per_mm)

        fingers_out[finger_name] = {
            "width_mm": meas.width_mm,
            "length_mm": meas.length_mm,
            "curve_adj_width_mm": curve_adj,
            "confidence": meas.confidence,
        }
        total_conf += meas.confidence
        n += 1

    if n == 0:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": "Could not measure any nails.",
            },
        )

    overall_confidence = round(total_conf / n, 3)

    debug_img = draw_debug_image(
        img,
        card_result=card_result,
        hand_result=hand_result,
        nail_masks=nail_masks,
        measurements=raw_measurements,
    )
    _, buf = cv2.imencode(".jpg", debug_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    debug_jpg = buf.tobytes()
    debug_b64 = base64.b64encode(debug_jpg).decode()

    measurement_id = f"msr_{uuid.uuid4().hex[:8]}"

    # Persist to SQLite + local filesystem (best-effort — never fail the request)
    try:
        _save_measurement(
            measurement_id=measurement_id,
            hand=detected_hand,
            px_per_mm=card_result.px_per_mm,
            fingers=fingers_out,
            confidence=overall_confidence,
            warnings=warnings,
            debug_jpg_bytes=debug_jpg,
        )
    except Exception:
        pass

    return {
        "id": measurement_id,
        "hand": detected_hand,
        "scale_px_per_mm": round(card_result.px_per_mm, 3),
        "card_detected": True,
        "fingers": fingers_out,
        "overall_confidence": overall_confidence,
        "debug_image_b64": debug_b64,
        "warnings": warnings,
    }
