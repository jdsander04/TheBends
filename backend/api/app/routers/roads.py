from fastapi import APIRouter, HTTPException, Query, Response

from ..db import get_db
from ..gpx import gpx_track

router = APIRouter()

# Columns returned in the lightweight (map) representation.
_SUMMARY_COLS = """
    id, name, highway, twistiness_score, surface,
    max_grade, avg_grade, elev_gain
"""


def _summary_props(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "highway": row["highway"],
        "twistiness_score": row["twistiness_score"],
        "surface": row["surface"],
        "max_grade": row["max_grade"],
        "avg_grade": row["avg_grade"],
        "elev_gain": row["elev_gain"],
    }


@router.get("/roads/bounds")
def get_roads_by_bounds(
    min_lat: float = Query(...),
    min_lon: float = Query(...),
    max_lat: float = Query(...),
    max_lon: float = Query(...),
    min_twistiness: float = Query(0.3, ge=0.0, le=1.0),
    min_grade: float = Query(0.0, ge=0.0, le=100.0),
    include_unpaved: bool = Query(False),
    include_private: bool = Query(False),
):
    filters = ["twistiness_score >= %s",
               "geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)"]
    params = [min_twistiness, min_lon, min_lat, max_lon, max_lat]

    if min_grade > 0.0:
        filters.append("max_grade >= %s")
        params.append(min_grade)
    if not include_unpaved:
        filters.append("surface <> 'unpaved'")
    if not include_private:
        filters.append("(access IS NULL OR access NOT IN ('private', 'no'))")

    sql = f"""
        SELECT {_SUMMARY_COLS}, ST_AsGeoJSON(geom, 6)::json AS geometry
        FROM osm_roads
        WHERE {' AND '.join(filters)}
        ORDER BY twistiness_score DESC
        LIMIT 500
    """
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": row["geometry"],
                "properties": _summary_props(row),
            }
            for row in rows
        ],
    }


@router.get("/roads/{road_id}")
def get_road(road_id: int):
    """Full detail for one road segment, including the elevation profile."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT {_SUMMARY_COLS}, access, elev_min, elev_max, elev_loss,
                   elev_profile,
                   ST_Length(geom::geography) AS length_m,
                   ST_AsGeoJSON(geom, 6)::json AS geometry
            FROM osm_roads WHERE id = %s
            """,
            (road_id,),
        )
        row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="road not found")

    props = _summary_props(row)
    props.update({
        "access": row["access"],
        "elev_min": row["elev_min"],
        "elev_max": row["elev_max"],
        "elev_loss": row["elev_loss"],
        "elev_profile": row["elev_profile"],
        "length_m": row["length_m"],
    })
    return {"type": "Feature", "geometry": row["geometry"], "properties": props}


@router.get("/roads/{road_id}/gpx")
def get_road_gpx(road_id: int):
    """Export one road segment as a GPX track for a GPS / phone mount."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT name, ST_AsGeoJSON(geom, 6)::json AS geometry "
            "FROM osm_roads WHERE id = %s",
            (road_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="road not found")

    coords = [(c[0], c[1]) for c in row["geometry"]["coordinates"]]
    body = gpx_track(row["name"] or "Unnamed Road", [coords])
    return Response(content=body, media_type="application/gpx+xml",
                    headers={"Content-Disposition":
                             f'attachment; filename="road-{road_id}.gpx"'})


@router.get("/routes/popular")
def get_popular_routes(limit: int = Query(20, ge=1, le=100)):
    """Top named roads by twistiness — a stand-in for curated routes."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT {_SUMMARY_COLS},
                   ST_AsGeoJSON(geom, 6)::json AS geometry,
                   ST_Length(geom::geography) AS length_m
            FROM osm_roads
            WHERE name IS NOT NULL AND name != ''
              AND twistiness_score > 0.7
              AND surface <> 'unpaved'
            ORDER BY twistiness_score DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": row["geometry"],
                "properties": {**_summary_props(row), "length_m": row["length_m"]},
            }
            for row in rows
        ],
    }
