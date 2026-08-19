# Wildfire Detection

Wildfire Detection is a modular, microservice-based system for early detection of wildfires using computer vision and edge computing. The architecture is designed to run on resource-constrained edge devices (e.g., drones, edge nodes, or small servers) and to scale to multi-node deployments.

The system ingests images from a simulated drone, preprocesses them, runs YOLO-based fire classification, and displays alerts on a map-based dashboard when fire is detected.

## System Architecture

The project is composed of the following microservices:

- **image-capture** – Simulates a drone that captures images from a local dataset and sends them to the preprocessor.
- **preprocessor** – Receives raw images, resizes them, normalizes brightness using CLAHE, and forwards them to the analyser.
- **fire-analyser** – Performs YOLO-based classification to detect fire and sends alerts to the alert manager when fire is detected.
- **alert-manager** – Stores active alerts and exposes a web dashboard with an OpenStreetMap map showing the simulated location of each alert.

All services communicate over HTTP using JSON payloads and share a common Pydantic model (`RawImage`) for image data.

```text
image-capture  →  preprocessor  →  fire-analyser  →  alert-manager
     ↓                ↓                ↓                ↓
  (dataset)      (resize +        (YOLO fire         (dashboard +
                 CLAHE)            classification)     map)
```

## Microservices

### image-capture

Simulates a drone that captures images from a local directory and sends them to the preprocessor.

- Reads images from a configurable folder.
- Generates deterministic simulated GPS coordinates from the filename.
- Sends images as base64-encoded payloads to the preprocessor.
- Exposes health and status endpoints.

