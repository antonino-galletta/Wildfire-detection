"""
preprocessor — edge microservice
Receives raw images from image-capture, resizes them,
normalizes brightness and forwards them to fire-analyser.
Writes processing metrics to /var/wildfire/output/metrics.csv
"""

import asyncio
import base64
import csv
import io
import logging
import os
import time
from datetime import datetime

import numpy as np
import cv2
import httpx
import psutil
from PIL import Image
from fastapi import FastAPI, HTTPException
import uvicorn

import sys
sys.path.append("/app/shared")
from models import RawImage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("preprocessor")

app = FastAPI(title="Preprocessor")

TARGET_WIDTH      = int(os.getenv("TARGET_WIDTH",  "640"))
TARGET_HEIGHT     = int(os.getenv("TARGET_HEIGHT", "480"))
JPEG_QUALITY      = int(os.getenv("JPEG_QUALITY",  "85"))
OUTPUT_DIR        = os.getenv("OUTPUT_DIR", "/var/wildfire/output")
PROCESSING_NODE   = os.getenv("PROCESSING_NODE", "unknown")
FIRE_ANALYSER_URL = os.getenv("FIRE_ANALYSER_URL", "http://fire-analyser:8003")

METRICS_FILE = os.path.join(OUTPUT_DIR, "metrics.csv")

state = {"received": 0, "processed": 0, "forwarded": 0, "errors": 0}
os.makedirs(OUTPUT_DIR, exist_ok=True)

if not os.path.exists(METRICS_FILE):
    with open(METRICS_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp",
            "capture_node",
            "processing_node",
            "image_id",
            "original_width",
            "original_height",
            "processed_width",
            "processed_height",
            "processing_time_ms",
            "cpu_usage_pct",
            "ram_usage_pct",
            "ram_used_mb",
        ])


def decode_image(b64_data: str) -> np.ndarray:
    raw = base64.b64decode(b64_data)
    pil = Image.open(io.BytesIO(raw)).convert("RGB")
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def preprocess(img: np.ndarray) -> np.ndarray:
    # Resize to target resolution
    resized = cv2.resize(img, (TARGET_WIDTH, TARGET_HEIGHT), interpolation=cv2.INTER_AREA)
    # Apply CLAHE on the L channel in LAB color space for adaptive brightness normalization
    lab = cv2.cvtColor(resized, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def encode_image(img: np.ndarray) -> str:
    params = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
    _, buffer = cv2.imencode(".jpg", img, params)
    return base64.b64encode(buffer).decode("utf-8")


def save_to_disk(img: np.ndarray, image_id: str):
    out_path = os.path.join(OUTPUT_DIR, f"processed_{image_id}")
    cv2.imwrite(out_path, img)


def write_metrics(capture_node: str, image_id: str,
                  orig_w: int, orig_h: int,
                  processing_time_ms: float,
                  cpu_usage_pct: float,
                  ram_usage_pct: float,
                  ram_used_mb: float):
    with open(METRICS_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.utcnow().isoformat(),
            capture_node,
            PROCESSING_NODE,
            image_id,
            orig_w,
            orig_h,
            TARGET_WIDTH,
            TARGET_HEIGHT,
            round(processing_time_ms, 3),
            round(cpu_usage_pct, 1),
            round(ram_usage_pct, 1),
            round(ram_used_mb, 1),
        ])


async def forward_to_analyser(capture_node: str, image_id: str,
                               width: int, height: int, b64_data: str):
    """Forwards the processed image to fire-analyser asynchronously."""
    try:
        payload = {
            "capture_node":    capture_node,
            "processing_node": PROCESSING_NODE,
            "image_id":        image_id,
            "width":           width,
            "height":          height,
            "data":            b64_data,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{FIRE_ANALYSER_URL}/analyse",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
            log.info(
                f"Analysis: {image_id} → {result.get('predicted_class')} "
                f"({result.get('confidence', 0)*100:.1f}%) "
                f"fire={result.get('fire_detected')}"
            )
            state["forwarded"] += 1
    except httpx.ConnectError:
        log.warning(f"Fire-analyser unreachable ({FIRE_ANALYSER_URL})")
    except Exception as e:
        log.error(f"Error forwarding to fire-analyser for {image_id}: {e}")


@app.get("/health")
async def health():
    return {"status": "ok", "processing_node": PROCESSING_NODE}


@app.get("/status")
async def status():
    return {
        "received":         state["received"],
        "processed":        state["processed"],
        "forwarded":        state["forwarded"],
        "errors":           state["errors"],
        "processing_node":  PROCESSING_NODE,
        "target_resolution": f"{TARGET_WIDTH}x{TARGET_HEIGHT}",
        "fire_analyser_url": FIRE_ANALYSER_URL,
        "metrics_file":     METRICS_FILE,
    }


@app.post("/preprocess")
async def preprocess_image(image: RawImage):
    state["received"] += 1
    log.info(f"Received: {image.image_id} ({image.width}x{image.height}) from {image.drone_id}")

    try:
        # Measure RAM before processing
        ram_before = psutil.virtual_memory()
        psutil.cpu_percent(interval=None)  # warm up CPU counter

        t_start = time.time()

        img_raw       = decode_image(image.data)
        img_processed = preprocess(img_raw)
        b64_processed = encode_image(img_processed)
        save_to_disk(img_processed, image.image_id)

        processing_time_ms = (time.time() - t_start) * 1000

        # Measure CPU over the exact processing duration
        cpu_usage = psutil.cpu_percent(interval=processing_time_ms / 1000)

        # Measure RAM after processing
        ram_after     = psutil.virtual_memory()
        ram_used_mb   = (ram_after.used - ram_before.used) / 1024 / 1024
        ram_usage_pct = ram_after.percent

        write_metrics(
            capture_node=image.drone_id,
            image_id=image.image_id,
            orig_w=image.width,
            orig_h=image.height,
            processing_time_ms=processing_time_ms,
            cpu_usage_pct=cpu_usage,
            ram_usage_pct=ram_usage_pct,
            ram_used_mb=ram_used_mb,
        )

        state["processed"] += 1
        log.info(
            f"Processed: {image.image_id} "
            f"({image.width}x{image.height} -> {TARGET_WIDTH}x{TARGET_HEIGHT}) "
            f"in {processing_time_ms:.1f}ms | "
            f"CPU {cpu_usage:.1f}% | "
            f"RAM {ram_usage_pct:.1f}% ({ram_used_mb:+.1f}MB)"
        )

        # Forward to fire-analyser asynchronously — does not block the response
        asyncio.create_task(forward_to_analyser(
            capture_node=image.drone_id,
            image_id=image.image_id,
            width=TARGET_WIDTH,
            height=TARGET_HEIGHT,
            b64_data=b64_processed,
        ))

        return {
            "status":             "ok",
            "image_id":           image.image_id,
            "capture_node":       image.drone_id,
            "processing_node":    PROCESSING_NODE,
            "original_size":      f"{image.width}x{image.height}",
            "processed_size":     f"{TARGET_WIDTH}x{TARGET_HEIGHT}",
            "processing_time_ms": round(processing_time_ms, 3),
            "cpu_usage_pct":      round(cpu_usage, 1),
            "ram_usage_pct":      round(ram_usage_pct, 1),
            "ram_used_mb":        round(ram_used_mb, 1),
        }

    except Exception as e:
        state["errors"] += 1
        log.error(f"Error processing {image.image_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=False)