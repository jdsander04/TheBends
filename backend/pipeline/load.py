import json
from typing import Iterable

import psycopg2
from psycopg2.extras import execute_values

from .parse import RoadRecord


def _linestring(nodes) -> str:
    return "LINESTRING(" + ", ".join(f"{lon} {lat}" for lon, lat in nodes) + ")"


def recreate_table(conn) -> None:
    """Drop and recreate osm_roads with the current schema."""
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS osm_roads")
    cur.execute("""
        CREATE TABLE osm_roads (
            id               BIGSERIAL PRIMARY KEY,
            way_id           BIGINT NOT NULL,
            seg_idx          INT    NOT NULL,
            name             TEXT,
            highway          TEXT   NOT NULL,
            geom             GEOMETRY(LineString, 4326) NOT NULL,
            twistiness_score FLOAT  NOT NULL DEFAULT 0.0,
            node_count       INT,
            surface          TEXT   NOT NULL DEFAULT 'unknown',
            access           TEXT,
            elev_min         REAL,
            elev_max         REAL,
            elev_gain        REAL,
            elev_loss        REAL,
            max_grade        REAL,
            avg_grade        REAL,
            elev_profile     JSONB,
            UNIQUE (way_id, seg_idx)
        )
    """)
    cur.execute("CREATE INDEX ON osm_roads USING GIST(geom)")
    cur.execute("CREATE INDEX ON osm_roads(twistiness_score)")
    cur.execute("CREATE INDEX ON osm_roads(surface)")
    conn.commit()
    cur.close()


def insert_raw(roads: Iterable[RoadRecord], conn, batch_size: int = 500) -> int:
    """Stream road segments into DB in small batches. Returns total inserted."""
    cur = conn.cursor()
    total = 0
    batch = []

    for road in roads:
        batch.append(road)
        if len(batch) >= batch_size:
            _flush(cur, batch)
            conn.commit()
            total += len(batch)
            print(f"  {total:,} segments inserted ...")
            batch.clear()

    if batch:
        _flush(cur, batch)
        conn.commit()
        total += len(batch)

    cur.close()
    print(f"  {total:,} segments total")
    return total


def _flush(cur, batch: list) -> None:
    execute_values(
        cur,
        """
        INSERT INTO osm_roads
            (way_id, seg_idx, name, highway, geom, twistiness_score, node_count,
             surface, access, elev_min, elev_max, elev_gain, elev_loss,
             max_grade, avg_grade, elev_profile)
        VALUES %s
        ON CONFLICT (way_id, seg_idx) DO NOTHING
        """,
        [
            (
                r.way_id,
                r.seg_idx,
                r.name,
                r.highway,
                _linestring(r.nodes),
                r.raw_curvature,
                len(r.nodes),
                r.surface,
                r.access,
                r.elev.get("elev_min"),
                r.elev.get("elev_max"),
                r.elev.get("elev_gain"),
                r.elev.get("elev_loss"),
                r.elev.get("max_grade"),
                r.elev.get("avg_grade"),
                json.dumps(r.elev.get("profile", [])),
            )
            for r in batch
        ],
        template="(%s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s, %s, "
                 "%s, %s, %s, %s, %s, %s, %s, %s, %s)",
    )


def prune_urban_residential(
    conn, radius_deg: float = 0.004, max_neighbors: int = 15
) -> int:
    """Drop residential segments embedded in a dense road grid (subdivisions).

    Rural residential roads are great driving backroads and are kept; subdivision
    streets are distinguished only by being surrounded by many other ways within
    ~360 m. Other highway classes are never touched. Returns rows deleted.

    Measured on the Tennessee extract: the qualifying residential set is ~98%
    rural (<=15 neighbours); this removes only the dense-grid tail.
    """
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM osm_roads r
        WHERE r.highway = 'residential'
          AND (
            SELECT count(*) FROM osm_roads o
            WHERE o.way_id <> r.way_id
              AND o.geom && ST_Expand(r.geom, %s)
              AND ST_DWithin(o.geom, r.geom, %s)
          ) > %s
        """,
        (radius_deg, radius_deg, max_neighbors),
    )
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    return deleted


def prune_short_residential(conn, min_length_m: float = 1000.0) -> int:
    """Drop residential roads whose full length is below min_length_m.

    A real residential driving backroad runs for kilometres (Parson Branch
    7.5km, Mt Baldy 4.2km); short residential ways are cottage/camp lanes and
    cul-de-sacs that pack one tight-curve window and otherwise outrank real
    roads (Scandia Rd, a 3.6km secondary, was being buried under thousands of
    sub-1km lanes scoring 10). Other highway classes are never touched.

    Length is the geometric union of a way's overlapping 1km windows, so it is
    the true road length, not the (qualify-filtered) segment count.
    Returns rows deleted.
    """
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM osm_roads
        WHERE highway = 'residential'
          AND way_id IN (
            SELECT way_id FROM osm_roads
            WHERE highway = 'residential'
            GROUP BY way_id
            HAVING ST_Length(ST_LineMerge(ST_Union(geom))::geography) < %s
          )
        """,
        (min_length_m,),
    )
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    return deleted


def normalize_in_db(conn) -> None:
    """Scale twistiness_score to [0, 1].

    99th-percentile ceiling computed only from proper road classes with
    enough nodes, so short stubs don't skew mountain road scores.

    A sqrt transfer is applied after the linear scaling: it keeps the elite
    roads near 1.0 while lifting genuinely-good mid-tier roads out of the
    bottom of the scale (e.g. Mt Baldy Rd: 0.31 linear -> 0.56). Chosen over
    raw-linear (crushes good local roads) and percentile-rank (inflates the
    median and erases top-end resolution).
    """
    cur = conn.cursor()
    cur.execute("""
        WITH p99 AS (
            SELECT PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY twistiness_score) AS val
            FROM osm_roads
            WHERE node_count >= 8
              AND highway IN ('primary', 'secondary', 'tertiary',
                              'unclassified', 'trunk', 'trunk_link', 'road')
        )
        UPDATE osm_roads
        SET twistiness_score = sqrt(LEAST(
            twistiness_score / NULLIF((SELECT val FROM p99), 0),
            1.0
        ))
    """)
    conn.commit()
    cur.close()
