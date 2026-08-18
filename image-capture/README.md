# Wildfire Image Capture

`Wildfire Image Capture` is an edge microservice that simulates a drone taking images during a wildfire-monitoring mission. Instead of acquiring frames from a physical camera, it reads images sequentially from a local directory, assigns each image a simulated geographic position, and sends it to the `preprocessor` microservice over HTTP.

The images used by this service are taken from [The Wildfire Dataset on Kaggle](https://www.kaggle.com/datasets/elmadafri/the-wildfire-dataset).

## How It Works

When the service starts, it launches a background capture loop that:

1. Loads supported image files from the configured local directory.
2. Reads one image at a time.
3. Converts the image to RGB and JPEG-encodes it.
4. Base64-encodes the resulting JPEG data.
5. Generates simulated GPS coordinates within a configurable bounding box.
6. Builds an `image_id` in the form `{latitude}_{longitude}.{extension}`.
7. Sends the image metadata and encoded content to the `preprocessor` service through `POST /preprocess`.
8. Waits for the configured interval before processing the next image.

After all files have been processed, the service restarts from the beginning of the directory.

## Simulated Drone Position

The microservice simulates the drone position by generating pseudo-random latitude and longitude values from the image filename. The implementation uses the SHA-256 hash of the filename as the seed for a local random generator.

Therefore, the coordinates appear random across different images but are deterministic: the same file always receives the same simulated location. By default, coordinates are generated inside a bounding box covering Sicily.

Example generated image identifier:

```text
38.1137_15.3315.jpg
```

This identifier enables downstream microservices to retrieve the simulated location directly from the image name.

## Docker Image

The container image is available on Docker Hub:

[agalletta/wildfire-image-capture](https://hub.docker.com/r/agalletta/wildfire-image-capture)

Pull the image:

```bash
docker pull agalletta/wildfire-image-capture:latest
```

Run the container, mounting a local directory containing the dataset images:

```bash
docker run -d \
  --name wildfire-image-capture \
  -p 8001:8001 \
  -v /path/to/images:/images:ro \
  -e PREPROCESSOR_URL=http://preprocessor:8002 \
  agalletta/wildfire-image-capture:latest
```

Replace `/path/to/images` with the absolute path to the local directory containing the downloaded dataset images.

> If the preprocessor runs in another Docker container, both containers should normally be attached to the same Docker network and `PREPROCESSOR_URL` should use the preprocessor container or service name.

## Configuration

Configure the service using environment variables:

| Variable | Default | Description |
|---|---:|---|
| `DRONE_ID` | `drone-1` | Identifier of the simulated drone. |
| `IMAGES_DIR` | `/images` | Local directory from which images are read. |
| `INTERVAL_SECONDS` | `3.0` | Delay, in seconds, between two image submissions. |
| `PREPROCESSOR_URL` | `http://preprocessor:8002` | Base URL of the preprocessor microservice. The service posts data to `{PREPROCESSOR_URL}/preprocess`. |
| `LAT_MIN` | `36.6` | Minimum latitude of the simulated bounding box. |
| `LAT_MAX` | `38.3` | Maximum latitude of the simulated bounding box. |
| `LON_MIN` | `11.9` | Minimum longitude of the simulated bounding box. |
| `LON_MAX` | `15.7` | Maximum longitude of the simulated bounding box. |

Example with custom settings:

```bash
docker run -d \
  --name wildfire-image-capture \
  -p 8001:8001 \
  -v /path/to/wildfire-dataset:/images:ro \
  -e DRONE_ID=drone-sicily-01 \
  -e INTERVAL_SECONDS=5 \
  -e PREPROCESSOR_URL=http://preprocessor:8002 \
  -e LAT_MIN=36.6 \
  -e LAT_MAX=38.3 \
  -e LON_MIN=11.9 \
  -e LON_MAX=15.7 \
  agalletta/wildfire-image-capture:latest
```

## Payload Format

For each image, the service sends a payload compatible with the shared `RawImage` Pydantic model:

```json
{
  "drone_id": "drone-1",
  "image_id": "38.1137_15.3315.jpg",
  "timestamp": "2026-08-18T12:00:00.000000",
  "width": 1920,
  "height": 1080,
  "data": "<base64-encoded JPEG image>"
}
```

| Field | Type | Description |
|---|---:|---|
| `drone_id` | `string` | Identifier of the simulated drone. |
| `image_id` | `string` | Generated identifier in the `{lat}_{lon}.{extension}` format. |
| `timestamp` | `string` | UTC timestamp generated when the image is sent. |
| `width` | `integer` | Original image width in pixels. |
| `height` | `integer` | Original image height in pixels. |
| `data` | `string` | Base64-encoded JPEG representation of the image. |

## API

The service exposes the following endpoints on port `8001`.

### Health Check

```http
GET /health
```

Example response:

```json
{
  "status": "ok",
  "drone_id": "drone-1"
}
```

### Capture Status

```http
GET /status
```

Returns the status of the capture loop, counters for sent images and errors, the last processed image, the interval, and the active coordinate bounding box.

Example request:

```bash
curl http://localhost:8001/status
```

### Stop Capture

```http
POST /stop
```

Stops the background capture loop.

```bash
curl -X POST http://localhost:8001/stop
```

### Start Capture

```http
POST /start
```

Starts the capture loop if it is not already running.

```bash
curl -X POST http://localhost:8001/start
```

## Supported Formats

The service scans `IMAGES_DIR` for files with the following extensions:

- `.jpg`
- `.jpeg`
- `.png`
- `.bmp`

Regardless of the original input format, the image is converted to RGB and transmitted as a JPEG-encoded, base64 string.

## Local Execution

Install the Python dependencies:

```bash
pip install fastapi uvicorn httpx pillow pydantic
```

Ensure the shared models are importable and set the required environment variables:

```bash
export IMAGES_DIR=/path/to/images
export PREPROCESSOR_URL=http://localhost:8002
```

Start the service:

```bash
python main.py
```

The API will be available at:

```text
http://localhost:8001
```

## OpenAPI Documentation

FastAPI automatically provides interactive API documentation:

- Swagger UI: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`

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