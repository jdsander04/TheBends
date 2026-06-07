import math

from fastapi import APIRouter, HTTPException, Query, Response

from ..db import get_db
from ..gpx import gpx_route, gpx_track

router = APIRouter()

_EARTH_R = 6_371_000.0


def _haversine(a, b) -> float:
    """Great-circle distance in metres between (lat, lon) points."""
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = math.radians(b[0] - a[0])
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_R * math.asin(math.sqrt(h))


def _candidates(lat, lon, radius_m, min_tw, include_unpaved):
    surface = "" if include_unpaved else "AND surface <> 'unpaved'"
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            WITH cand AS (
                SELECT DISTINCT ON (way_id)
                       id, name, twistiness_score AS score, surface,
                       ST_Y(ST_Centroid(geom)) AS clat,
                       ST_X(ST_Centroid(geom)) AS clon,
                       ST_Length(geom::geography) AS len_m,
                       ST_AsGeoJSON(geom)::json AS geometry
                FROM osm_roads
                WHERE twistiness_score >= %s
                  {surface}
                  AND (access IS NULL OR access NOT IN ('private', 'no'))
                  AND ST_DWithin(
                        geom::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                        %s)
                ORDER BY way_id, twistiness_score DESC
            )
            SELECT * FROM cand ORDER BY score DESC LIMIT 250
            """,
            (min_tw, lon, lat, radius_m),
        )
        return cur.fetchall()


def _build_loop(rows, start, target_m):
    """
    Greedy prize-collecting tour: from the start point, repeatedly hop to the
    nearby segment with the best score-per-detour, never committing to a leg
    that can't still return to start within ~120% of the distance budget.
    Returns (ordered_rows, summary).
    """
    used = set()
    cur_pt = start
    dist = 0.0
    twisty = 0.0
    route = []

    while len(route) < 40:
        best = None
        best_val = -1.0
        best_gap = 0.0
        for r in rows:
            if r["id"] in used:
                continue
            c = (r["clat"], r["clon"])
            gap = _haversine(cur_pt, c)
            back = _haversine(c, start)
            projected = dist + gap + r["len_m"] + back
            if route and projected > target_m * 1.2:
                continue
            # favour high score and short detours
            val = r["score"] / ((gap + 200.0) / 200.0)
            if val > best_val:
                best_val, best, best_gap = val, r, gap
        if best is None:
            break
        used.add(best["id"])
        dist += best_gap + best["len_m"]
        twisty += best["len_m"]
        route.append(best)
        cur_pt = (best["clat"], best["clon"])

    dist += _haversine(cur_pt, start)  # closing leg back to start

    summary = {
        "stops": len(route),
        "twisty_km": round(twisty / 1000.0, 1),
        "est_distance_km": round(dist / 1000.0, 1),
        "avg_score": round(
            sum(r["score"] for r in route) / len(route), 3) if route else 0.0,
    }
    return route, summary


def _loop_or_404(lat, lon, distance_km, min_tw, include_unpaved):
    radius_m = distance_km * 1000.0 * 0.6
    rows = _candidates(lat, lon, radius_m, min_tw, include_unpaved)
    return _build_loop(rows, (lat, lon), distance_km * 1000.0)


@router.get("/routes/loop")
def routes_loop(
    lat: float = Query(...),
    lon: float = Query(...),
    distance_km: float = Query(40.0, ge=5.0, le=400.0),
    min_twistiness: float = Query(0.5, ge=0.0, le=1.0),
    include_unpaved: bool = Query(False),
):
    """Suggest a curvy round-trip of high-scoring roads near a start point."""
    route, summary = _loop_or_404(
        lat, lon, distance_km, min_twistiness, include_unpaved)
    return {
        "type": "FeatureCollection",
        "summary": summary,
        "features": [
            {
                "type": "Feature",
                "geometry": r["geometry"],
                "properties": {
                    "order": i,
                    "id": r["id"],
                    "name": r["name"],
                    "surface": r["surface"],
                    "twistiness_score": r["score"],
                },
            }
            for i, r in enumerate(route)
        ],
    }


@router.get("/routes/gpx")
def route_gpx(
    points: str = Query(..., description="semicolon-separated lat,lng pairs"),
    name: str = Query("TheBends route"),
):
    """Build a GPX route from an ordered list of pins, served as a download."""
    pts = []
    for pair in points.split(";"):
        pair = pair.strip()
        if not pair:
            continue
        try:
            lat_s, lon_s = pair.split(",")
            pts.append((float(lon_s), float(lat_s)))
        except ValueError:
            continue
    if len(pts) < 2:
        raise HTTPException(status_code=400, detail="need at least 2 points")

    body = gpx_route(name, pts)
    return Response(content=body, media_type="application/gpx+xml",
                    headers={"Content-Disposition":
                             'attachment; filename="thebends-route.gpx"'})


@router.get("/routes/loop.gpx")
def routes_loop_gpx(
    lat: float = Query(...),
    lon: float = Query(...),
    distance_km: float = Query(40.0, ge=5.0, le=400.0),
    min_twistiness: float = Query(0.5, ge=0.0, le=1.0),
    include_unpaved: bool = Query(False),
):
    route, summary = _loop_or_404(
        lat, lon, distance_km, min_twistiness, include_unpaved)
    segments = [
        [(c[0], c[1]) for c in r["geometry"]["coordinates"]] for r in route
    ]
    name = f"TheBends loop — {summary['twisty_km']}km twisty / " \
           f"~{summary['est_distance_km']}km total"
    body = gpx_track(name, segments)
    return Response(content=body, media_type="application/gpx+xml",
                    headers={"Content-Disposition":
                             'attachment; filename="thebends-loop.gpx"'})
