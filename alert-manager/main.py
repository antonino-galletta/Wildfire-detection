"""
alert-manager — edge microservice
Receives fire alerts from fire-analyser and displays them on a dashboard
with an OpenStreetMap map. Coordinates are extracted from the image filename
in the format {lat}_{lon}.png (e.g. 38.1137_15.3315.png).
Alerts expire after 24 hours.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("alert-manager")

app = FastAPI(title="Alert Manager")

ALERT_NODE     = os.getenv("ALERT_NODE",     "unknown")
ALERT_TTL_H    = int(os.getenv("ALERT_TTL_H", "24"))
MAP_CENTER_LAT = float(os.getenv("MAP_CENTER_LAT", "38.1137"))
MAP_CENTER_LON = float(os.getenv("MAP_CENTER_LON", "15.3315"))
MAP_ZOOM       = int(os.getenv("MAP_ZOOM", "10"))

# In-memory alert store
alerts: List[dict] = []


# ── Models ────────────────────────────────────────────────────────

class FireAlert(BaseModel):
    image_id:       str
    capture_node:   str
    inference_node: str
    confidence:     float
    timestamp:      str


# ── Helpers ───────────────────────────────────────────────────────

def parse_coordinates(image_id: str):
    """
    Extracts lat/lon from filename in the format {lat}_{lon}.png
    e.g. 38.1137_15.3315.png -> (38.1137, 15.3315)
    """
    try:
        name = image_id.replace(".png", "").replace(".jpg", "").replace(".jpeg", "")
        parts = name.split("_")
        if len(parts) >= 2:
            lat = float(parts[0])
            lon = float(parts[1])
            return lat, lon
    except Exception:
        pass
    return None, None


def purge_expired():
    """Removes alerts older than ALERT_TTL_H hours."""
    global alerts
    cutoff = datetime.utcnow() - timedelta(hours=ALERT_TTL_H)
    before = len(alerts)
    alerts = [a for a in alerts
              if datetime.fromisoformat(a["timestamp"]) > cutoff]
    removed = before - len(alerts)
    if removed > 0:
        log.info(f"Removed {removed} expired alerts")


# ── API Endpoints ─────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "alert_node": ALERT_NODE}


@app.get("/alerts")
async def get_alerts():
    purge_expired()
    return {"alerts": alerts, "count": len(alerts)}


@app.post("/alert")
async def receive_alert(alert: FireAlert):
    purge_expired()

    lat, lon = parse_coordinates(alert.image_id)
    if lat is None:
        log.warning(f"Invalid coordinates for image_id={alert.image_id}")
        raise HTTPException(
            status_code=422,
            detail=f"Cannot extract coordinates from image_id='{alert.image_id}'. "
                   f"Expected format: {{lat}}_{{lon}}.png"
        )

    entry = {
        "id":             len(alerts) + 1,
        "image_id":       alert.image_id,
        "capture_node":   alert.capture_node,
        "inference_node": alert.inference_node,
        "confidence":     round(alert.confidence * 100, 1),
        "timestamp":      alert.timestamp,
        "lat":            lat,
        "lon":            lon,
    }
    alerts.append(entry)
    log.info(f"Alert #{entry['id']} | {alert.image_id} | "
             f"lat={lat} lon={lon} | conf={entry['confidence']}%")

    return {"status": "ok", "alert_id": entry["id"], "lat": lat, "lon": lon}


@app.delete("/alerts")
async def clear_alerts():
    alerts.clear()
    log.info("All alerts cleared")
    return {"status": "ok"}


# ── Dashboard ─────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    purge_expired()
    alerts_json = str(alerts).replace("'", '"').replace("True", "true").replace("False", "false")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Wildfire Alert Dashboard</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #1a1a2e;
      color: #eee;
      height: 100vh;
      display: flex;
      flex-direction: column;
    }}
    header {{
      background: #16213e;
      padding: 12px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 2px solid #e74c3c;
    }}
    header h1 {{
      font-size: 1.2rem;
      color: #e74c3c;
      letter-spacing: 1px;
    }}
    #status {{
      font-size: 0.85rem;
      color: #aaa;
    }}
    #badge {{
      background: #e74c3c;
      color: white;
      border-radius: 12px;
      padding: 2px 10px;
      font-size: 0.85rem;
      font-weight: bold;
    }}
    .main {{
      display: flex;
      flex: 1;
      overflow: hidden;
    }}
    #map {{
      flex: 1;
    }}
    #sidebar {{
      width: 340px;
      background: #16213e;
      display: flex;
      flex-direction: column;
      border-left: 1px solid #2c3e6b;
      overflow: hidden;
    }}
    #sidebar-header {{
      padding: 14px 16px;
      background: #0f3460;
      font-size: 0.9rem;
      font-weight: bold;
      color: #e74c3c;
      border-bottom: 1px solid #2c3e6b;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    #clear-btn {{
      background: transparent;
      border: 1px solid #e74c3c;
      color: #e74c3c;
      padding: 3px 10px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 0.75rem;
    }}
    #clear-btn:hover {{ background: #e74c3c; color: white; }}
    #alert-list {{
      flex: 1;
      overflow-y: auto;
      padding: 8px;
    }}
    .alert-card {{
      background: #0f3460;
      border-left: 3px solid #e74c3c;
      border-radius: 6px;
      padding: 10px 12px;
      margin-bottom: 8px;
      cursor: pointer;
      transition: background 0.2s;
    }}
    .alert-card:hover {{ background: #1a4a80; }}
    .alert-card .alert-id {{
      font-size: 0.7rem;
      color: #aaa;
      margin-bottom: 4px;
    }}
    .alert-card .alert-img {{
      font-size: 0.85rem;
      font-weight: bold;
      color: #eee;
      margin-bottom: 4px;
      word-break: break-all;
    }}
    .alert-card .alert-conf {{
      display: inline-block;
      background: #e74c3c;
      color: white;
      border-radius: 4px;
      padding: 1px 7px;
      font-size: 0.75rem;
      font-weight: bold;
      margin-bottom: 4px;
    }}
    .alert-card .alert-meta {{
      font-size: 0.75rem;
      color: #aaa;
    }}
    .no-alerts {{
      text-align: center;
      color: #555;
      padding: 40px 20px;
      font-size: 0.9rem;
    }}
    #refresh-info {{
      padding: 8px 16px;
      font-size: 0.72rem;
      color: #555;
      border-top: 1px solid #2c3e6b;
      text-align: center;
    }}
  </style>
</head>
<body>
  <header>
    <h1>🔥 WILDFIRE ALERT DASHBOARD</h1>
    <div id="status">
      Active alerts: <span id="badge">{len(alerts)}</span>
      &nbsp;|&nbsp; TTL: {ALERT_TTL_H}h
      &nbsp;|&nbsp; Node: {ALERT_NODE}
    </div>
  </header>

  <div class="main">
    <div id="map"></div>
    <div id="sidebar">
      <div id="sidebar-header">
        RECENT ALERTS
        <button id="clear-btn" onclick="clearAlerts()">Clear all</button>
      </div>
      <div id="alert-list"></div>
      <div id="refresh-info">Auto-refresh every 10s</div>
    </div>
  </div>

  <script>
    const MAP_CENTER = [{MAP_CENTER_LAT}, {MAP_CENTER_LON}];
    const MAP_ZOOM   = {MAP_ZOOM};
    const ALERTS     = {alerts_json};

    // Initialize map
    const map = L.map('map').setView(MAP_CENTER, MAP_ZOOM);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      attribution: '© OpenStreetMap contributors',
      maxZoom: 18,
    }}).addTo(map);

    // Fire icon
    const fireIcon = L.divIcon({{
      className: '',
      html: '<div style="font-size:28px;line-height:1;">🔥</div>',
      iconSize: [32, 32],
      iconAnchor: [16, 28],
      popupAnchor: [0, -28],
    }});

    let markers = {{}};

    function formatTs(ts) {{
      const d = new Date(ts + 'Z');
      return d.toLocaleString('en-GB');
    }}

    function renderAlerts(alerts) {{
      // Update badge
      document.getElementById('badge').textContent = alerts.length;

      // Clear existing markers
      Object.values(markers).forEach(m => map.removeLayer(m));
      markers = {{}};

      // Update sidebar list
      const list = document.getElementById('alert-list');
      if (alerts.length === 0) {{
        list.innerHTML = '<div class="no-alerts">No active alerts</div>';
        return;
      }}

      // Sort by timestamp descending
      alerts.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

      list.innerHTML = alerts.map(a => `
        <div class="alert-card" onclick="flyTo(${{a.lat}}, ${{a.lon}}, ${{a.id}})">
          <div class="alert-id">Alert #${{a.id}} — ${{a.capture_node}}</div>
          <div class="alert-img">${{a.image_id}}</div>
          <span class="alert-conf">${{a.confidence}}%</span>
          <div class="alert-meta">
            📍 ${{a.lat.toFixed(4)}}, ${{a.lon.toFixed(4)}}<br>
            🕐 ${{formatTs(a.timestamp)}}<br>
            ⚙️ ${{a.inference_node}}
          </div>
        </div>
      `).join('');

      // Add markers to map
      alerts.forEach(a => {{
        const marker = L.marker([a.lat, a.lon], {{icon: fireIcon}})
          .addTo(map)
          .bindPopup(`
            <b>🔥 Alert #${{a.id}}</b><br>
            <b>File:</b> ${{a.image_id}}<br>
            <b>Confidence:</b> ${{a.confidence}}%<br>
            <b>Capture node:</b> ${{a.capture_node}}<br>
            <b>Inference node:</b> ${{a.inference_node}}<br>
            <b>Timestamp:</b> ${{formatTs(a.timestamp)}}
          `);
        markers[a.id] = marker;
      }});
    }}

    function flyTo(lat, lon, alertId) {{
      map.flyTo([lat, lon], 14, {{duration: 1.0}});
      if (markers[alertId]) markers[alertId].openPopup();
    }}

    async function clearAlerts() {{
      await fetch('/alerts', {{method: 'DELETE'}});
      renderAlerts([]);
    }}

    async function refresh() {{
      try {{
        const res  = await fetch('/alerts');
        const data = await res.json();
        renderAlerts(data.alerts);
      }} catch(e) {{
        console.error('Refresh error:', e);
      }}
    }}

    // Initial render with SSR data
    renderAlerts(ALERTS);

    // Auto-refresh every 10 seconds
    setInterval(refresh, 10000);
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8005, reload=False)