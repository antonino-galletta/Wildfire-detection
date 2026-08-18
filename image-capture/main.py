"""
image_capture — edge microservice
Reads images from a local folder one at a time every INTERVAL_SECONDS
and sends them to the preprocessor microservice via HTTP POST.
Each image is assigned deterministic GPS coordinates based on its filename hash,
formatted as {lat}_{lon}.ext — same file always produces the same coordinates.
"""

import asyncio
import base64
import hashlib
import io
import logging
import os
import random
from datetime import datetime
from pathlib import Path

import httpx
from PIL import Image
from fastapi import FastAPI
import uvicorn

import sys
sys.path.append("/app/shared")
from models import RawImage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("image-capture")

app = FastAPI(title="Image Capture")

DRONE_ID         = os.getenv("DRONE_ID",         "drone-1")
IMAGES_DIR       = os.getenv("IMAGES_DIR",       "/images")
INTERVAL_SECONDS = float(os.getenv("INTERVAL_SECONDS", "3.0"))
PREPROCESSOR_URL = os.getenv("PREPROCESSOR_URL", "http://preprocessor:8002")

# Bounding box for Sicily (realistic coordinates)
LAT_MIN = float(os.getenv("LAT_MIN", "36.6"))
LAT_MAX = float(os.getenv("LAT_MAX", "38.3"))
LON_MIN = float(os.getenv("LON_MIN", "11.9"))
LON_MAX = float(os.getenv("LON_MAX", "15.7"))

state = {"running": False, "sent": 0, "errors": 0, "last_image": None}


def generate_coordinates(filename: str) -> tuple[float, float]:
    """
    Generates deterministic lat/lon coordinates from the filename hash.
    Same filename always produces the same coordinates.
    Uses SHA256 hash as seed for the random generator.
    """
    seed = int(hashlib.sha256(filename.encode()).hexdigest(), 16) % (2**32)
    rng  = random.Random(seed)
    lat  = round(rng.uniform(LAT_MIN, LAT_MAX), 4)
    lon  = round(rng.uniform(LON_MIN, LON_MAX), 4)
    return lat, lon


def build_geo_image_id(path: Path) -> str:
    """
    Returns image_id in the format {lat}_{lon}.ext
    e.g. 38.1137_15.3315.jpg
    """
    lat, lon = generate_coordinates(path.name)
    return f"{lat}_{lon}{path.suffix.lower()}"


def load_image_list() -> list[Path]:
    folder     = Path(IMAGES_DIR)
    extensions = {".jpg", ".jpeg", ".png", ".bmp"}
    return sorted([f for f in folder.iterdir() if f.suffix.lower() in extensions])


def encode_image(path: Path) -> tuple[int, int, str]:
    """Opens the original image and encodes it in base64 without resizing."""
    with Image.open(path) as img:
        img    = img.convert("RGB")
        width, height = img.size
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return width, height, b64


async def send_image(path: Path) -> bool:
    try:
        width, height, b64 = encode_image(path)
        image_id = build_geo_image_id(path)

        payload = {
            "drone_id":  DRONE_ID,
            "image_id":  image_id,
            "timestamp": datetime.utcnow().isoformat(),
            "width":     width,
            "height":    height,
            "data":      b64,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{PREPROCESSOR_URL}/preprocess",
                json=payload,
            )
            response.raise_for_status()
            log.info(f"Sent: {path.name} → {image_id} ({width}x{height}) "
                     f"status={response.status_code}")
            return True
    except httpx.ConnectError:
        log.warning(f"Preprocessor unreachable ({PREPROCESSOR_URL})")
        return False
    except Exception as e:
        log.error(f"Error sending {path.name}: {e}")
        return False


async def capture_loop():
    log.info(f"Starting capture loop | dir={IMAGES_DIR} | interval={INTERVAL_SECONDS}s")
    state["running"] = True
    while state["running"]:
        images = load_image_list()
        if not images:
            log.warning(f"No images found in {IMAGES_DIR}, retrying in {INTERVAL_SECONDS}s")
            await asyncio.sleep(INTERVAL_SECONDS)
            continue
        for path in images:
            if not state["running"]:
                break
            state["last_image"] = path.name
            ok = await send_image(path)
            if ok:
                state["sent"] += 1
            else:
                state["errors"] += 1
            await asyncio.sleep(INTERVAL_SECONDS)
        log.info("Folder complete, restarting from the beginning")


@app.on_event("startup")
async def startup():
    asyncio.create_task(capture_loop())


@app.get("/health")
async def health():
    return {"status": "ok", "drone_id": DRONE_ID}


@app.get("/status")
async def status():
    return {
        "drone_id":        DRONE_ID,
        "running":         state["running"],
        "images_sent":     state["sent"],
        "errors":          state["errors"],
        "last_image":      state["last_image"],
        "interval_seconds": INTERVAL_SECONDS,
        "bbox": {
            "lat": [LAT_MIN, LAT_MAX],
            "lon": [LON_MIN, LON_MAX],
        }
    }


@app.post("/stop")
async def stop():
    state["running"] = False
    return {"status": "stopped"}


@app.post("/start")
async def start():
    if not state["running"]:
        asyncio.create_task(capture_loop())
    return {"status": "started"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False)