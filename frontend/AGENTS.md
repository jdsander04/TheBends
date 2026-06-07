# TheBends - Frontend Agent Blueprint

This document outlines the implementation details for the Flutter mobile application. The frontend focuses on sleek UI, responsive map rendering, and smooth performance while handling heavy geospatial data.

## 1. Tech Stack & State Management
* **Framework:** Flutter (Targeting iOS and Android).
* **Map Rendering:** `flutter_map` (OpenStreetMap/Vector tile compatible) or `mapbox_gl` / `maplibre_gl` for high-performance vector tile styling.
* **State Management:** Bloc or Riverpod (for predictable map states, user location tracking, and route caching).
* **Local Storage:** Hive or Isar DB (for caching downloaded maps/routes for offline driving).

## 2. UI/UX Style Guide ("Clean & Minimal")
* **Theme:** Dark mode by default (optimized for in-car dashboard views).
* **Palette:** Deep slate backgrounds, neon accents (e.g., Electric Green/Cyan for straight roads transitioning to Neon Orange/Hot Magenta for highly twisty sections).
* **Interactions:** Fluid map gestures, persistent bottom sheets for route details, and a clean minimalist search HUD.

## 3. Map Layer & Rendering Implementation
The app needs to overlay the "Twisty Factor" onto the map seamlessly.

### Approach: Vector Tile Styling (Recommended)
1. Use a MapLibre/Vector-based map view.
2. Consume the custom backend tile endpoint (`/tiles/{z}/{x}/{y}.pbf`).
3. Define a style layer expression that dynamically colors the road based on the `twistiness_score` property:
    * Score $< 0.3$: Invisible or faint gray.
    * Score $0.4 - 0.7$: Vibrant Amber.
    * Score $> 0.8$: Intense Crimson/Magenta.

### Alternative Approach: Custom Polyline Overlay
If using raw GeoJSON over standard raster OSM tiles:
1. Fetch `GET /api/v1/roads/bounds` whenever the map camera stops moving.
2. Render custom `Polyline` widgets on top of the map layer, applying a gradient color based on the segment's twistiness.

## 4. Key Screens & Features
* **Map View Screen:** The core hub. Features a toggle to filter roads by minimum "twistiness" via a slider.
* **Route Detail Sheet:** Slid up from the bottom when a twisty road is tapped. Displays distance, average curvature, elevation changes (if available), and user ratings.
* **Drive Mode:** A simplified HUD view that locks onto the user's GPS position, rotating the map in the direction of travel, highlighting upcoming twisty corners.

## 5. Agent Instructions & Constraints
* **FPS Optimization:** Redrawing lines on a map can easily tank frame rates. Ensure map polylines or vector styles are cached and only updated when bounding boxes shift significantly.
* **Battery Efficiency:** Manage GPS polling frequencies carefully, especially when the user isn't actively in "Drive Mode."