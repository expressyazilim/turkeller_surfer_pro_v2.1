import math
import io
import numpy as np
import tifffile as tiff
from collections import deque

def parse_coord_pair(s: str):
    if not s:
        return None, None
    s = s.strip().replace(",", " ")
    parts = [p for p in s.split() if p.strip()]
    if len(parts) < 2:
        return None, None
    try:
        lat = float(parts[0].replace(",", "."))
        lon = float(parts[1].replace(",", "."))
        return lat, lon
    except Exception:
        return None, None

def bbox_from_latlon(lat: float, lon: float, cap_m: float):
    lat_f = cap_m / 111320.0
    lon_f = cap_m / (40075000.0 * math.cos(math.radians(lat)) / 360.0)
    return [lon - lon_f, lat - lat_f, lon + lon_f, lat + lat_f]

def box_blur(img: np.ndarray, k: int = 3):
    if k <= 1:
        return img
    k = int(k)
    pad = k // 2
    a = np.pad(img, ((pad, pad), (pad, pad)), mode="edge").astype(np.float32)

    s = np.zeros((a.shape[0] + 1, a.shape[1] + 1), dtype=np.float32)
    s[1:, 1:] = np.cumsum(np.cumsum(a, axis=0), axis=1)

    h, w = img.shape
    out = np.empty((h, w), dtype=np.float32)

    for r in range(h):
        r0 = r
        r1 = r + k
        for c in range(w):
            c0 = c
            c1 = c + k
            total = s[r1, c1] - s[r0, c1] - s[r1, c0] + s[r0, c0]
            out[r, c] = total / (k * k)
    return out

def robust_z(x: np.ndarray):
    valid = x[~np.isnan(x)]
    if valid.size == 0:
        return x * np.nan
    med = np.median(valid)
    mad = np.median(np.abs(valid - med))
    denom = (1.4826 * mad) if mad > 1e-9 else (np.std(valid) if np.std(valid) > 1e-9 else 1.0)
    return (x - med) / denom

def classic_z(x: np.ndarray):
    valid = x[~np.isnan(x)]
    if valid.size == 0:
        return x * np.nan
    mu = float(np.mean(valid))
    sd = float(np.std(valid)) if float(np.std(valid)) > 1e-9 else 1.0
    return (x - mu) / sd

def connected_components(mask: np.ndarray):
    h, w = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    comps = []
    neighbors = [(-1,-1),(-1,0),(-1,1),
                 ( 0,-1),       ( 0,1),
                 ( 1,-1),( 1,0),( 1,1)]
    for r in range(h):
        for c in range(w):
            if mask[r, c] and not visited[r, c]:
                q = deque([(r, c)])
                visited[r, c] = True
                pixels = []
                rmin=rmax=r
                cmin=cmax=c
                while q:
                    rr, cc = q.popleft()
                    pixels.append((rr, cc))
                    rmin = min(rmin, rr); rmax = max(rmax, rr)
                    cmin = min(cmin, cc); cmax = max(cmax, cc)
                    for dr, dc in neighbors:
                        nr, nc = rr + dr, cc + dc
                        if 0 <= nr < h and 0 <= nc < w and mask[nr, nc] and not visited[nr, nc]:
                            visited[nr, nc] = True
                            q.append((nr, nc))
                comps.append({"pixels": pixels, "area": len(pixels), "bbox": (rmin, rmax, cmin, cmax)})
    return comps

def weighted_peak_center(peak_r, peak_c, Zz, X, Y, win=1):
    H, W = Zz.shape
    r0 = max(0, peak_r - win); r1 = min(H - 1, peak_r + win)
    c0 = max(0, peak_c - win); c1 = min(W - 1, peak_c + win)

    rr, cc = np.meshgrid(np.arange(r0, r1 + 1), np.arange(c0, c1 + 1), indexing="ij")
    w = np.abs(Zz[rr, cc]).astype(np.float64)
    s = float(np.sum(w))
    if s <= 1e-12:
        return float(Y[peak_r, peak_c]), float(X[peak_r, peak_c])
    lat = float(np.sum(w * Y[rr, cc]) / s)
    lon = float(np.sum(w * X[rr, cc]) / s)
    return lat, lon

