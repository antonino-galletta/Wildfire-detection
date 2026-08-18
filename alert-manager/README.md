
# Wildfire Alert Manager

Edge microservice for receiving and displaying wildfire alerts. The service exposes a FastAPI-based REST API and a web dashboard with an OpenStreetMap map.

Geographic coordinates of the fire are extracted from the image filename associated with the alert, using the following format:

```text
{lat}_{lon}.png
```

Example:

```text
38.1137_15.3315.png
```

## Features

- Receiving alerts via REST API.
- Automatic extraction of latitude and longitude from the image filename.
- Visualization of alerts on a web dashboard.
- Interactive map based on OpenStreetMap.
- Automatic dashboard refresh every 10 seconds.
- Automatic expiration of alerts older than the configured TTL.
- Health check endpoint.
- In-memory storage of received alerts.

> Alerts are kept in memory only and are lost when the container restarts.

## Docker Image

The Docker image is available on Docker Hub:

[agalletta/wildfire-alert-manager](https://hub.docker.com/r/agalletta/wildfire-alert-manager)

To run the container:

```bash
docker pull agalletta/wildfire-alert-manager:latest

docker run -d \
  --name wildfire-alert-manager \
  -p 8005:8005 \
  agalletta/wildfire-alert-manager:latest
```

The dashboard will be available at:

```text
http://localhost:8005
```

## Configuration

The service behavior can be customized via environment variables:

| Variable | Default | Description |
|---|---:|---|
| `ALERT_NODE` | `unknown` | Identifier of the node managing the alerts. |
| `ALERT_TTL_H` | `24` | Alert lifetime in hours. |
| `MAP_CENTER_LAT` | `38.1137` | Initial latitude of the map. |
| `MAP_CENTER_LON` | `15.3315` | Initial longitude of the map. |
| `MAP_ZOOM` | `10` | Initial zoom level of the map. |

Example:

```bash
docker run -d \
  --name wildfire-alert-manager \
  -p 8005:8005 \
  -e ALERT_NODE=alert-manager-messina \
  -e ALERT_TTL_H=48 \
  -e MAP_CENTER_LAT=38.1137 \
  -e MAP_CENTER_LON=15.3315 \
  -e MAP_ZOOM=10 \
  agalletta/wildfire-alert-manager:latest
```

## API

### Dashboard

```http
GET /
```

Returns the HTML dashboard with the map and the list of recent alerts.

### Health Check

```http
GET /health
```

Example response:

```json
{
  "status": "ok",
  "alert_node": "unknown"
}
```

### List Alerts

```http
GET /alerts
```

Returns the active alerts and their total count.

Example response:

```json
{
  "alerts": [
    {
      "id": 1,
      "image_id": "38.1137_15.3315.png",
      "capture_node": "camera-01",
      "inference_node": "inference-01",
      "confidence": 94.5,
      "timestamp": "2026-08-18T10:00:00",
      "lat": 38.1137,
      "lon": 15.3315
    }
  ],
  "count": 1
}
```

### Receive an Alert

```http
POST /alert
Content-Type: application/json
```

Required payload:

```json
{
  "image_id": "38.1137_15.3315.png",
  "capture_node": "camera-01",
  "inference_node": "inference-01",
  "confidence": 0.945,
  "timestamp": "2026-08-18T10:00:00"
}
```

Example with `curl`:

```bash
curl -X POST http://localhost:8005/alert \
  -H "Content-Type: application/json" \
  -d '{
    "image_id": "38.1137_15.3315.png",
    "capture_node": "camera-01",
    "inference_node": "inference-01",
    "confidence": 0.945,
    "timestamp": "2026-08-18T10:00:00"
  }'
```

Expected response:

```json
{
  "status": "ok",
  "alert_id": 1,
  "lat": 38.1137,
  "lon": 15.3315
}
```

The `confidence` field must be expressed as a decimal value, typically between `0` and `1`; in the API response and on the dashboard it is converted to a percentage.

Supported image formats for coordinate extraction are `.png`, `.jpg`, and `.jpeg`.

If the image filename does not match the expected format, the API returns an HTTP `422` error.

### Clear Alerts

```http
DELETE /alerts
```

Clears all alerts currently stored in memory.

Example:

```bash
curl -X DELETE http://localhost:8005/alerts
```

## Local Execution

To run the service without Docker, Python must be installed.

Install dependencies:

```bash
pip install fastapi uvicorn pydantic
```

Start the application:

```bash
python main.py
```

Alternatively:

```bash
uvicorn main:app --host 0.0.0.0 --port 8005
```

## OpenAPI Documentation

FastAPI automatically generates interactive documentation:

- Swagger UI: `http://localhost:8005/docs`
- ReDoc: `http://localhost:8005/redoc`

## Logical Architecture

The service operates as an alert management component within the wildfire detection pipeline:

1. An acquisition node produces an image.
2. The inference node analyzes the image and determines the fire probability.
3. The system sends a `POST /alert` request to the Alert Manager.
4. The Alert Manager extracts coordinates from the image filename.
5. The alert is stored and displayed on the dashboard.
6. Expired alerts are automatically removed after the configured TTL.

## Operational Notes

- The service uses UTC for calculating alert expiration.
- The numeric alert identifier is sequential with respect to the current in-memory state.
- No persistent database is used in the current implementation.
- OpenStreetMap tile usage requires network connectivity from the client browser.
- For production environments, it is recommended to add authentication, authorization, persistence, stricter timestamp validation, and an HTTPS reverse proxy.

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