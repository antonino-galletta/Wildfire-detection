# Wildfire Fire Analyser

`Wildfire Fire Analyser` is an edge/cloud microservice that receives preprocessed images, performs fire classification using a YOLOv8 classification model, records inference metrics, and asynchronously sends alerts to the `alert-manager` service when fire is detected.

## Docker Image

The Docker image is available at:

[agalletta/wildfire-fire-analyser](https://hub.docker.com/repository/docker/agalletta/wildfire-fire-analyser)

Pull the image with:

```bash
docker pull agalletta/wildfire-fire-analyser:latest
```

## Features

- Receives preprocessed images through an HTTP API.
- Decodes base64-encoded JPEG images.
- Runs YOLOv8 image classification inference.
- Detects fire according to the predicted class and a configurable confidence threshold.
- Sends fire alerts asynchronously to the Alert Manager.
- Records inference and resource-usage metrics in a CSV file.
- Exposes health and status endpoints.
- Provides automatic OpenAPI documentation through FastAPI.

## Processing Flow

1. The `preprocessor` sends a processed image to `POST /analyse`.
2. The analyser decodes the base64 image payload.
3. The YOLO classification model predicts a class and confidence score.
4. The result is classified as fire or no fire.
5. CPU, memory, and inference-time metrics are collected.
6. The inference result is appended to `inference_metrics.csv`.
7. If fire is detected, an alert is sent asynchronously to the configured Alert Manager.
8. The analysis result is returned to the caller.

## Model Requirements

The service expects a YOLO model file at the path configured by `MODEL_PATH`.

Default path:

```text
/var/wildfire/models/fire_classifier.pt
```

The model must be compatible with the Ultralytics YOLO classification API and should expose a class named `fire` for fire detections.

## Configuration

The service is configured through environment variables:

| Variable | Default | Description |
|---|---:|---|
| `MODEL_PATH` | `/var/wildfire/models/fire_classifier.pt` | Path to the YOLO classification model. |
| `OUTPUT_DIR` | `/var/wildfire/output` | Directory where inference metrics are stored. |
| `INFERENCE_NODE` | `unknown` | Identifier of the node running inference. |
| `CONFIDENCE_THR` | `0.5` | Minimum confidence required for a fire detection. |
| `ALERT_MANAGER_URL` | `http://alert-manager:8005` | Base URL of the Alert Manager. Alerts are sent to `{ALERT_MANAGER_URL}/alert`. |

A fire is considered detected only when both conditions are true:

```text
predicted_class == "fire"
confidence >= CONFIDENCE_THR
```

## Docker Usage

The following example assumes that the model is available locally and that the Alert Manager is reachable through the Docker network:

```bash
docker run -d \
  --name wildfire-fire-analyser \
  -p 8003:8003 \
  -v /path/to/models:/var/wildfire/models:ro \
  -v /path/to/output:/var/wildfire/output \
  -e MODEL_PATH=/var/wildfire/models/fire_classifier.pt \
  -e INFERENCE_NODE=fire-analyser-01 \
  -e CONFIDENCE_THR=0.5 \
  -e ALERT_MANAGER_URL=http://alert-manager:8005 \
  agalletta/wildfire-fire-analyser:latest
```

Replace `/path/to/models` and `/path/to/output` with suitable local paths.

If the analyser and Alert Manager are running as separate containers, attach them to the same Docker network. For example:

```bash
docker network create wildfire-network
```

Then run both services with:

```bash
docker run -d \
  --name wildfire-fire-analyser \
  --network wildfire-network \
  -p 8003:8003 \
  -v /path/to/models:/var/wildfire/models:ro \
  -v /path/to/output:/var/wildfire/output \
  -e ALERT_MANAGER_URL=http://alert-manager:8005 \
  agalletta/wildfire-fire-analyser:latest
```

## Input API

### Analyse an Image

```http
POST /analyse
Content-Type: application/json
```

The request body must contain a preprocessed image with the following structure:

```json
{
  "capture_node": "drone-1",
  "processing_node": "preprocessor-1",
  "image_id": "38.1137_15.3315.jpg",
  "width": 640,
  "height": 480,
  "data": "<base64-encoded JPEG image>"
}
```

| Field | Type | Description |
|---|---:|---|
| `capture_node` | `string` | Identifier of the node that captured the image. |
| `processing_node` | `string` | Identifier of the node that performed preprocessing. |
| `image_id` | `string` | Image identifier. |
| `width` | `integer` | Image width in pixels. |
| `height` | `integer` | Image height in pixels. |
| `data` | `string` | Base64-encoded JPEG image, normally resized to 640×480 by the preprocessor. |

Example request:

```bash
curl -X POST http://localhost:8003/analyse \
  -H "Content-Type: application/json" \
  -d '{
    "capture_node": "drone-1",
    "processing_node": "preprocessor-1",
    "image_id": "38.1137_15.3315.jpg",
    "width": 640,
    "height": 480,
    "data": "<base64-encoded-JPEG>"
  }'
```

Example response:

```json
{
  "image_id": "38.1137_15.3315.jpg",
  "capture_node": "drone-1",
  "processing_node": "preprocessor-1",
  "inference_node": "fire-analyser-01",
  "predicted_class": "fire",
  "confidence": 0.9342,
  "fire_detected": true,
  "inference_time_ms": 42.781,
  "cpu_usage_pct": 28.4,
  "ram_usage_pct": 51.2,
  "ram_used_mb": 12.6
}
```

The endpoint returns HTTP `503` if the model has not been loaded and HTTP `500` if an error occurs while decoding or analysing the image.

## Alert Manager Integration

When an image is classified as fire with sufficient confidence, the service sends an asynchronous request to:

```http
POST {ALERT_MANAGER_URL}/alert
Content-Type: application/json
```

Payload:

```json
{
  "image_id": "38.1137_15.3315.jpg",
  "capture_node": "drone-1",
  "inference_node": "fire-analyser-01",
  "confidence": 0.9342,
  "timestamp": "2026-08-19T08:00:00.000000"
}
```

The alert request is performed asynchronously so that alert delivery does not block the response to the image-analysis request.

## Monitoring Endpoints

### Health Check

```http
GET /health
```

Returns the service status, inference node, model status, and configured model path.

Example:

```bash
curl http://localhost:8003/health
```

### Runtime Status

```http
GET /status
```

Returns counters and configuration information:

- Number of received images.
- Number of fire detections.
- Number of no-fire results.
- Number of processing errors.
- Number of alerts sent successfully.
- Fire detection rate.
- Model-loading status.
- Confidence threshold.
- Alert Manager URL.

Example:

```bash
curl http://localhost:8003/status
```

## Metrics

Metrics are saved to:

```text
${OUTPUT_DIR}/inference_metrics.csv
```

With the default configuration:

```text
/var/wildfire/output/inference_metrics.csv
```

The CSV file contains:

| Column | Description |
|---|---|
| `timestamp` | UTC timestamp of the inference. |
| `capture_node` | Image capture node. |
| `processing_node` | Preprocessing node. |
| `inference_node` | Inference node. |
| `image_id` | Image identifier. |
| `image_width` | Image width. |
| `image_height` | Image height. |
| `predicted_class` | Class predicted by the model. |
| `confidence` | Model confidence score. |
| `fire_detected` | `1` when fire is detected, otherwise `0`. |
| `inference_time_ms` | Inference duration in milliseconds. |
| `cpu_usage_pct` | CPU usage measured during inference. |
| `ram_usage_pct` | System RAM usage after inference. |
| `ram_used_mb` | Approximate RAM variation measured during inference. |

A volume should be mounted on `/var/wildfire/output` if the metrics need to survive container restarts.

## Local Execution

Install the Python dependencies:

```bash
pip install fastapi uvicorn httpx psutil pillow pydantic ultralytics
```

Set the required environment variables:

```bash
export MODEL_PATH=/path/to/fire_classifier.pt
export OUTPUT_DIR=/tmp/wildfire-output
export ALERT_MANAGER_URL=http://localhost:8005
```

Start the service:

```bash
python main.py
```

The API listens on:

```text
http://localhost:8003
```

## OpenAPI Documentation

FastAPI automatically provides interactive API documentation:

- Swagger UI: `http://localhost:8003/docs`
- ReDoc: `http://localhost:8003/redoc`

## Operational Notes

- The model is loaded during application startup. If the model file is missing or invalid, startup fails.
- Alert delivery is asynchronous and errors are logged without changing the inference response already being processed.
- Runtime counters are stored in memory and reset when the service restarts.
- Metrics are appended to a local CSV file and require a mounted volume for persistence across container restarts.
- The service expects the classifier to use the class label `fire`; if a different label is used, update the detection condition in `main.py`.

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