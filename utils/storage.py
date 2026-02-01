import json
import os
from datetime import datetime

HISTORY_FILE = "scan_history.json"

def _safe_read_json(path: str):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            txt = f.read().strip()
            if not txt:
                return []
            return json.loads(txt)
    except Exception:
        return []

def load_history() -> list[dict]:
    data = _safe_read_json(HISTORY_FILE)
    # Eski kayıtlar farklı anahtarla geldiyse normalize et
    out = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        out.append({
            "ts": item.get("ts") or item.get("timestamp") or "Tarih yok",
            "lat": item.get("lat") or item.get("latitude") or None,
            "lon": item.get("lon") or item.get("longitude") or None,
            "cap_m": item.get("cap_m", item.get("cap")),
            "thr": item.get("thr", item.get("threshold")),
            "top": item.get("top", item.get("topN", [])),
        })
    return out

def append_history(lat: float, lon: float, cap_m: int, thr: float, top: list[dict]):
    hist = load_history()
    hist.append({
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "lat": float(lat),
        "lon": float(lon),
        "cap_m": int(cap_m),
        "thr": float(thr),
        "top": top,
    })
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)
