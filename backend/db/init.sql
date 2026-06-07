CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS osm_roads (
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
);

CREATE INDEX IF NOT EXISTS idx_roads_geom        ON osm_roads USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_roads_twistiness  ON osm_roads(twistiness_score);
CREATE INDEX IF NOT EXISTS idx_roads_surface     ON osm_roads(surface);
