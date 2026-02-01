import json
import os

HISTORY_FILE = "scan_history.json"

def save_report(filename, lat, lon, z, timestamp):
    data = {
        "filename": filename,
        "lat": lat,
        "lon": lon,
        "z": z,
        "timestamp": timestamp
    }
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                history = json.load(f)
        else:
            history = []
    except Exception:
        history = []

    history.append(data)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []
