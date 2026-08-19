"""
fire_analyser — edge/cloud microservice
Receives preprocessed images (640x480) from the preprocessor
and runs YOLOv8n-classify inference to detect fire.
Saves inference metrics to /var/wildfire/output/inference_metrics.csv.
When fire is detected, sends an alert to the alert-manager asynchronously.
"""

import asyncio
import base64
import csv
import io
import logging
import os
import time
from datetime import datetime

import httpx
import psutil
from PIL import Image
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fire-analyser")

app = FastAPI(title="Fire Analyser")

# ── Configuration ─────────────────────────────────────────────────
MODEL_PATH         = os.getenv("MODEL_PATH",         "/var/wildfire/models/fire_classifier.pt")
OUTPUT_DIR         = os.getenv("OUTPUT_DIR",         "/var/wildfire/output")
INFERENCE_NODE     = os.getenv("INFERENCE_NODE",     "unknown")
CONFIDENCE_THR     = float(os.getenv("CONFIDENCE_THR", "0.5"))
ALERT_MANAGER_URL  = os.getenv("ALERT_MANAGER_URL",  "http://alert-manager:8005")

METRICS_FILE = os.path.join(OUTPUT_DIR, "inference_metrics.csv")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── State ─────────────────────────────────────────────────────────
state = {
    "received":      0,
    "fire_detected": 0,
    "nofire":        0,
    "errors":        0,
    "alerts_sent":   0,
    "model_loaded":  False,
}

model = None

# ── CSV ───────────────────────────────────────────────────────────
if not os.path.exists(METRICS_FILE):
    with open(METRICS_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp",
            "capture_node",
            "processing_node",
            "inference_node",
            "image_id",
            "image_width",
            "image_height",
            "predicted_class",
            "confidence",
            "fire_detected",
            "inference_time_ms",
            "cpu_usage_pct",
            "ram_usage_pct",
            "ram_used_mb",
        ])


# ── Model ─────────────────────────────────────────────────────────

def load_model():
    global model
    from ultralytics import YOLO
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Model not found: {MODEL_PATH}")
    log.info(f"Loading model from {MODEL_PATH} ...")
    model = YOLO(MODEL_PATH)
    state["model_loaded"] = True
    log.info(f"Model loaded | node={INFERENCE_NODE}")


# ── Input schema ──────────────────────────────────────────────────

class ProcessedImage(BaseModel):
    capture_node:    str
    processing_node: str
    image_id:        str
    width:           int
    height:          int
    data:            str  # base64 JPEG 640x480


# ── Inference ─────────────────────────────────────────────────────

def decode_image(b64_data: str) -> Image.Image:
    raw = base64.b64decode(b64_data)
    return Image.open(io.BytesIO(raw)).convert("RGB")


def run_inference(pil_img: Image.Image) -> tuple[str, float]:
    results = model(pil_img, verbose=False)
    probs = results[0].probs
    predicted_class = results[0].names[probs.top1]
    confidence = float(probs.top1conf)
    return predicted_class, confidence


def write_metrics(capture_node: str, processing_node: str, image_id: str,
                  width: int, height: int, predicted_class: str,
                  confidence: float, fire_detected: bool,
                  inference_time_ms: float, cpu_usage_pct: float,
                  ram_usage_pct: float, ram_used_mb: float):
    with open(METRICS_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.utcnow().isoformat(),
            capture_node,
            processing_node,
            INFERENCE_NODE,
            image_id,
            width,
            height,
            predicted_class,
            round(confidence, 4),
            int(fire_detected),
            round(inference_time_ms, 3),
            round(cpu_usage_pct, 1),
            round(ram_usage_pct, 1),
            round(ram_used_mb, 1),
        ])


# ── Alert ─────────────────────────────────────────────────────────

