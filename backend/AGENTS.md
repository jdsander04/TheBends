# TheBends - Backend Agent Blueprint

This document defines the architecture, data pipeline, and API specifications for TheBends backend. The primary objective is to ingest OpenStreetMap (OSM) data, calculate a custom "Twistiness Index," and serve both vector/raster map layers and a supporting REST API.

## 1. System Architecture & Tech Stack
* **Language/Runtime:** Python (FastAPI) or Go (for high-performance geospatial processing).
* **Database:** PostgreSQL with **PostGIS** extension (essential for spatial queries).
* **Data Ingestion:** Osmium tool / Overpass API (for downloading OSM `.pbf` files).
* **Tile Serving:** Tegola or Martin (PostGIS-native vector tile servers) or custom FastAPI endpoints for GeoJSON layers.

## 2. Core Feature: The "Twisty" Algorithm
To determine how windy a road is, we process the coordinates (nodes) of OSM `way` elements tagged as highways (e.g., `primary`, `secondary`, `tertiary`, `residential`).

### The Menger Curvature / Triangle Area Method
For every three consecutive nodes $P_1, P_2, P_3$ along a way, we calculate the area of the triangle they form, or compute the **Menger Curvature**, defined as:

$$K = \frac{4 \times \text{Area}(P_1, P_2, P_3)}{|P_1 - P_2| \cdot |P_2 - P_3| \cdot |P_3 - P_1|}$$

### Pipeline Implementation Steps
1.  **Ingestion:** Parse OSM PBF files for the target region and extract roads.
2.  **Smoothing/Filtering:** Ignore tiny node jitters; filter out dead-straight highways to save compute.
3.  **Windowing:** Implement a rolling window over nodes:
    * Window 1: Nodes $(1, 2, 3)$ $\rightarrow$ Calculate Curvature $K_1$
    * Window 2: Nodes $(2, 3, 4)$ $\rightarrow$ Calculate Curvature $K_2$
    * Window 3: Nodes $(3, 4, 5)$ $\rightarrow$ Calculate Curvature $K_3$
4.  **Aggregation:** Normalize the scores and assign an overall **Twistiness Score (0.0 - 1.0)** to the entire `way` segment, or store it per-segment node for granular rendering.
5.  **Database Storage:** Store geometry in PostGIS with the calculated score indexed:
    ```sql
    ALTER TABLE OSM_Roads ADD COLUMN twistiness_score FLOAT;
    CREATE INDEX idx_roads_geometry ON OSM_Roads USING GIST(geom);
    ```

## 3. API Endpoints (REST & Vector Tiles)

### Geo-Queries & Routing
* **`GET /api/v1/roads/bounds`**
    * *Description:* Returns roads with high twistiness within a bounding box.
    * *Params:* `min_lat`, `min_lon`, `max_lat`, `max_lon`, `min_twistiness`.
* **`GET /api/v1/routes/popular`**
    * *Description:* Returns curated, community-rated twisty routes.

### Tile Server (MVT Specification)
* **`GET /tiles/{z}/{x}/{y}.pbf`**
    * *Description:* Serves Mapbox Vector Tiles directly from PostGIS. The `twistiness_score` is embedded as a feature property so the frontend can dynamically style it.

## 4. Agent Instructions & Constraints
* **Performance First:** Spatial joins and math loops must be optimized. Utilize batch processing for the initial OSM ingestion.
* **Data Hygiene:** Filter out roundabouts, highways with errors, and ferry routes.