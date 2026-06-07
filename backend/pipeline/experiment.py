"""
Compare scoring-formula variants against ground-truth roads.

Goal: a formula where the Tail of the Dragon stays top, Mt Baldy Road (great
road, but punctuated with straights) scores clearly "good", and I-40 / dense
residential stay near zero.

Run:  python -m pipeline.experiment
"""
import math

from .curvature import _menger, _radius_weight, _to_meters
from .validate import fetch_ways

ROADS = [
    ("Tail of the Dragon",      '["ref"="US 129"]',  (35.44, -84.02, 35.57, -83.90)),
    ("NC-28 Hellbender",        '["ref"="NC 28"]',   (35.20, -83.85, 35.50, -83.55)),
    ("Cherohala Skyway",        '["name"~"Cherohala"]', (35.20, -84.20, 35.45, -83.90)),
    ("Mt Baldy Rd (Westfield)", '["name"~"Baldy",i]', (42.25, -79.70, 42.40, -79.45)),
    ("I-40 (straight)",         '["ref"="I 40"]',    (36.00, -85.20, 36.10, -85.00)),
    ("Knoxville residential",   '["highway"="residential"]', (35.93, -84.00, 35.95, -83.98)),
]

_WINDOW_M = 1000.0
_STEP_M = 500.0
_MIN_LEN = 400.0


def project(nodes):
    avg_lat = math.radians(sum(p[1] for p in nodes) / len(nodes))
    pts = [_to_meters(lo, la, avg_lat) for lo, la in nodes]
    seglen = [math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
              for i in range(len(pts) - 1)]
    return pts, seglen


def windows(nodes):
    """Yield projected 1km windows (pts, seglen) like slice_road does."""
    if len(nodes) < 5:
        return
    pts, seglen = project(nodes)
    cum = [0.0]
    for s in seglen:
        cum.append(cum[-1] + s)
    total = cum[-1]
    if total < _MIN_LEN:
        return

    def idx_at(d):
        lo, hi = 0, len(cum) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if cum[mid] < d:
                lo = mid + 1
            else:
                hi = mid
        return lo

    start = 0.0
    while start <= total - _MIN_LEN * 0.5:
        end = min(start + _WINDOW_M, total)
        i0 = max(0, idx_at(start) - 1)
        i1 = idx_at(end)
        wp = pts[i0:i1 + 1]
        if len(wp) >= 5:
            ws = [math.hypot(wp[i + 1][0] - wp[i][0], wp[i + 1][1] - wp[i][1])
                  for i in range(len(wp) - 1)]
            yield wp, ws
        start += _STEP_M


def _w_gentle0(K):
    """Like _radius_weight but gentle bends (R>175) count as ZERO, not 0.3.
    Removes the leak where highway sweepers (I-40) accumulate score."""
    if K < 1e-6:
        return 0.0
    R = 1.0 / K
    if R > 175: return 0.0
    if R > 100: return 1.0
    if R > 60:  return 2.0
    if R > 30:  return 3.0
    return 4.0


def variants(pts, segs):
    """Return dict of {variant_name: score} for one window."""
    total = sum(segs)
    if total < _MIN_LEN:
        return None
    disp = math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])
    if disp / total < 0.10:
        return None

    weighted = 0.0      # Σ weight·len (old weights, gentle=0.3)
    w0 = 0.0            # Σ weight·len (gentle=0)
    curvy_len = 0.0     # length in curves R<175
    for i in range(len(pts) - 2):
        K = _menger(pts[i], pts[i + 1], pts[i + 2])
        weighted += _radius_weight(K) * segs[i]
        w0 += _w_gentle0(K) * segs[i]
        if K > 1.0 / 175.0:
            curvy_len += segs[i]

    if weighted < 1e-9:
        return None

    km = total / 1000.0
    curvy_frac = curvy_len / total

    return {
        # A: current production formula
        "A_current": (weighted / total) * math.sqrt(curvy_frac),
        # F: gentle=0, units/km, NO consistency factor
        "F_w0/km": w0 / km,
        # G: gentle=0, units/km, soft 4th-root consistency
        "G_w0/km×f^.25": (w0 / km) * (curvy_frac ** 0.25),
        # H: gentle=0, units/km, sqrt consistency
        "H_w0/km×sqrt(f)": (w0 / km) * math.sqrt(curvy_frac),
    }


def main():
    variant_names = None
    results = {}
    for label, sel, bbox in ROADS:
        try:
            ways = fetch_ways(sel, bbox)
        except Exception as ex:
            print(f"{label}: fetch failed {ex}")
            continue
        best = {}
        for _, nodes in ways:
            for wp, ws in windows(nodes):
                v = variants(wp, ws)
                if not v:
                    continue
                if variant_names is None:
                    variant_names = list(v)
                for k, val in v.items():
                    if val > best.get(k, 0.0):
                        best[k] = val
        results[label] = best

    if not variant_names:
        print("no data")
        return

    # Print table: rows = roads, cols = variants (best window per road)
    w = max(len(r) for r in results) + 2
    header = "ROAD".ljust(w) + "".join(vn.rjust(20) for vn in variant_names)
    print(header)
    print("-" * len(header))
    for label, best in results.items():
        row = label.ljust(w)
        for vn in variant_names:
            row += f"{best.get(vn, 0.0):20.3f}"
        print(row)


if __name__ == "__main__":
    main()