def estimate_relative_depth(area_px: int, peak_abs_z: float):
    peak = max(peak_abs_z, 1e-6)
    return float(math.sqrt(max(area_px, 1)) / peak)

def run_analysis_from_tiff_bytes(
    tiff_bytes: bytes,
    bbox: list[float],
    clip_lo: float,
    clip_hi: float,
    smooth_on: bool,
    smooth_k: int,
    z_mode: str,
    thr: float,
    posneg: bool,
):
    Z = tiff.imread(io.BytesIO(tiff_bytes)).astype(np.float32)
    H, W = Z.shape[:2]

    X, Y = np.meshgrid(
        np.linspace(bbox[0], bbox[2], W),
        np.linspace(bbox[1], bbox[3], H),
    )

    eps = 1e-10
    Z_db = 10.0 * np.log10(np.maximum(Z, eps))

    valid = Z_db[~np.isnan(Z_db)]
    p_lo, p_hi = np.percentile(valid, [clip_lo, clip_hi])
    Z_db_clip = np.clip(Z_db, p_lo, p_hi)

    if smooth_on and smooth_k > 1:
        Z_db_clip = box_blur(Z_db_clip.astype(np.float32), k=int(smooth_k))

    Z_z = robust_z(Z_db_clip) if z_mode.startswith("Robust") else classic_z(Z_db_clip)

    if posneg:
        pos_mask = (Z_z >= thr)
        neg_mask = (Z_z <= -thr)
    else:
        pos_mask = (np.abs(Z_z) >= thr)
        neg_mask = np.zeros_like(pos_mask, dtype=bool)

    comps_pos = connected_components(pos_mask) if np.any(pos_mask) else []
    comps_neg = connected_components(neg_mask) if np.any(neg_mask) else []

    def score_components(comps, sign_label):
        ranked = []
        for comp in comps:
            pix = comp["pixels"]
            rr = np.array([p[0] for p in pix], dtype=int)
            cc = np.array([p[1] for p in pix], dtype=int)

            vals = Z_z[rr, cc]
            if sign_label == "POS":
                k = int(np.argmax(vals))
                signed_peak = float(vals[k])
            else:
                k = int(np.argmin(vals))
                signed_peak = float(vals[k])

            peak_abs = float(abs(signed_peak))
            area = int(comp["area"])
            rmin, rmax, cmin, cmax = comp["bbox"]

            bbox_area = int((rmax - rmin + 1) * (cmax - cmin + 1))
            fill = (area / bbox_area) if bbox_area > 0 else 0.0
            score = peak_abs * math.log1p(area) * (0.6 + 0.8 * fill)

            peak_r = int(rr[k])
            peak_c = int(cc[k])
            target_lat, target_lon = weighted_peak_center(peak_r, peak_c, Z_z, X, Y, win=1)

            rel_z = estimate_relative_depth(area, peak_abs)

            ranked.append({
                "type": sign_label,
                "score": float(score),
                "peak_z": float(signed_peak),
                "area": area,
                "fill": float(fill),
                "bbox_rc": (int(rmin), int(rmax), int(cmin), int(cmax)),
                "target_lat": float(target_lat),
                "target_lon": float(target_lon),
                "rel_depth": float(rel_z),
            })
        ranked.sort(key=lambda d: d["score"], reverse=True)
        return ranked

    ranked = score_components(comps_pos, "POS") + score_components(comps_neg, "NEG")
    ranked.sort(key=lambda d: d["score"], reverse=True)

    return {
        "Z_db_clip": Z_db_clip,
        "X": X,
        "Y": Y,
        "Z_z": Z_z,
        "ranked": ranked,
        "pos_mask": pos_mask,
        "neg_mask": neg_mask,
    }
