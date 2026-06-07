"""
Ground-truth validation harness for the twistiness algorithm.

Pulls specific real-world roads from the Overpass API and scores them with
curvature.slice_road, so we can sanity-check that famous twisty roads (Tail of
the Dragon) score high and boring roads score low -- WITHOUT running a whole
state through the pipeline each time.

Run:  python -m pipeline.validate
"""
import math
import sys

import httpx

from .curvature import _score_pts, _to_meters, slice_road

OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# (label, overpass selector, bbox south,west,north,east)
TARGETS = [
    # The gold standard: 318 curves in 11 miles. Should score ~10.
    ("Tail of the Dragon (US-129)",
     '["ref"="US 129"]', (35.44, -84.02, 35.57, -83.90)),
    # Cherohala Skyway -- famous sweeping mountain road nearby.
    ("Cherohala Skyway",
     '["name"~"Cherohala"]', (35.20, -84.20, 35.45, -83.90)),
    # The Moonshiner 28 / Hellbender -- another well-known twisty stretch.
    ("NC-28 (Hellbender)",
     '["ref"="NC 28"]', (35.20, -83.85, 35.50, -83.55)),
    # A genuinely straight reference road: I-40 across TN.
    ("I-40 (straight interstate)",
     '["ref"="I 40"]', (36.00, -85.20, 36.10, -85.00)),
    # Suburban residential grid in Knoxville -- should be near zero.
    ("Knoxville residential grid",
     '["highway"="residential"]', (35.93, -84.00, 35.95, -83.98)),
    # User benchmark: Mt Baldy Road, Westfield NY -- known great road.
    ("Mt Baldy Road (Westfield NY)",
     '["name"~"Baldy",i]', (42.25, -79.70, 42.40, -79.45)),
]


def fetch_ways(selector: str, bbox) -> list:
    s, w, n, e = bbox
    q = f"""
    [out:json][timeout:90];
    way["highway"]{selector}({s},{w},{n},{e});
    out geom;
    """
    import time
    last_err = None
    for attempt in range(4):
        for url in OVERPASS_MIRRORS:
            try:
                r = httpx.post(url, data={"data": q}, timeout=120,
                               headers={"User-Agent": "thebends-validate/1.0"})
                r.raise_for_status()
                return _parse_ways(r.json())
            except Exception as ex:
                last_err = ex
                continue
        time.sleep(3 * (attempt + 1))
    raise last_err


def _parse_ways(data) -> list:
    ways = []
    for el in data.get("elements", []):
        if el.get("type") != "way":
            continue
        geom = el.get("geometry") or []
        nodes = [(p["lon"], p["lat"]) for p in geom]
        if len(nodes) >= 2:
            ways.append((el["id"], nodes))
    return ways


def way_length_m(nodes) -> float:
    avg_lat = math.radians(sum(n[1] for n in nodes) / len(nodes))
    pts = [_to_meters(lon, lat, avg_lat) for lon, lat in nodes]
    return sum(math.hypot(pts[i + 1][0] - pts[i][0],
                          pts[i + 1][1] - pts[i][1])
               for i in range(len(pts) - 1))


def main():
    for label, selector, bbox in TARGETS:
        print(f"\n=== {label} ===")
        try:
            ways = fetch_ways(selector, bbox)
        except Exception as ex:
            print(f"  fetch failed: {ex}")
            continue

        if not ways:
            print("  no ways returned")
            continue

        total_len = sum(way_length_m(n) for _, n in ways)
        seg_scores = []
        for wid, nodes in ways:
            for seg_idx, _, score in slice_road(nodes):
                seg_scores.append(score)

        print(f"  OSM ways: {len(ways)}   "
              f"total length: {total_len/1609:.1f} mi   "
              f"avg way: {total_len/len(ways):.0f} m")
        if seg_scores:
            seg_scores.sort(reverse=True)
            print(f"  qualifying segments: {len(seg_scores)}")
            print(f"  best raw score: {seg_scores[0]:.4f}   "
                  f"median: {seg_scores[len(seg_scores)//2]:.4f}")
        else:
            print("  !! ZERO qualifying segments "
                  "(ways too short / filtered out)")


if __name__ == "__main__":
    sys.exit(main())