async def send_alert(image: ProcessedImage, confidence: float):
    """Sends a fire alert to the alert-manager asynchronously."""
    try:
        payload = {
            "image_id":       image.image_id,
            "capture_node":   image.capture_node,
            "inference_node": INFERENCE_NODE,
            "confidence":     confidence,
            "timestamp":      datetime.utcnow().isoformat(),
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{ALERT_MANAGER_URL}/alert",
                json=payload,
            )
            response.raise_for_status()
            state["alerts_sent"] += 1
            log.info(f"Alert sent for {image.image_id} → alert_id={response.json().get('alert_id')}")
    except httpx.ConnectError:
        log.warning(f"Alert manager unreachable ({ALERT_MANAGER_URL})")
    except Exception as e:
        log.error(f"Error sending alert for {image.image_id}: {e}")


# ── Endpoints ─────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    load_model()


@app.get("/health")
async def health():
    return {
        "status":         "ok",
        "inference_node": INFERENCE_NODE,
        "model_loaded":   state["model_loaded"],
        "model_path":     MODEL_PATH,
    }


@app.get("/status")
async def status():
    total = state["received"]
    fire_rate = round(state["fire_detected"] / total * 100, 1) if total > 0 else 0
    return {
        "inference_node":        INFERENCE_NODE,
        "received":              total,
        "fire_detected":         state["fire_detected"],
        "nofire":                state["nofire"],
        "errors":                state["errors"],
        "alerts_sent":           state["alerts_sent"],
        "fire_detection_rate_pct": fire_rate,
        "model_loaded":          state["model_loaded"],
        "confidence_threshold":  CONFIDENCE_THR,
        "alert_manager_url":     ALERT_MANAGER_URL,
    }


@app.post("/analyse")
async def analyse(image: ProcessedImage):
    if not state["model_loaded"]:
        raise HTTPException(status_code=503, detail="Model not yet loaded")

    state["received"] += 1
    log.info(f"Received: {image.image_id} ({image.width}x{image.height}) "
             f"from processing_node={image.processing_node}")

    try:
        ram_before = psutil.virtual_memory()
        psutil.cpu_percent(interval=None)

        t_start = time.time()

        pil_img = decode_image(image.data)
        predicted_class, confidence = run_inference(pil_img)

        inference_time_ms = (time.time() - t_start) * 1000
        cpu_usage         = psutil.cpu_percent(interval=inference_time_ms / 1000)
        ram_after         = psutil.virtual_memory()
        ram_used_mb       = (ram_after.used - ram_before.used) / 1024 / 1024
        ram_usage_pct     = ram_after.percent

        fire_detected = (predicted_class == "fire") and (confidence >= CONFIDENCE_THR)

        if fire_detected:
            state["fire_detected"] += 1
            # Send alert asynchronously — does not block the response
            asyncio.create_task(send_alert(image, confidence))
        else:
            state["nofire"] += 1

        write_metrics(
            capture_node=image.capture_node,
            processing_node=image.processing_node,
            image_id=image.image_id,
            width=image.width,
            height=image.height,
            predicted_class=predicted_class,
            confidence=confidence,
            fire_detected=fire_detected,
            inference_time_ms=inference_time_ms,
            cpu_usage_pct=cpu_usage,
            ram_usage_pct=ram_usage_pct,
            ram_used_mb=ram_used_mb,
        )

        log.info(
            f"Result: {image.image_id} → {predicted_class} "
            f"({confidence*100:.1f}%) | fire={fire_detected} | "
            f"{inference_time_ms:.1f}ms | CPU {cpu_usage:.1f}% | "
            f"RAM {ram_usage_pct:.1f}% ({ram_used_mb:+.1f}MB)"
        )

        return {
            "image_id":         image.image_id,
            "capture_node":     image.capture_node,
            "processing_node":  image.processing_node,
            "inference_node":   INFERENCE_NODE,
            "predicted_class":  predicted_class,
            "confidence":       round(confidence, 4),
            "fire_detected":    fire_detected,
            "inference_time_ms": round(inference_time_ms, 3),
            "cpu_usage_pct":    round(cpu_usage, 1),
            "ram_usage_pct":    round(ram_usage_pct, 1),
            "ram_used_mb":      round(ram_used_mb, 1),
        }

    except Exception as e:
        state["errors"] += 1
        log.error(f"Error on {image.image_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=False)