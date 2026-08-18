# Shared Models

This directory contains shared Pydantic models used across the wildfire detection microservices. These models ensure consistent data structures and validation for inter-service communication.

## Models

### `RawImage`

The `RawImage` model defines the structure of the HTTP payload sent by the `image-capture` service to the `preprocessor` service. It represents a raw image captured by a drone, including metadata and the image data encoded in base64.

#### Fields

| Field | Type | Description |
|---|---:|---|
| `drone_id` | `str` | Unique identifier of the drone that captured the image. |
| `image_id` | `str` | Unique identifier of the image, typically used for tracking and correlation across services. |
| `timestamp` | `str` | ISO 8601 timestamp indicating when the image was captured. |
| `width` | `int` | Width of the image in pixels. |
| `height` | `int` | Height of the image in pixels. |
| `data` | `str` | Base64-encoded image data. |

#### Example Payload

```json
{
  "drone_id": "drone-01",
  "image_id": "20260818_120000_drone01_img001",
  "timestamp": "2026-08-18T12:00:00Z",
  "width": 1920,
  "height": 1080,
  "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
}
```

#### Usage

The `RawImage` model is used as follows:

```python
from shared.models import RawImage

payload = RawImage(
    drone_id="drone-01",
    image_id="20260818_120000_drone01_img001",
    timestamp="2026-08-18T12:00:00Z",
    width=1920,
    height=1080,
    data="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
```

The model provides automatic validation of field types and can be used directly in FastAPI request/response definitions.

## Directory Structure

```
shared/
├── __init__.py
└── models.py      # Contains RawImage and other shared models
```

## Dependencies

- `pydantic`: Used for data validation and settings management.
- `python`: Version 3.8 or higher recommended.

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