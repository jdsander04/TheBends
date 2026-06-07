"""
Elevation sampling from SRTM 1-arc-second tiles (AWS 'skadi' open dataset).

Free, no API key. Tiles are 1x1-degree gzipped HGT files; we cache the
decompressed .hgt on disk and memory-map them (numpy memmap), so RAM stays
flat no matter how many tiles a region touches.

    elev = ElevationData("/data/srtm")
    e = elev.elevation(35.4655, -83.9170)   # metres, or None over no-data/ocean
    feats = profile_features([(lon, lat), ...], elev)
"""
import gzip
import math
import os
from pathlib import Path
from typing import List, Optional, Tuple

import httpx
import numpy as np

_SKADI = "https://s3.amazonaws.com/elevation-tiles-prod/skadi"
_SIZE = 3601           # samples per side for 1 arc-second tiles
_NODATA = -32768
_EARTH_R = 6_371_000.0


def _tile_id(lat: float, lon: float) -> str:
    la = math.floor(lat)
    lo = math.floor(lon)
    ns = "N" if la >= 0 else "S"
    ew = "E" if lo >= 0 else "W"
    return f"{ns}{abs(la):02d}{ew}{abs(lo):03d}"


class ElevationData:
    """Lazily downloads, caches and memory-maps SRTM tiles for point sampling."""

    def __init__(self, cache_dir: str):
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self._tiles = {}          # tile_id -> np.memmap | None (None = missing)

    def _load(self, tid: str):
        if tid in self._tiles:
            return self._tiles[tid]

        hgt = self.cache / f"{tid}.hgt"
        if not hgt.exists():
            url = f"{_SKADI}/{tid[:3]}/{tid}.hgt.gz"
            gz = self.cache / f"{tid}.hgt.gz"
            try:
                with httpx.stream("GET", url, timeout=180,
                                  follow_redirects=True) as r:
                    if r.status_code != 200:
                        self._tiles[tid] = None
                        return None
                    with open(gz, "wb") as f:
                        for chunk in r.iter_bytes(65_536):
                            f.write(chunk)
                with gzip.open(gz, "rb") as fin, open(hgt, "wb") as fout:
                    fout.write(fin.read())
                gz.unlink(missing_ok=True)
            except Exception:
                self._tiles[tid] = None
                return None

        arr = np.memmap(hgt, dtype=">i2", mode="r", shape=(_SIZE, _SIZE))
        self._tiles[tid] = arr
        return arr

    def elevation(self, lat: float, lon: float) -> Optional[float]:
        """Bilinearly-interpolated elevation in metres, or None if unavailable."""
        arr = self._load(_tile_id(lat, lon))
        if arr is None:
            return None

        la0 = math.floor(lat)
        lo0 = math.floor(lon)
        # row 0 is the NORTH edge; latitude increases upward
        fy = (la0 + 1 - lat) * (_SIZE - 1)
        fx = (lon - lo0) * (_SIZE - 1)

        y0 = max(0, min(int(math.floor(fy)), _SIZE - 1))
        x0 = max(0, min(int(math.floor(fx)), _SIZE - 1))
        y1 = min(y0 + 1, _SIZE - 1)
        x1 = min(x0 + 1, _SIZE - 1)
        dy = fy - y0
        dx = fx - x0

        v00, v10 = int(arr[y0, x0]), int(arr[y0, x1])
        v01, v11 = int(arr[y1, x0]), int(arr[y1, x1])
        quad = (v00, v10, v01, v11)
        if _NODATA in quad:
            valid = [v for v in quad if v != _NODATA]
            return sum(valid) / len(valid) if valid else None

        top = v00 * (1 - dx) + v10 * dx
        bot = v01 * (1 - dx) + v11 * dx
        return top * (1 - dy) + bot * dy


def profile_features(coords: List[Tuple[float, float]],
                     elev: ElevationData) -> dict:
    """
    Compute elevation/grade features for a polyline of (lon, lat) coords.

    Returns dict with metres/percent/array, or zeros if elevation unavailable:
      elev_min, elev_max, elev_gain (total ascent), elev_loss,
      max_grade (steepest, %), avg_grade (climb+descent over length, %),
      profile (down-sampled elevation list for the detail view)
    """
    n = len(coords)
    blank = {"elev_min": None, "elev_max": None, "elev_gain": 0.0,
             "elev_loss": 0.0, "max_grade": 0.0, "avg_grade": 0.0,
             "profile": []}
    if n < 2:
        return blank

    es = [elev.elevation(lat, lon) for lon, lat in coords]
    if all(e is None for e in es):
        return blank
    # forward/back-fill the occasional no-data node
    last = next((e for e in es if e is not None), 0.0)
    for i in range(n):
        if es[i] is None:
            es[i] = last
        else:
            last = es[i]

    ref_lat = math.radians(sum(lat for _, lat in coords) / n)
    cos_lat = math.cos(ref_lat)

    def dist(a, b):
        dx = math.radians(b[0] - a[0]) * _EARTH_R * cos_lat
        dy = math.radians(b[1] - a[1]) * _EARTH_R
        return math.hypot(dx, dy)

    # Cumulative distance along the polyline.
    cum = [0.0]
    for i in range(1, n):
        cum.append(cum[-1] + dist(coords[i - 1], coords[i]))
    total_d = cum[-1]
    if total_d < 1.0:
        return blank

    # Resample elevation at a fixed step (SRTM is ~30 m native), then lightly
    # smooth. This kills the spurious 30%+ grades that node-to-node deltas
    # produce where OSM nodes are only a few metres apart.
    _STEP = 30.0
    _GRADE_BASE = 60.0          # measure grade over a ~60 m baseline
    m = max(2, int(total_d / _STEP) + 1)
    xs = [j * total_d / (m - 1) for j in range(m)]
    re = []
    k = 0
    for x in xs:
        while k < n - 1 and cum[k + 1] < x:
            k += 1
        seg = cum[k + 1] - cum[k] if k < n - 1 else 0.0
        t = (x - cum[k]) / seg if seg > 1e-6 else 0.0
        e_lo = es[k]
        e_hi = es[min(k + 1, n - 1)]
        re.append(e_lo + (e_hi - e_lo) * t)
    # 3-point moving average
    sm = re[:]
    for j in range(1, m - 1):
        sm[j] = (re[j - 1] + re[j] + re[j + 1]) / 3.0

    gain = loss = 0.0
    for j in range(1, m):
        de = sm[j] - sm[j - 1]
        if de > 0.3:           # deadband to suppress vertical noise
            gain += de
        elif de < -0.3:
            loss += -de

    # max grade over a sliding ~_GRADE_BASE window
    win = max(1, int(round(_GRADE_BASE / _STEP)))
    max_grade = 0.0
    for j in range(win, m):
        d = xs[j] - xs[j - win]
        if d > 1.0:
            g = abs(sm[j] - sm[j - win]) / d
            if g > max_grade:
                max_grade = g

    avg_grade = (gain + loss) / total_d if total_d > 0 else 0.0

    # down-sample profile to <= 30 points for a compact API payload
    pstep = max(1, m // 30)
    profile = [round(sm[j], 1) for j in range(0, m, pstep)]

    return {
        "elev_min": round(min(sm), 1),
        "elev_max": round(max(sm), 1),
        "elev_gain": round(gain, 1),
        "elev_loss": round(loss, 1),
        "max_grade": round(max_grade * 100, 1),
        "avg_grade": round(avg_grade * 100, 1),
        "profile": profile,
    }
