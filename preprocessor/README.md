# Wildfire Preprocessor

`Wildfire Preprocessor` is an edge microservice that receives raw images from the `image-capture` service, preprocesses them, stores the processed files and forwards them asynchronously to the `fire-analyser` microservice.

The service is implemented with FastAPI and processes images using OpenCV, NumPy and Pillow.

## Docker Image

The Docker image is available at:

[agalletta/wildfire-preprocessor](https://hub.docker.com/repository/docker/agalletta/wildfire-preprocessor)

Pull the image with:

```bash
docker pull agalletta/wildfire-preprocessor:latest
```

## Features

- Receives raw images through an HTTP API.
- Validates incoming payloads using the shared `RawImage` Pydantic model.
- Decodes base64-encoded image data.
- Resizes images to a configurable target resolution.
- Normalizes image brightness using CLAHE in the LAB color space.
- Re-encodes processed images as JPEG.
- Saves processed images to a local output directory.
- Records processing and resource-usage metrics in a CSV file.
- Forwards processed images asynchronously to `fire-analyser`.
- Exposes health and runtime status endpoints.

## Processing Flow

1. `image-capture` sends a raw image to `POST /preprocess`.
2. The service validates the request using the `RawImage` model.
3. The base64 image is decoded into an OpenCV image.
4. The image is resized to the configured target resolution.
5. CLAHE brightness normalization is applied.
6. The processed image is JPEG-encoded and converted to base64.
7. A local copy of the processed image is saved.
8. Processing metrics are appended to `metrics.csv`.
9. The processed image is forwarded asynchronously to `fire-analyser`.
10. The preprocessing result is returned to the caller.

## Configuration

The service is configured using environment variables:

| Variable | Default | Description |
|---|---:|---|
| `TARGET_WIDTH` | `640` | Output image width in pixels. |
| `TARGET_HEIGHT` | `480` | Output image height in pixels. |
| `JPEG_QUALITY` | `85` | JPEG encoding quality for the processed image. |
| `OUTPUT_DIR` | `/var/wildfire/output` | Directory for processed images and metrics. |
| `PROCESSING_NODE` | `unknown` | Identifier of the preprocessing node. |
| `FIRE_ANALYSER_URL` | `http://fire-analyser:8003` | Base URL of the fire analyser. The image is sent to `{FIRE_ANALYSER_URL}/analyse`. |

## Docker Usage

The following command runs the service on port `8002` and persists processed files and metrics on the host:

```bash
docker run -d \
  --name wildfire-preprocessor \
  -p 8002:8002 \
  -v /path/to/output:/var/wildfire/output \
  -e PROCESSING_NODE=preprocessor-01 \
  -e FIRE_ANALYSER_URL=http://fire-analyser:8003 \
  agalletta/wildfire-preprocessor:latest
```

Replace `/path/to/output` with the path where processed images and metrics should be stored.

If the preprocessor and fire analyser run in separate Docker containers, attach them to the same Docker network. For example:

```bash
docker network create wildfire-network
```

Start the preprocessor on that network:

```bash
docker run -d \
  --name wildfire-preprocessor \
  --network wildfire-network \
  -p 8002:8002 \
  -v /path/to/output:/var/wildfire/output \
  -e PROCESSING_NODE=preprocessor-01 \
  -e FIRE_ANALYSER_URL=http://fire-analyser:8003 \
  agalletta/wildfire-preprocessor:latest
```

## Input Payload

The `POST /preprocess` endpoint accepts the shared `RawImage` model:

```json
{
  "drone_id": "drone-1",
  "image_id": "38.1137_15.3315.jpg",
  "timestamp": "2026-08-19T08:00:00.000000",
  "width": 1920,
  "height": 1080,
  "data": "<base64-encoded image>"
}
```

| Field | Type | Description |
|---|---:|---|
| `drone_id` | `string` | Identifier of the image-capture or drone node. |
| `image_id` | `string` | Image identifier. |
| `timestamp` | `string` | Timestamp associated with image capture. |
| `width` | `integer` | Original image width in pixels. |
| `height` | `integer` | Original image height in pixels. |
| `data` | `string` | Base64-encoded image data. |

## API

### Preprocess an Image

```http
POST /preprocess
Content-Type: application/json
```

Example request:

```bash
curl -X POST http://localhost:8002/preprocess \
  -H "Content-Type: application/json" \
  -d '{
    "drone_id": "drone-1",
    "image_id": "38.1137_15.3315.jpg",
    "timestamp": "2026-08-19T08:00:00.000000",
    "width": 1920,
    "height": 1080,
    "data": "<base64-encoded-image>"
  }'
```

Example response:

```json
{
  "status": "ok",
  "image_id": "38.1137_15.3315.jpg",
  "capture_node": "drone-1",
  "processing_node": "preprocessor-01",
  "original_size": "1920x1080",
  "processed_size": "640x480",
  "processing_time_ms": 18.421,
  "cpu_usage_pct": 24.7,
  "ram_usage_pct": 48.3,
  "ram_used_mb": 4.8
}
```

The response is returned after local preprocessing and metric recording. Forwarding to `fire-analyser` is performed asynchronously and does not block the HTTP response.

### Health Check

```http
GET /health
```

Example:

```bash
curl http://localhost:8002/health
```

Response:

```json
{
  "status": "ok",
  "processing_node": "preprocessor-01"
}
```

### Runtime Status

```http
GET /status
```

Returns counters and configuration details, including:

- Number of received images.
- Number of successfully processed images.
- Number of images forwarded to the analyser.
- Number of processing errors.
- Target resolution.
- Fire analyser URL.
- Metrics file path.

Example:

```bash
curl http://localhost:8002/status
```

## Forwarded Payload

After preprocessing, the service sends the following structure to:

```http
POST {FIRE_ANALYSER_URL}/analyse
```

```json
{
  "capture_node": "drone-1",
  "processing_node": "preprocessor-01",
  "image_id": "38.1137_15.3315.jpg",
  "width": 640,
  "height": 480,
  "data": "<base64-encoded processed JPEG>"
}
```

The payload is compatible with the `ProcessedImage` model expected by the fire analyser.

## Image Processing

### Resizing

Every input image is resized to:

```text
640 × 480 pixels
```

unless `TARGET_WIDTH` or `TARGET_HEIGHT` is changed.

### Brightness Normalization

The service applies Contrast Limited Adaptive Histogram Equalization (CLAHE) to the luminance channel of the image in LAB color space. This improves local contrast and helps normalize brightness variations before classification.

### JPEG Encoding

Processed images are encoded as JPEG using the configured `JPEG_QUALITY` value and then base64-encoded for transmission to the analyser.

## Metrics and Output Files

The output directory contains:

- Processed image files named `processed_{image_id}`.
- `metrics.csv`, containing preprocessing and resource-usage measurements.

Default metrics path:

```text
/var/wildfire/output/metrics.csv
```

The CSV columns are:

| Column | Description |
|---|---|
| `timestamp` | UTC timestamp of processing. |
| `capture_node` | Source capture node. |
| `processing_node` | Preprocessing node. |
| `image_id` | Image identifier. |
| `original_width` | Original image width. |
| `original_height` | Original image height. |
| `processed_width` | Output image width. |
| `processed_height` | Output image height. |
| `processing_time_ms` | Processing duration in milliseconds. |
| `cpu_usage_pct` | CPU usage measured during processing. |
| `ram_usage_pct` | System RAM usage after processing. |
| `ram_used_mb` | Approximate RAM variation during processing. |

Mount `/var/wildfire/output` as a Docker volume if the files must survive container restarts.

## Local Execution

Install the dependencies:

```bash
pip install fastapi uvicorn numpy opencv-python httpx psutil pillow pydantic
```

Ensure that the shared models package is available and configure the analyser URL:

```bash
export FIRE_ANALYSER_URL=http://localhost:8003
export OUTPUT_DIR=/tmp/wildfire-output
```

Start the service:

```bash
python main.py
```

The API listens on:

```text
http://localhost:8002
```

## OpenAPI Documentation

FastAPI automatically provides interactive documentation:

- Swagger UI: `http://localhost:8002/docs`
- ReDoc: `http://localhost:8002/redoc`

## Operational Notes

- Image forwarding is asynchronous; an unreachable analyser is logged but does not change the already returned preprocessing response.
- Runtime counters are stored in memory and reset when the service restarts.
- Processed images and metrics require a mounted output volume for persistence.
- Invalid base64 data or unreadable images result in HTTP `500`.
- The service uses UTC timestamps for processing metrics.

## License

Copyright 2026

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.