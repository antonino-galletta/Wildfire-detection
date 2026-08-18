from pydantic import BaseModel
from datetime import datetime


class RawImage(BaseModel):
    drone_id: str
    image_id: str          # nome del file, es. "frame_001.jpg"
    timestamp: datetime
    width: int
    height: int
    data: str              # immagine codificata in base64