**Docker image:**  
[agalletta/wildfire-image-capture](https://hub.docker.com/r/agalletta/wildfire-image-capture)

**Documentation:**  
See `image-capture/README.md`.

### preprocessor

Receives raw images, preprocesses them, and forwards them to the fire analyser.

- Resizes images to a configurable resolution (default 640×�80).
- Applies CLAHE brightness normalization in LAB color space.
- Saves processed images and metrics to disk.
- Forwards processed images asynchronously to the analyser.

**Docker image:**  
[agalletta/wildfire-preprocessor](https://hub.docker.com/repository/docker/agalletta/wildfire-preprocessor)

**Documentation:**  
See `preprocessor/README.md`.

### fire-analyser

Performs fire classification on preprocessed images using a YOLO model.

- Loads a YOLO classification model (e.g., `fire_classifier.pt`).
- Classifies images as `fire` or `nofire`.
- Applies a configurable confidence threshold.
- Sends fire alerts asynchronously to the alert manager.
- Records inference metrics (time, CPU, RAM) in a CSV file.

**Pre-trained model:**  
A trained YOLO classification model is available in this repository:  
[fire-analyser/fire_classifier.pt](https://github.com/antonino-galletta/Wildfire-detection/blob/main/fire-analyser/fire_classifier.pt)

**Docker image:**  
[agalletta/wildfire-fire-analyser](https://hub.docker.com/repository/docker/agalletta/wildfire-fire-analyser)

**Documentation:**  
See `fire-analyser/README.md`.

### alert-manager

Stores active alerts and provides a web dashboard with a map.

- Receives fire alerts from the analyser.
- Extracts simulated GPS coordinates from the image identifier.
- Stores alerts in memory with a configurable TTL.
- Exposes a dashboard with an OpenStreetMap map.
- Provides REST endpoints for health, alerts, and management.

**Docker image:**  
[agalletta/wildfire-alert-manager](https://hub.docker.com/r/agalletta/wildfire-alert-manager)

**Documentation:**  
See `alert-manager/README.md`.

## Shared Models

The `shared/` directory contains common Pydantic models used across services.

- `RawImage` – Defines the structure of the image payload sent from `image-capture` to `preprocessor`.

**Documentation:**  
See `shared/README.md`.

## Dataset

The images used to simulate drone captures are taken from [The Wildfire Dataset on Kaggle](https://www.kaggle.com/datasets/elmadafri/the-wildfire-dataset).

To use the dataset:

1. Download the dataset from Kaggle.
2. Place the images in a local directory.
3. Mount this directory into the `image-capture` container (e.g., `/images`).

## Quick Start

### Prerequisites

- Docker and Docker Compose.
- A YOLO classification model compatible with Ultralytics.  
  A pre-trained model is provided in this repository at:  
  [fire-analyser/fire_classifier.pt](https://github.com/antonino-galletta/Wildfire-detection/blob/main/fire-analyser/fire_classifier.pt)
- A directory containing wildfire images.

### Environment Variables

Each service is configured via environment variables. Typical variables include:

- `DRONE_ID`, `IMAGES_DIR`, `INTERVAL_SECONDS` (image-capture)
- `TARGET_WIDTH`, `TARGET_HEIGHT`, `FIRE_ANALYSER_URL` (preprocessor)
- `MODEL_PATH`, `CONFIDENCE_THR`, `ALERT_MANAGER_URL` (fire-analyser)
- `ALERT_NODE`, `ALERT_TTL_H`, `MAP_CENTER_LAT`, `MAP_CENTER_LON` (alert-manager)

Refer to the individual service README files for detailed configuration options.

### Running with Docker Compose

Create a `docker-compose.yml` file similar to the following (adapt paths and environment variables as needed):

```yaml
services:
  image-capture:
    image: agalletta/wildfire-image-capture:latest
    ports:
      - "8001:8001"
    volumes:
      - /path/to/images:/images:ro
    environment:
      - DRONE_ID=drone-1
      - IMAGES_DIR=/images
      - INTERVAL_SECONDS=3
      - PREPROCESSOR_URL=http://preprocessor:8002
    depends_on:
      - preprocessor

  preprocessor:
    image: agalletta/wildfire-preprocessor:latest
    ports:
      - "8002:8002"
    volumes:
      - /path/to/output:/var/wildfire/output
    environment:
      - PROCESSING_NODE=preprocessor-01
      - TARGET_WIDTH=640
      - TARGET_HEIGHT=480
      - FIRE_ANALYSER_URL=http://fire-analyser:8003
    depends_on:
      - fire-analyser

  fire-analyser:
    image: agalletta/wildfire-fire-analyser:latest
    ports:
      - "8003:8003"
    volumes:
      - /path/to/models:/var/wildfire/models:ro
      - /path/to/output:/var/wildfire/output
    environment:
      - INFERENCE_NODE=fire-analyser-01
      - MODEL_PATH=/var/wildfire/models/fire_classifier.pt
      - CONFIDENCE_THR=0.5
      - ALERT_MANAGER_URL=http://alert-manager:8005
    depends_on:
      - alert-manager

  alert-manager:
    image: agalletta/wildfire-alert-manager:latest
    ports:
      - "8005:8000"
    environment:
      - ALERT_NODE=alert-manager-01
      - ALERT_TTL_H=24
      - MAP_CENTER_LAT=38.1137
      - MAP_CENTER_LON=15.3315
      - MAP_ZOOM=10
```

Start the stack:

```bash
docker compose up -d
```

Access the dashboard at:

```text
http://localhost:8005
```

Check service logs:

```bash
docker compose logs -f
```

## API Overview

Each microservice exposes a FastAPI-based REST API with automatic OpenAPI documentation.

- `image-capture`: `http://localhost:8001/docs`
- `preprocessor`: `http://localhost:8002/docs`
- `fire-analyser`: `http://localhost:8003/docs`
- `alert-manager`: `http://localhost:8005/docs`

Key endpoints:

- `POST /preprocess` – Preprocess a raw image.
- `POST /analyse` – Run fire classification on a preprocessed image.
- `POST /alert` – Register a fire alert.
- `GET /status` and `GET /health` – Monitoring endpoints for each service.

## Metrics and Logging

Each service logs structured messages to stdout and writes operational metrics to CSV files:

- `preprocessor`: `/var/wildfire/output/metrics.csv`
- `fire-analyser`: `/var/wildfire/output/inference_metrics.csv`

Metrics include:

- Timestamps and node identifiers.
- Image dimensions and processing times.
- CPU and RAM usage.
- Predicted class, confidence, and fire detection flag.

Mount `/var/wildfire/output` as a Docker volume to persist metrics.

## Extending the System

The modular design allows several possible extensions:

- Replace the simulated `image-capture` with a real camera or drone stream.
- Add authentication and authorization between services.
- Integrate a persistent database or message queue.
- Deploy on Kubernetes or other orchestration platforms.
- Add additional analyser nodes for horizontal scaling.
- Integrate federated learning for collaborative model training across edge nodes.

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