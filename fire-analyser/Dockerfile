FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libglib2.0-0 libgl1 \
    gcc python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Modello incluso direttamente nell'immagine Docker
COPY fire_classifier.pt /var/wildfire/models/fire_classifier.pt

RUN mkdir -p /var/wildfire/output

EXPOSE 8003

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
